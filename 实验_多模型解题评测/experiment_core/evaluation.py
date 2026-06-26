from __future__ import annotations

import json
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from .manifest import load_and_validate_manifest, load_successful_output_problem_set
from .models import ClientFactory, InfrastructureError, ModelConfig, OpenAICompatibleClient, load_model_configs
from .prompting import CodeResponseError, build_prompts, extract_and_validate_code
from .utils import atomic_write_json, read_json, safe_filename, sha256_bytes, storage_name, truncate_text, utc_now_iso


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXECUTION_MODULE_DIR = PROJECT_ROOT / "生成测试用例和标准解法"
if str(EXECUTION_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(EXECUTION_MODULE_DIR))

from local_execution import (  # noqa: E402
    EXECUTION_ERROR,
    EXECUTION_MEMORY_LIMIT,
    EXECUTION_OK,
    EXECUTION_TIMEOUT,
    run_checker,
    run_solution,
)


def _load_problem_payload(problem: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    generation = read_json(Path(problem["generation_artifact_path"]))
    verification = read_json(Path(problem["verification_artifact_path"]))
    return generation, verification


def _test_cases(verification: dict[str, Any]) -> list[dict[str, Any]]:
    cases = []
    for case in verification["bruteforce_verification"]["solved_cases"]:
        source = str(case.get("source", ""))
        if source not in {"random", "adversarial", "small_challenge"}:
            continue
        cases.append(
            {
                "case_id": str(case.get("case_id", "")),
                "category": source,
                "input": case["input"],
                "output": case["output"],
            }
        )
    for case in verification["large_scale_truth_outputs"]["cases"]:
        cases.append(
            {
                "case_id": str(case.get("case_id", "")),
                "category": "large_scale",
                "input": case["input"],
                "output": case["output"],
            }
        )
    return cases


def _execution_summary(result: Any) -> dict[str, Any]:
    return {
        "status": result.status,
        "phase": result.phase,
        "error_type": result.error_type,
        "error_message": result.error_message,
        "duration_seconds": result.duration_seconds,
        "timeout_seconds": result.timeout_seconds,
        "memory_limit_mb": result.memory_limit_mb,
        "peak_memory_mb": result.peak_memory_mb,
        "user_stdout": truncate_text(result.user_stdout, 2_000),
        "user_stderr": truncate_text(result.user_stderr, 2_000),
    }


def _classify_execution(result: Any) -> str:
    if result.status == EXECUTION_TIMEOUT:
        return "timeout"
    if result.status == EXECUTION_MEMORY_LIMIT:
        return "memory_limit"
    if result.status == EXECUTION_ERROR and result.phase in {"compile", "interface"}:
        return "interface_error"
    return "runtime_error"


def _evaluate_case(
    code: str,
    case: dict[str, Any],
    *,
    checker_code: str | None,
    timeout_seconds: float,
    memory_limit_mb: int,
    checker_timeout_seconds: float,
    checker_memory_limit_mb: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    result = run_solution(
        code,
        case["input"],
        timeout_seconds=timeout_seconds,
        memory_limit_mb=memory_limit_mb,
    )
    record: dict[str, Any] = {
        "case_id": case["case_id"],
        "category": case["category"],
        "input_sha256": sha256_bytes(case["input"].encode("utf-8")),
        "input_chars": len(case["input"]),
        "expected_output_sha256": sha256_bytes(case["output"].encode("utf-8")),
        "expected_output_chars": len(case["output"]),
        "execution": _execution_summary(result),
    }
    if result.status != EXECUTION_OK:
        record.update({"passed": False, "classification": _classify_execution(result)})
        return record
    if not isinstance(result.return_value, str):
        record.update(
            {
                "passed": False,
                "classification": "interface_error",
                "actual_return_type": type(result.return_value).__name__,
            }
        )
        return record
    actual = result.return_value
    record.update(
        {
            "actual_output_sha256": sha256_bytes(actual.encode("utf-8")),
            "actual_output_chars": len(actual),
        }
    )
    if checker_code is None:
        passed = actual == case["output"]
        record.update(
            {
                "passed": passed,
                "classification": "accepted" if passed else "wrong_answer",
                "actual_output_preview": "" if passed else truncate_text(actual, 2_000),
                "expected_output_preview": "" if passed else truncate_text(case["output"], 2_000),
            }
        )
        return record
    checker_result = run_checker(
        checker_code,
        case["input"],
        actual,
        timeout_seconds=checker_timeout_seconds,
        memory_limit_mb=checker_memory_limit_mb,
    )
    record["checker_execution"] = _execution_summary(checker_result)
    if checker_result.status != EXECUTION_OK:
        record.update({"passed": False, "classification": "checker_error"})
    elif checker_result.return_value is True:
        record.update({"passed": True, "classification": "accepted_by_checker"})
    elif checker_result.return_value is False:
        record.update({"passed": False, "classification": "wrong_answer"})
    else:
        record.update({"passed": False, "classification": "checker_error"})
    record["evaluation_duration_seconds"] = time.perf_counter() - started
    return record


def _cost(model: ModelConfig, usage: dict[str, int]) -> float | None:
    if model.input_price_per_million is None or model.output_price_per_million is None:
        return None
    return (
        usage.get("prompt_tokens", 0) * model.input_price_per_million
        + usage.get("completion_tokens", 0) * model.output_price_per_million
    ) / 1_000_000


def _result_identity(problem_set_fingerprint: str, model: ModelConfig, problem_id: str) -> dict[str, Any]:
    return {
        # 兼容既有报告与结果文件字段名；直接运行模式下这里保存的是问题集指纹。
        "manifest_sha256": problem_set_fingerprint,
        "model_config_fingerprint": model.fingerprint,
        "problem_id": problem_id,
        "attempt": 1,
    }


def _is_completed_result(path: Path, identity: dict[str, Any]) -> bool:
    if not path.is_file():
        return False
    try:
        result = read_json(path)
    except (OSError, ValueError):
        return False
    return isinstance(result, dict) and result.get("status") == "completed" and result.get("identity") == identity


def _evaluate_job(
    *,
    problem: dict[str, Any],
    model: ModelConfig,
    client: Any,
    problem_set_fingerprint: str,
    result_path: Path,
    generation: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = _result_identity(problem_set_fingerprint, model, problem["problem_id"])
    if _is_completed_result(result_path, identity):
        return {"action": "skipped", "path": str(result_path)}
    if generation is None or verification is None:
        generation, verification = _load_problem_payload(problem)
    generated_problem = generation["generated_problem"]
    system_prompt, user_prompt = build_prompts(generated_problem)
    base_result: dict[str, Any] = {
        "schema_version": 1,
        "created_at": utc_now_iso(),
        "identity": identity,
        "model": model.public_dict(),
        "problem": {
            "problem_id": problem["problem_id"],
            "problem_kind": problem.get("problem_kind", "generated"),
            "pair_id": problem.get("pair_id", ""),
            "title": problem.get("title", ""),
            "source": problem.get("source", ""),
            "applied_rule": problem.get("applied_rule", ""),
            "changed_axes": problem.get("changed_axes", []),
            "algorithm_tags": problem.get("algorithm_tags", []),
        },
        "prompt": {"system": system_prompt, "user": user_prompt},
    }
    try:
        response = client.complete(system_prompt=system_prompt, user_prompt=user_prompt)
    except InfrastructureError as exc:
        base_result.update(
            {
                "status": "infrastructure_error",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "api_attempts": exc.attempts,
            }
        )
        atomic_write_json(result_path, base_result)
        return {"action": "infrastructure_error", "path": str(result_path)}
    except Exception as exc:
        base_result.update(
            {
                "status": "infrastructure_error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        atomic_write_json(result_path, base_result)
        return {"action": "infrastructure_error", "path": str(result_path)}

    base_result["response"] = response
    usage = response.get("usage", {})
    base_result["estimated_cost_usd"] = _cost(model, usage)
    try:
        code = extract_and_validate_code(response["content"])
    except CodeResponseError as exc:
        base_result.update(
            {
                "status": "completed",
                "passed": False,
                "failure_kind": exc.classification,
                "failure_message": str(exc),
                "code": "",
                "category_results": {},
                "case_results": [],
            }
        )
        atomic_write_json(result_path, base_result)
        return {"action": "completed", "path": str(result_path), "passed": False}

    checker = verification.get("checker", {})
    checker_code = None
    if isinstance(checker, dict) and checker.get("needs_checker") is True:
        checker_code = checker.get("verified_checker_code") or checker.get("checker_code")
    standard_limits = verification["standard_solution_verification"]["standard_solution_limits"]
    execution_config = verification.get("execution_metadata", {}).get("execution_config", {})
    case_results = [
        _evaluate_case(
            code,
            case,
            checker_code=checker_code,
            timeout_seconds=float(standard_limits["timeout_seconds"]),
            memory_limit_mb=int(standard_limits["memory_limit_mb"]),
            checker_timeout_seconds=float(execution_config.get("checker_timeout_seconds", 5)),
            checker_memory_limit_mb=int(execution_config.get("checker_memory_limit_mb", 512)),
        )
        for case in _test_cases(verification)
    ]
    category_results = {}
    for category in ("random", "adversarial", "small_challenge", "large_scale"):
        selected = [item for item in case_results if item["category"] == category]
        category_results[category] = {
            "passed": bool(selected) and all(item["passed"] for item in selected),
            "passed_case_count": sum(1 for item in selected if item["passed"]),
            "case_count": len(selected),
        }
    passed = all(item["passed"] for item in category_results.values())
    failure_kind = ""
    if not passed:
        failure_kind = next(
            (item["classification"] for item in case_results if not item["passed"]),
            "wrong_answer",
        )
    base_result.update(
        {
            "status": "completed",
            "passed": passed,
            "failure_kind": failure_kind,
            "code": code,
            "execution_limits": {
                "timeout_seconds": float(standard_limits["timeout_seconds"]),
                "memory_limit_mb": int(standard_limits["memory_limit_mb"]),
                "checker_timeout_seconds": float(execution_config.get("checker_timeout_seconds", 5)),
                "checker_memory_limit_mb": int(execution_config.get("checker_memory_limit_mb", 512)),
            },
            "category_results": category_results,
            "case_results": case_results,
        }
    )
    atomic_write_json(result_path, base_result)
    return {"action": "completed", "path": str(result_path), "passed": passed}


def _evaluate_problem_jobs(
    *,
    problem: dict[str, Any],
    jobs: list[dict[str, Any]],
    model_executor: ThreadPoolExecutor,
    models_per_problem: int,
    on_job_finished: Callable[[dict[str, Any]], None],
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    pending_jobs = []
    for job in jobs:
        identity = _result_identity(job["problem_set_fingerprint"], job["model"], problem["problem_id"])
        if _is_completed_result(job["result_path"], identity):
            outcomes.append({"action": "skipped", "path": str(job["result_path"])})
            on_job_finished(job)
        else:
            pending_jobs.append(job)
    if not pending_jobs:
        return outcomes

    generation, verification = _load_problem_payload(problem)
    job_iterator = iter(pending_jobs)
    active = {}

    def submit_next() -> None:
        try:
            job = next(job_iterator)
        except StopIteration:
            return
        future = model_executor.submit(
            _evaluate_job,
            **job,
            generation=generation,
            verification=verification,
        )
        active[future] = job

    for _ in range(min(models_per_problem, len(pending_jobs))):
        submit_next()

    while active:
        done, _ = wait(active, return_when=FIRST_COMPLETED)
        for future in done:
            job = active.pop(future)
            on_job_finished(job)
            outcomes.append(future.result())
            submit_next()
    return outcomes


def run_experiment(
    *,
    manifest_path: Path | None = None,
    workflow_output_root: Path | None = None,
    models_path: Path,
    output_root: Path,
    run_id: str,
    client_factory: ClientFactory | None = None,
) -> dict[str, Any]:
    if (manifest_path is None) == (workflow_output_root is None):
        raise ValueError("必须且只能指定 manifest_path 或 workflow_output_root。")
    if manifest_path is not None:
        problem_set, problem_set_fingerprint = load_and_validate_manifest(manifest_path)
        problem_source_type = "manifest"
    else:
        problem_set, problem_set_fingerprint = load_successful_output_problem_set(workflow_output_root)
        problem_source_type = "successful_output"

    models, concurrency = load_model_configs(models_path)
    run_dir = output_root.resolve() / safe_filename(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    client_factory = client_factory or OpenAICompatibleClient
    clients = {model.model_id: client_factory(model) for model in models}
    effective_problem_workers = min(concurrency.problem_workers, len(problem_set["problems"]))
    effective_models_per_problem = min(concurrency.models_per_problem, len(models))
    max_model_workers = max(1, effective_problem_workers * effective_models_per_problem)
    run_metadata = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "problem_source_type": problem_source_type,
        "manifest_sha256": problem_set_fingerprint,
        "problem_set_fingerprint": problem_set_fingerprint,
        "manifest_content_fingerprint": problem_set.get("content_fingerprint", ""),
        "models_path": str(models_path.resolve()),
        "concurrency": {
            "requested": concurrency.public_dict(),
            "effective": {
                "problem_workers": effective_problem_workers,
                "models_per_problem": effective_models_per_problem,
                "max_model_workers": max_model_workers,
            },
        },
        "sampling_attempts_per_problem": 1,
        "models": [model.public_dict() for model in models],
        "problem_count": len(problem_set["problems"]),
    }
    if manifest_path is not None:
        run_metadata["manifest_path"] = str(manifest_path.resolve())
    else:
        run_metadata["workflow_output_root"] = str(workflow_output_root.resolve())
        run_metadata["excluded_count"] = int(problem_set.get("excluded_count", 0))
    atomic_write_json(run_dir / "run_metadata.json", run_metadata)

    problem_jobs = []
    for problem in problem_set["problems"]:
        jobs = []
        for model in models:
            model_dir = run_dir / "results" / storage_name(model.model_id)
            jobs.append(
                {
                    "problem": problem,
                    "model": model,
                    "client": clients[model.model_id],
                    "problem_set_fingerprint": problem_set_fingerprint,
                    "result_path": model_dir / f"{storage_name(problem['problem_id'])}.json",
                }
            )
        problem_jobs.append({"problem": problem, "jobs": jobs})

    job_count = sum(len(item["jobs"]) for item in problem_jobs)
    outcomes: list[dict[str, Any]] = []
    progress_lock = Lock()
    progress = {"count": 0}

    def on_job_finished(job: dict[str, Any]) -> None:
        with progress_lock:
            progress["count"] += 1
            print(
                f"[experiment {progress['count']}/{job_count}] "
                f"{job['model'].model_id} / {job['problem']['problem_id']}"
            )

    with ThreadPoolExecutor(max_workers=max_model_workers) as model_executor, ThreadPoolExecutor(
        max_workers=effective_problem_workers
    ) as problem_executor:
        future_map = {
            problem_executor.submit(
                _evaluate_problem_jobs,
                problem=item["problem"],
                jobs=item["jobs"],
                model_executor=model_executor,
                models_per_problem=effective_models_per_problem,
                on_job_finished=on_job_finished,
            ): item
            for item in problem_jobs
        }
        for future in as_completed(future_map):
            outcomes.extend(future.result())
    summary = {
        "run_dir": str(run_dir),
        "job_count": job_count,
        "completed_count": sum(item["action"] in {"completed", "skipped"} for item in outcomes),
        "infrastructure_error_count": sum(item["action"] == "infrastructure_error" for item in outcomes),
        "skipped_count": sum(item["action"] == "skipped" for item in outcomes),
    }
    atomic_write_json(run_dir / "run_outcome.json", summary)
    return summary
