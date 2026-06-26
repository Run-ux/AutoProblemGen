from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .config import VERIFICATION_DIR, load_runtime_config
from .manifest import load_manifest
from .pipeline import _standard_memory, _standard_timeout, _submission_rows, _write_jsonl
from .reporting import generate_report
from .submission_execution import evaluate_submission_on_cases
from .suites import TARGETED_SOURCE, build_suites
from .utils import read_json, utc_now_iso, write_json

if str(VERIFICATION_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFICATION_DIR))

from llm_client import OpenAIChatLLMClient  # noqa: E402
from verification_pipeline import verify_wrong_solution_pool  # noqa: E402


def _completed_problem_dirs(run_dir: Path) -> list[Path]:
    problem_root = run_dir / "problems"
    if not problem_root.is_dir():
        return []
    completed: list[Path] = []
    for problem_dir in sorted(path for path in problem_root.iterdir() if path.is_dir()):
        result_path = problem_dir / "result.json"
        if not result_path.is_file():
            continue
        try:
            result = read_json(result_path)
        except Exception:  # noqa: BLE001 - 预检和批处理阶段跳过损坏结果。
            continue
        if isinstance(result, dict) and result.get("status") == "completed":
            completed.append(problem_dir)
    return completed


def _read_run_metadata(run_dir: Path) -> dict[str, Any]:
    metadata_path = run_dir / "run_metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"缺少 run_metadata.json：{metadata_path}")
    metadata = read_json(metadata_path)
    if not isinstance(metadata, dict):
        raise ValueError(f"run_metadata.json 格式不正确：{metadata_path}")
    return metadata


def _manifest_path_from_metadata(run_dir: Path, metadata: dict[str, Any]) -> Path:
    raw_path = metadata.get("manifest_path")
    if not raw_path:
        raise ValueError(f"run_metadata.json 缺少 manifest_path：{run_dir}")
    manifest_path = Path(str(raw_path))
    if not manifest_path.is_absolute():
        manifest_path = (run_dir / manifest_path).resolve()
    return manifest_path


def _workflow_config_from_metadata(metadata: dict[str, Any], override: Path | None) -> Path | None:
    if override is not None:
        return override
    raw_path = metadata.get("workflow_config_path")
    return Path(str(raw_path)) if raw_path else None


def _problem_id_from_dir(problem_dir: Path, result: dict[str, Any]) -> str:
    return str(result.get("problem_id") or problem_dir.name)


def _language_counts_from_existing_verdicts(problem_dirs: list[Path]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for problem_dir in problem_dirs:
        verdict_path = problem_dir / "candidate_verdicts.jsonl"
        if not verdict_path.is_file():
            continue
        with verdict_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    verdict = json.loads(line)
                except json.JSONDecodeError:
                    continue
                language = str(verdict.get("language", ""))
                if language:
                    counts[language] = counts.get(language, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _targeted_case_count(suites: dict[str, list[dict[str, Any]]]) -> int:
    return sum(1 for case in suites.get("ours_pipeline", []) if str(case.get("source", "")) == TARGETED_SOURCE)


def _update_verification_with_wrong_pool(
    verification: dict[str, Any],
    wrong_pool_result: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(verification)
    solved_cases = list(wrong_pool_result["solved_cases"])
    verified_test_inputs = wrong_pool_result["verified_test_inputs"]
    wrong_pool_verification = wrong_pool_result["verification"]

    bruteforce_verification = dict(verification["bruteforce_verification"])
    bruteforce_verification["solved_cases"] = solved_cases
    bruteforce_verification["solved_case_count"] = len(solved_cases)

    execution_metadata = dict(verification.get("execution_metadata") or {})
    execution_metadata.update(
        {
            "verified_test_input_count": verified_test_inputs.get("count", len(verified_test_inputs.get("cases", []))),
            "solved_case_count": len(solved_cases),
            "wrong_solution_pool_targeted_input_count": wrong_pool_verification.get("targeted_input_count", 0),
            "wrong_solution_pool_killed_count": wrong_pool_verification.get("killed_count", 0),
            "wrong_solution_pool_survived_count": wrong_pool_verification.get("survived_count", 0),
            "wrong_solution_pool_invalid_count": wrong_pool_verification.get("invalid_count", 0),
            "wrong_pool_backfilled_at": utc_now_iso(),
        }
    )

    updated["wrong_solution_pool_verification"] = wrong_pool_verification
    updated["verified_test_inputs"] = verified_test_inputs
    updated["bruteforce_verification"] = bruteforce_verification
    updated["execution_metadata"] = execution_metadata
    return updated


def _submission_ids_for_problem(result: dict[str, Any], manifest_problem: dict[str, Any]) -> tuple[list[int], list[int]]:
    right_ids = result.get("right_submission_ids") or manifest_problem.get("right_submission_ids") or []
    wrong_ids = result.get("wrong_submission_ids") or manifest_problem.get("wrong_submission_ids") or []
    return [int(value) for value in right_ids], [int(value) for value in wrong_ids]


def _evaluate_problem_submissions(
    *,
    problem_dir: Path,
    problem: dict[str, Any],
    result: dict[str, Any],
    verification: dict[str, Any],
    suites: dict[str, list[dict[str, Any]]],
    submissions_by_id: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[int], list[int]]:
    timeout_seconds = _standard_timeout(problem, verification)
    memory_limit_mb = _standard_memory(verification)
    right_ids, wrong_ids = _submission_ids_for_problem(result, problem)
    submission_results: list[dict[str, Any]] = []
    prepared_submissions: dict[str, Any] = {}
    submission_cache_dir = problem_dir / "compiled_submissions"
    for suite_name, cases in suites.items():
        for submission_id in [*right_ids, *wrong_ids]:
            submission = submissions_by_id[int(submission_id)]
            submission_results.append(
                evaluate_submission_on_cases(
                    submission=submission,
                    suite_name=suite_name,
                    cases=cases,
                    timeout_seconds=timeout_seconds,
                    memory_limit_mb=memory_limit_mb,
                    submission_cache_dir=submission_cache_dir,
                    prepared_submissions=prepared_submissions,
                )
            )
    return submission_results, right_ids, wrong_ids


def _backfill_problem(
    *,
    problem_dir: Path,
    problem: dict[str, Any],
    result: dict[str, Any],
    submissions_by_id: dict[int, dict[str, Any]],
    client: Any,
    runtime: dict[str, Any],
) -> dict[str, Any]:
    problem_id = _problem_id_from_dir(problem_dir, result)
    artifact_path = problem_dir / "artifact.json"
    verification_path = problem_dir / "verification.json"
    if not artifact_path.is_file():
        raise FileNotFoundError(f"缺少 artifact.json：{problem_id}")
    if not verification_path.is_file():
        raise FileNotFoundError(f"缺少 verification.json：{problem_id}")

    artifact = read_json(artifact_path)
    verification = read_json(verification_path)
    before_targeted = int(
        verification.get("wrong_solution_pool_verification", {}).get("targeted_input_count", 0)
    )
    wrong_pool_result = verify_wrong_solution_pool(
        artifact,
        verification,
        verification["verified_test_inputs"],
        verification["bruteforce_verification"],
        verification["checker_verification"],
        client,
        runtime["execution_config"],
        runtime["context_limits"],
    )
    updated_verification = _update_verification_with_wrong_pool(verification, wrong_pool_result)
    write_json(verification_path, updated_verification)

    suites = build_suites(updated_verification, execution_config=runtime["execution_config"])
    write_json(problem_dir / "suites.json", suites)

    submission_results, right_ids, wrong_ids = _evaluate_problem_submissions(
        problem_dir=problem_dir,
        problem=problem,
        result=result,
        verification=updated_verification,
        suites=suites,
        submissions_by_id=submissions_by_id,
    )
    verdict_path = problem_dir / "candidate_verdicts.jsonl"
    _write_jsonl(verdict_path, submission_results)

    result_path = problem_dir / "result.json"
    updated_result = {
        **result,
        "status": "completed",
        "problem_id": problem_id,
        "suite_case_counts": {name: len(cases) for name, cases in suites.items()},
        "right_submission_ids": right_ids,
        "wrong_submission_ids": wrong_ids,
        "result_path": str(result_path),
        "candidate_verdicts_path": str(verdict_path),
        "wrong_pool_backfill": {
            "updated_at": utc_now_iso(),
            "targeted_input_count_before": before_targeted,
            "targeted_input_count_after": wrong_pool_result["verification"].get("targeted_input_count", 0),
            "suite_wrong_pool_targeted_count": _targeted_case_count(suites),
        },
    }
    write_json(result_path, updated_result)
    return {
        "status": "completed",
        "problem_id": problem_id,
        "targeted_input_count_before": before_targeted,
        "targeted_input_count_after": wrong_pool_result["verification"].get("targeted_input_count", 0),
        "suite_wrong_pool_targeted_count": _targeted_case_count(suites),
        "suite_case_counts": updated_result["suite_case_counts"],
    }


def backfill_wrong_pool_run(
    *,
    run_dir: Path,
    workflow_config_path: Path | None = None,
    dry_run: bool = False,
    problem_ids: set[str] | None = None,
    limit: int | None = None,
    skip_report: bool = False,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    metadata = _read_run_metadata(run_dir)
    manifest_path = _manifest_path_from_metadata(run_dir, metadata)
    manifest = load_manifest(manifest_path)
    manifest_by_problem_id = {str(problem["problem_id"]): problem for problem in manifest["problems"]}
    completed_dirs = _completed_problem_dirs(run_dir)
    if problem_ids is not None:
        completed_dirs = [
            problem_dir
            for problem_dir in completed_dirs
            if _problem_id_from_dir(problem_dir, read_json(problem_dir / "result.json")) in problem_ids
        ]
    if limit is not None:
        completed_dirs = completed_dirs[:limit]

    dry_run_summary = {
        "run_dir": str(run_dir),
        "manifest_path": str(manifest_path),
        "completed_problem_count": len(completed_dirs),
        "language_counts": _language_counts_from_existing_verdicts(completed_dirs),
    }
    if dry_run:
        return {"status": "dry_run", **dry_run_summary, "outcomes": []}

    runtime = load_runtime_config(_workflow_config_from_metadata(metadata, workflow_config_path))
    client = OpenAIChatLLMClient(runtime["llm_config"])
    all_submission_ids: set[int] = set()
    problem_results: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    for problem_dir in completed_dirs:
        result = read_json(problem_dir / "result.json")
        problem_id = _problem_id_from_dir(problem_dir, result)
        if problem_id not in manifest_by_problem_id:
            raise KeyError(f"manifest 中找不到已完成题目：{problem_id}")
        problem = manifest_by_problem_id[problem_id]
        right_ids, wrong_ids = _submission_ids_for_problem(result, problem)
        all_submission_ids.update(right_ids)
        all_submission_ids.update(wrong_ids)
        problem_results.append((problem_dir, result, problem))

    submissions_by_id = _submission_rows(manifest["submission_parquet_url"], all_submission_ids)
    outcomes: list[dict[str, Any]] = []
    for index, (problem_dir, result, problem) in enumerate(problem_results, start=1):
        problem_id = _problem_id_from_dir(problem_dir, result)
        print(f"[backfill {index}/{len(problem_results)}] {problem_id}", flush=True)
        try:
            outcomes.append(
                _backfill_problem(
                    problem_dir=problem_dir,
                    problem=problem,
                    result=result,
                    submissions_by_id=submissions_by_id,
                    client=client,
                    runtime=runtime,
                )
            )
        except Exception as exc:  # noqa: BLE001 - 单题失败不应覆盖原 completed 结果。
            outcomes.append(
                {
                    "status": "failed",
                    "problem_id": problem_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    report_summary = {"status": "skipped"} if skip_report else generate_report(run_dir)
    completed_outcomes = [item for item in outcomes if item.get("status") == "completed"]
    failed_outcomes = [item for item in outcomes if item.get("status") == "failed"]
    return {
        "status": "completed" if not failed_outcomes else "partial",
        **dry_run_summary,
        "backfilled_problem_count": len(completed_outcomes),
        "failed_problem_count": len(failed_outcomes),
        "targeted_input_count_after": sum(int(item.get("targeted_input_count_after", 0)) for item in completed_outcomes),
        "targeted_problem_count_after": sum(
            int(item.get("targeted_input_count_after", 0)) > 0 for item in completed_outcomes
        ),
        "outcomes": outcomes,
        "report_status": report_summary.get("status"),
    }


def backfill_wrong_pool_runs(
    *,
    run_dirs: list[Path],
    workflow_config_path: Path | None = None,
    dry_run: bool = False,
    problem_ids: set[str] | None = None,
    limit: int | None = None,
    skip_report: bool = False,
) -> dict[str, Any]:
    run_summaries = [
        backfill_wrong_pool_run(
            run_dir=run_dir,
            workflow_config_path=workflow_config_path,
            dry_run=dry_run,
            problem_ids=problem_ids,
            limit=limit,
            skip_report=skip_report,
        )
        for run_dir in run_dirs
    ]
    failed_runs = [item for item in run_summaries if item.get("status") not in {"completed", "dry_run"}]
    return {
        "status": "completed" if not failed_runs else "partial",
        "dry_run": dry_run,
        "run_count": len(run_summaries),
        "runs": run_summaries,
    }
