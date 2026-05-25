from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from llm_trace import (
    WORKFLOW_CURRENT_PROBLEM_ID,
    WORKFLOW_CURRENT_STAGE,
    WORKFLOW_LLM_TRACE_PATH,
    WORKFLOW_RUN_ID,
)
from runtime_config import (
    ContextLimits,
    ExecutionLimits,
    LLMEndpointConfig,
    RuntimeConfigError,
    load_env_values,
    load_llm_endpoint_config,
    runtime_env_payload,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = MODULE_ROOT / "output"

TUPLE_EXTRACT_DIR = PROJECT_ROOT / "四元组抽取"
PROBLEM_GENERATION_DIR = PROJECT_ROOT / "生成题面"

TUPLE_EXTRACT_SCRIPT = TUPLE_EXTRACT_DIR / "extract.py"
PROBLEM_GENERATION_SCRIPT = PROBLEM_GENERATION_DIR / "main.py"
VERIFICATION_RUNNER_SCRIPT = MODULE_ROOT / "verification_runner.py"

TUPLE_DIMENSIONS = (
    "input_structure",
    "core_constraints",
    "objective",
    "invariant",
)


class WorkflowError(RuntimeError):
    """总流程执行阶段错误。"""


@dataclass(frozen=True)
class WorkflowConfig:
    input_path: Path
    generation_llm: LLMEndpointConfig
    embedding_llm: LLMEndpointConfig
    execution_limits: ExecutionLimits
    context_limits: ContextLimits
    output_root: Path = DEFAULT_OUTPUT_ROOT
    run_id: str | None = None
    quality_iterations: int = 3
    quality_full_score_max_iterations: int = 10
    verification_timeout_seconds: float = 0.0
    python_executable: str = sys.executable
    workflow_config_path: Path | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> "WorkflowConfig":
        config_path = Path(path).resolve()
        values = load_env_values(config_path)
        base_dir = config_path.parent
        source = str(config_path)
        _reject_removed_workflow_keys(values, source=source)
        generation_llm_path = _resolve_config_path(
            _require_text(values, "GENERATION_LLM_CONFIG", source=source),
            base_dir=base_dir,
        )
        embedding_llm_path = _resolve_config_path(
            _require_text(values, "EMBEDDING_LLM_CONFIG", source=source),
            base_dir=base_dir,
        )
        return cls(
            input_path=_resolve_config_path(_require_text(values, "INPUT_PATH", source=source), base_dir=base_dir),
            output_root=_resolve_config_path(
                values.get("OUTPUT_ROOT", str(DEFAULT_OUTPUT_ROOT)) or str(DEFAULT_OUTPUT_ROOT),
                base_dir=base_dir,
            ),
            run_id=_optional_text(values, "RUN_ID"),
            quality_iterations=_read_int(values, "QUALITY_ITERATIONS", 3, source=source),
            quality_full_score_max_iterations=_read_positive_int(
                values,
                "QUALITY_FULL_SCORE_MAX_ITERATIONS",
                10,
                source=source,
            ),
            verification_timeout_seconds=_read_float(
                values,
                "VERIFICATION_TIMEOUT_SECONDS",
                0.0,
                source=source,
            ),
            python_executable=_optional_text(values, "PYTHON_EXECUTABLE") or sys.executable,
            generation_llm=load_llm_endpoint_config(generation_llm_path),
            embedding_llm=load_llm_endpoint_config(embedding_llm_path),
            execution_limits=ExecutionLimits.from_values(values, source=source),
            context_limits=ContextLimits.from_values(values, source=source),
            workflow_config_path=config_path,
        )

    def runtime_env(self) -> dict[str, str]:
        return runtime_env_payload(
            generation_llm=self.generation_llm,
            embedding_llm=self.embedding_llm,
            execution_limits=self.execution_limits,
            context_limits=self.context_limits,
        )


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    cwd: str
    log_path: str
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def to_summary(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "cwd": self.cwd,
            "log_path": self.log_path,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
        }


class CommandRunner(Protocol):
    def __call__(
        self,
        command: list[str],
        *,
        cwd: Path,
        log_path: Path,
        env: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        ...


def default_command_runner(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> CommandResult:
    """执行外部阶段命令，实时透传终端输出，并把完整 stdout/stderr 保存到总流程日志。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []

    def pipe_reader(pipe: Any, sink: Any, parts: list[str]) -> None:
        try:
            for line in iter(pipe.readline, ""):
                parts.append(line)
                sink.write(line)
                sink.flush()
        finally:
            pipe.close()

    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=process_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout_thread = threading.Thread(
        target=pipe_reader,
        args=(process.stdout, sys.stdout, stdout_parts),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=pipe_reader,
        args=(process.stderr, sys.stderr, stderr_parts),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait(timeout=5)
        returncode = -1
        stderr_parts.append(f"命令超时：{timeout_seconds} 秒\n")
    finally:
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

    result = CommandResult(
        command=list(command),
        cwd=str(cwd),
        log_path=str(log_path),
        returncode=returncode,
        stdout="".join(stdout_parts),
        stderr="".join(stderr_parts),
        timed_out=timed_out,
    )

    if timed_out and not result.stderr:
        result = CommandResult(
            command=list(command),
            cwd=str(cwd),
            log_path=str(log_path),
            returncode=-1,
            stdout="".join(stdout_parts),
            stderr=f"命令超时：{timeout_seconds} 秒",
            timed_out=True,
        )

    log_text = [
        "# command",
        _format_command(command),
        "",
        "# cwd",
        str(cwd),
        "",
        "# runtime_env_keys",
        ", ".join(sorted(env.keys())) if env else "",
        "",
        "# returncode",
        str(result.returncode),
        "",
        "# timed_out",
        str(result.timed_out),
        "",
        "# stdout",
        result.stdout,
        "",
        "# stderr",
        result.stderr,
        "",
    ]
    log_path.write_text("\n".join(log_text), encoding="utf-8")
    return result


def run_workflow(
    config: WorkflowConfig,
    *,
    command_runner: CommandRunner | None = None,
    progress_writer: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    runner = command_runner or default_command_runner
    progress = progress_writer or (lambda message: print(message, flush=True))

    input_path = config.input_path.resolve()
    output_root = config.output_root.resolve()
    run_id, run_id_source = _resolve_run_id(config, input_path)
    run_dir = output_root / run_id
    paths = _build_paths(run_dir)
    _ensure_dirs(paths)

    problems = _load_input_problem_entries(input_path)
    summary_path = paths["summary"]
    existing_summary = _load_existing_summary(summary_path)
    summary = _build_run_summary(
        config=config,
        input_path=input_path,
        output_root=output_root,
        run_id=run_id,
        run_id_source=run_id_source,
        paths=paths,
        problems=problems,
        existing_summary=existing_summary,
    )

    try:
        skip_count = sum(1 for problem in summary["problems"] if _can_skip_problem(problem))
        progress("=" * 80)
        progress("[workflow] 运行开始")
        progress(f"[workflow] run_id={run_id}；来源={run_id_source}")
        progress(
            f"[workflow] 输入={input_path}；模式={'目录' if input_path.is_dir() else '单文件'}；"
            f"题目总数={len(problems)}"
        )
        progress(
            f"[workflow] 历史 summary={'已发现' if existing_summary else '未发现'}；"
            f"可跳过={skip_count}；待处理={len(problems) - skip_count}"
        )
        progress(f"[workflow] summary={summary_path}")
        progress(f"[workflow] 日志目录={paths['logs']}")
        progress(f"[workflow] LLM 详细调用日志={paths['llm_trace']}")
        _write_summary(summary_path, summary)

        for order, problem in enumerate(summary["problems"], start=1):
            if _can_skip_problem(problem):
                problem["skipped_this_run"] = True
                progress("=" * 80)
                progress(f"[problem {order}/{len(problems)}] 跳过")
                progress(f"[problem] problem_id={problem['problem_id']}")
                progress("[problem] 原因=workflow_summary 显示 verified，且输入文件 hash 未变化。")
                progress(
                    "[problem] 上次完成状态=verified；"
                    f"input_hash校验=match；previous={_short_hash(problem.get('previous_input_sha256'))}；"
                    f"current={_short_hash(problem.get('input_sha256'))}"
                )
                continue

            problem["resume_decision"] = _resume_decision(problem)
            _reset_problem_for_current_run(problem)
            _run_single_problem_workflow(
                config=config,
                runner=runner,
                paths=paths,
                summary=summary,
                problem=problem,
                order=order,
                total=len(problems),
                progress=progress,
            )
            _write_summary(summary_path, summary)

        summary["status"] = _derive_overall_status(summary["problems"])
        _emit_final_progress(progress, summary, summary_path, paths["llm_trace"])
        return _finalize_summary(summary_path, summary)
    except WorkflowError as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)
        _emit_final_progress(progress, summary, summary_path, paths["llm_trace"])
        return _finalize_summary(summary_path, summary)
    except Exception as exc:  # 兜底只负责摘要落盘，异常信息仍在 status 中暴露。
        summary["status"] = "failed"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        _emit_final_progress(progress, summary, summary_path, paths["llm_trace"])
        return _finalize_summary(summary_path, summary)


def _resolve_run_id(config: WorkflowConfig, input_path: Path) -> tuple[str, str]:
    if config.run_id:
        return config.run_id, "RUN_ID 配置"
    digest = hashlib.sha256(str(input_path.resolve()).lower().encode("utf-8")).hexdigest()[:8]
    name = input_path.name or "input"
    return f"input_{_safe_path_part(name)}_{digest}", "INPUT_PATH 稳定指纹"


def _load_existing_summary(summary_path: Path) -> dict[str, Any] | None:
    if not summary_path.exists():
        return None
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _build_run_summary(
    *,
    config: WorkflowConfig,
    input_path: Path,
    output_root: Path,
    run_id: str,
    run_id_source: str,
    paths: dict[str, Path],
    problems: list[dict[str, str]],
    existing_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    existing_problems = {
        str(item.get("problem_id", "")): item
        for item in (existing_summary or {}).get("problems", [])
        if isinstance(item, dict)
    }
    merged_problems: list[dict[str, Any]] = []
    for item in problems:
        problem_id = item["problem_id"]
        old_item = existing_problems.get(problem_id)
        if isinstance(old_item, dict):
            entry = json.loads(json.dumps(old_item, ensure_ascii=False))
            entry["previous_input_sha256"] = str(old_item.get("input_sha256", ""))
        else:
            entry = {
                "problem_id": problem_id,
                "status": "pending",
                "tuple": {},
                "generation": {},
                "previous_input_sha256": "",
            }
        entry["problem_id"] = problem_id
        entry["input_path"] = item["input_path"]
        entry["input_sha256"] = item["input_sha256"]
        entry.setdefault("tuple", {})
        entry.setdefault("generation", {})
        merged_problems.append(entry)

    return {
        "run_id": run_id,
        "run_id_source": run_id_source,
        "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": "",
        "config": _config_summary(config, input_path=input_path, output_root=output_root, run_id=run_id),
        "paths": {key: str(value) for key, value in paths.items()},
        "resume": {
            "existing_summary_found": existing_summary is not None,
            "loaded_from": str(paths["summary"]) if existing_summary else "",
        },
        "stages": list((existing_summary or {}).get("stages", [])),
        "problems": merged_problems,
        "counts": {},
    }


def _can_skip_problem(problem: dict[str, Any]) -> bool:
    return (
        problem.get("status") == "verified"
        and bool(problem.get("input_sha256"))
        and problem.get("previous_input_sha256") == problem.get("input_sha256")
    )


def _resume_decision(problem: dict[str, Any]) -> str:
    previous_status = str(problem.get("status") or "pending")
    previous_hash = str(problem.get("previous_input_sha256") or "")
    current_hash = str(problem.get("input_sha256") or "")
    if previous_hash and previous_hash != current_hash:
        return (
            f"历史状态={previous_status}；输入hash变化；"
            f"previous={_short_hash(previous_hash)}；current={_short_hash(current_hash)}；"
            "从四元组抽取开始完整重跑。"
        )
    if previous_status != "pending":
        return f"历史状态={previous_status}；不满足 verified+hash未变化 跳过条件，从四元组抽取开始完整重跑。"
    return "未发现可复用的完成记录，从四元组抽取开始完整处理。"


def _short_hash(value: Any) -> str:
    text = str(value or "")
    return text[:12] if text else "无"


def _reset_problem_for_current_run(problem: dict[str, Any]) -> None:
    problem["status"] = "pending"
    problem["tuple"] = {}
    problem["generation"] = {}
    problem["skipped_this_run"] = False
    problem["processed_this_run"] = True


def _run_single_problem_workflow(
    *,
    config: WorkflowConfig,
    runner: CommandRunner,
    paths: dict[str, Path],
    summary: dict[str, Any],
    problem: dict[str, Any],
    order: int,
    total: int,
    progress: Callable[[str], None],
) -> None:
    problem_id = str(problem["problem_id"])
    input_path = Path(str(problem["input_path"]))
    progress("=" * 80)
    progress(f"[problem {order}/{total}] 开始处理")
    progress(f"[problem] problem_id={problem_id}")
    progress(f"[problem] 输入文件={input_path}")
    if problem.get("resume_decision"):
        progress(f"[problem] 续传决策={problem['resume_decision']}")

    progress("[stage 1/5] 四元组抽取开始")
    _run_extract_stage(
        config,
        runner,
        paths,
        input_path,
        summary,
        problem_id=problem_id,
        order=order,
    )
    tuple_status = _collect_single_tuple_raw_status(paths["tuple_raw"], problem_id)
    problem["tuple"] = tuple_status
    if not tuple_status["success"]:
        problem["status"] = "skipped_before_generation"
        progress(
            f"[stage 1/5] 四元组抽取未通过；失败维度={','.join(tuple_status['failed_dimensions']) or '无'}。"
        )
        progress("[problem] 本题结束，继续下一题。")
        return
    progress(
        f"[stage 1/5] 四元组抽取完成；成功维度=4/4；raw目录={paths['tuple_raw']}。"
    )

    progress("[stage 2/5] 组装题面生成输入开始")
    generation_source_dir = _prepare_generation_source_for_problem(
        raw_dir=paths["tuple_raw"],
        generation_source_root=paths["generation_source"],
        problem=problem,
    )
    if problem.get("status") == "tuple_assembly_failed":
        progress(f"[stage 2/5] 组装失败：{problem['tuple'].get('assembly_error', '')}")
        progress("[problem] 本题结束，继续下一题。")
        return
    progress(f"[stage 2/5] 组装完成；source_dir={generation_source_dir}")

    progress("[stage 3/5] 题面生成开始")
    _run_generation_stage(
        config,
        runner,
        paths,
        summary,
        source_dir=generation_source_dir,
        problem_id=problem_id,
        order=order,
    )
    batch_summary = _load_generation_batch_summary(paths["generation_artifacts"], expected_problem_id=problem_id)
    _apply_generation_results(batch_summary, {problem_id: problem})
    if problem.get("status") != "generated":
        progress(f"[stage 3/5] 题面生成未完成；状态={problem.get('status')}。")
        progress("[problem] 本题结束，继续下一题。")
        return
    generation = problem.get("generation", {})
    progress(f"[stage 3/5] 题面生成完成；artifact={generation.get('artifact_path', '')}")

    progress("[stage 4/5] 质量门槛检查开始")
    if not isinstance(generation, dict):
        problem["status"] = "generation_failed"
        problem["generation"] = {"status": "generation_failed", "error_reason": "generation 必须是对象。"}
        progress("[stage 4/5] generation 结构异常，跳过验证。")
        return
    gate = _quality_gate_result(generation)
    generation["quality_gate"] = gate
    if not gate["passed"]:
        generation["status"] = "quality_gate_failed"
        problem["status"] = "quality_gate_failed"
        progress(
            "[stage 4/5] 质量门槛未通过；"
            f"quality_status={gate.get('quality_status', '')}；"
            f"generated_status={gate.get('generated_status', '')}；"
            f"stop_reason={gate.get('stop_reason', '')}。"
        )
        progress("[problem] 本题结束，继续下一题。")
        return
    progress("[stage 4/5] 质量门槛通过")

    progress("[stage 5/5] 验证开始")
    _run_verification_for_single_problem(
        config=config,
        runner=runner,
        paths=paths,
        summary=summary,
        problem=problem,
        order=order,
        progress=progress,
    )
    progress(f"[problem {order}/{total}] 完成；最终状态={problem.get('status')}")


def _collect_single_tuple_raw_status(raw_dir: Path, problem_id: str) -> dict[str, Any]:
    status = {
        "success": False,
        "dimension_status": {dimension: "missing" for dimension in TUPLE_DIMENSIONS},
        "failed_dimensions": list(TUPLE_DIMENSIONS),
    }
    for dimension in TUPLE_DIMENSIONS:
        raw_file = raw_dir / f"{problem_id}_{dimension}.json"
        if not raw_file.exists():
            continue
        try:
            payload = json.loads(raw_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status["dimension_status"][dimension] = "invalid_json"
            continue
        status["dimension_status"][dimension] = str(payload.get("status", ""))
    failed = [
        dimension
        for dimension in TUPLE_DIMENSIONS
        if status["dimension_status"].get(dimension) != "success"
    ]
    status["failed_dimensions"] = failed
    status["success"] = not failed
    return status


def _prepare_generation_source_for_problem(
    *,
    raw_dir: Path,
    generation_source_root: Path,
    problem: dict[str, Any],
) -> Path:
    problem_id = str(problem["problem_id"])
    generation_source_dir = generation_source_root / _safe_path_part(problem_id)
    generation_source_dir.mkdir(parents=True, exist_ok=True)
    target = generation_source_dir / f"{problem_id}.json"
    try:
        original_problem = _load_original_problem_for_generation(
            input_path=Path(str(problem.get("input_path", ""))),
            expected_problem_id=problem_id,
        )
        payload = _build_generation_source_payload(raw_dir, problem_id, original_problem=original_problem)
    except WorkflowError as exc:
        problem["status"] = "tuple_assembly_failed"
        problem["tuple"]["generation_source_path"] = ""
        problem["tuple"]["assembly_error"] = str(exc)
        return generation_source_dir
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    problem["status"] = "ready_for_generation"
    problem["tuple"]["generation_source_path"] = str(target)
    return generation_source_dir


def _build_paths(run_dir: Path) -> dict[str, Path]:
    return {
        "run_dir": run_dir,
        "tuple_root": run_dir / "tuple",
        "tuple_raw": run_dir / "tuple" / "raw",
        "generation_root": run_dir / "generation",
        "generation_source": run_dir / "generation" / "source",
        "generation_output": run_dir / "generation" / "output",
        "generation_artifacts": run_dir / "generation" / "artifacts",
        "generation_reports": run_dir / "generation" / "reports",
        "verification": run_dir / "verification",
        "logs": run_dir / "logs",
        "llm_trace": run_dir / "logs" / "llm_calls.jsonl",
        "summary": run_dir / "workflow_summary.json",
    }


def _ensure_dirs(paths: dict[str, Path]) -> None:
    for key in (
        "tuple_root",
        "generation_source",
        "generation_output",
        "generation_artifacts",
        "generation_reports",
        "verification",
        "logs",
    ):
        paths[key].mkdir(parents=True, exist_ok=True)


def _config_summary(
    config: WorkflowConfig,
    *,
    input_path: Path,
    output_root: Path,
    run_id: str,
) -> dict[str, Any]:
    return {
        "workflow_config_path": str(config.workflow_config_path) if config.workflow_config_path else "",
        "input_path": str(input_path),
        "output_root": str(output_root),
        "run_id": run_id,
        "quality_iterations": config.quality_iterations,
        "quality_full_score_max_iterations": config.quality_full_score_max_iterations,
        "verification_timeout_seconds": config.verification_timeout_seconds,
        "verification_outer_timeout_enabled": False,
        "verification_timeout_policy": "外层验证总超时已禁用；验证阶段依赖 LLM 与本地执行的内部阶段超时。",
        "python_executable": config.python_executable,
        "generation_llm": config.generation_llm.to_safe_summary(),
        "embedding_llm": config.embedding_llm.to_safe_summary(),
        "execution_limits": asdict(config.execution_limits),
        "context_limits": asdict(config.context_limits),
    }


def _load_input_problem_entries(input_path: Path) -> list[dict[str, str]]:
    if not input_path.exists():
        raise WorkflowError(f"输入路径不存在：{input_path}")

    if input_path.is_dir():
        files = [
            path
            for path in sorted(input_path.glob("*.json"))
            if path.name.lower() != "manifest.json"
        ]
    else:
        files = [input_path]

    if not files:
        raise WorkflowError(f"输入路径中没有可用 JSON 题目：{input_path}")

    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WorkflowError(f"输入 JSON 解析失败：{path}；{exc.msg}") from exc
        if not isinstance(payload, dict):
            raise WorkflowError(f"输入文件必须是单题 JSON 对象：{path}")
        problem_id = str(payload.get("problem_id", "")).strip()
        if not problem_id:
            raise WorkflowError(f"输入题目缺少 problem_id：{path}")
        if problem_id in seen:
            raise WorkflowError(f"输入中存在重复 problem_id：{problem_id}")
        seen.add(problem_id)
        entries.append(
            {
                "problem_id": problem_id,
                "input_path": str(path),
                "input_sha256": _file_sha256(path),
            }
        )
    return entries


def _run_extract_stage(
    config: WorkflowConfig,
    runner: CommandRunner,
    paths: dict[str, Path],
    input_path: Path,
    summary: dict[str, Any],
    *,
    problem_id: str,
    order: int,
) -> None:
    command = [
        config.python_executable,
        str(TUPLE_EXTRACT_SCRIPT),
        "--input",
        str(input_path),
        "--output",
        str(paths["tuple_root"]),
    ]
    result = runner(
        command,
        cwd=TUPLE_EXTRACT_DIR,
        log_path=paths["logs"] / f"01_tuple_extract_{order:03d}_{_safe_path_part(problem_id)}.log",
        env=_stage_env(config, paths, problem_id=problem_id, stage="tuple_extract"),
    )
    _append_stage(summary, f"tuple_extract:{problem_id}", result)
    if not result.ok:
        raise WorkflowError(f"{problem_id} 四元组抽取子进程失败，详见日志：" + result.log_path)


def _run_generation_stage(
    config: WorkflowConfig,
    runner: CommandRunner,
    paths: dict[str, Path],
    summary: dict[str, Any],
    *,
    source_dir: Path,
    problem_id: str,
    order: int,
) -> None:
    command = [
        config.python_executable,
        str(PROBLEM_GENERATION_SCRIPT),
        "--mode",
        "single",
        "--source-dir",
        str(source_dir),
        "--output-dir",
        str(paths["generation_output"]),
        "--artifact-dir",
        str(paths["generation_artifacts"]),
        "--report-dir",
        str(paths["generation_reports"]),
        "--quality-iterations",
        str(config.quality_iterations),
        "--quality-full-score-max-iterations",
        str(config.quality_full_score_max_iterations),
    ]

    result = runner(
        command,
        cwd=PROBLEM_GENERATION_DIR,
        log_path=paths["logs"] / f"03_problem_generation_{order:03d}_{_safe_path_part(problem_id)}.log",
        env=_stage_env(config, paths, problem_id=problem_id, stage="problem_generation"),
    )
    _append_stage(summary, f"problem_generation:{problem_id}", result)
    if not result.ok:
        raise WorkflowError(f"{problem_id} 生成题面子进程失败，详见日志：" + result.log_path)


def _append_stage(summary: dict[str, Any], name: str, result: CommandResult) -> None:
    item = {"name": name, **result.to_summary()}
    item["status"] = "ok" if result.ok else "failed"
    summary["stages"].append(item)


def _collect_tuple_raw_status(raw_dir: Path, problem_map: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    raw_status: dict[str, dict[str, Any]] = {
        problem_id: {
            "success": False,
            "dimension_status": {dimension: "missing" for dimension in TUPLE_DIMENSIONS},
            "failed_dimensions": list(TUPLE_DIMENSIONS),
        }
        for problem_id in problem_map
    }

    for raw_file in sorted(raw_dir.glob("*.json")):
        try:
            payload = json.loads(raw_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        problem_id = str(payload.get("problem_id", "")).strip()
        dimension = str(payload.get("dimension", "")).strip()
        if problem_id not in raw_status or dimension not in TUPLE_DIMENSIONS:
            continue
        raw_status[problem_id]["dimension_status"][dimension] = str(payload.get("status", ""))

    for status in raw_status.values():
        failed = [
            dimension
            for dimension in TUPLE_DIMENSIONS
            if status["dimension_status"].get(dimension) != "success"
        ]
        status["failed_dimensions"] = failed
        status["success"] = not failed
    return raw_status


def _prepare_generation_source(
    *,
    raw_dir: Path,
    generation_source_dir: Path,
    eligible_problem_ids: list[str],
    problem_map: dict[str, dict[str, Any]],
) -> list[str]:
    generation_source_dir.mkdir(parents=True, exist_ok=True)
    ready: list[str] = []
    for problem_id in eligible_problem_ids:
        target = generation_source_dir / f"{problem_id}.json"
        entry = problem_map[problem_id]
        try:
            payload = _build_generation_source_from_raw(raw_dir, problem_id)
        except WorkflowError as exc:
            entry["status"] = "tuple_assembly_failed"
            entry["tuple"]["generation_source_path"] = ""
            entry["tuple"]["assembly_error"] = str(exc)
            continue
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        entry["status"] = "ready_for_generation"
        entry["tuple"]["generation_source_path"] = str(target)
        ready.append(problem_id)
    return ready


def _build_generation_source_from_raw(raw_dir: Path, problem_id: str) -> dict[str, Any]:
    return _build_generation_source_payload(raw_dir, problem_id, original_problem=None)


def _build_generation_source_payload(
    raw_dir: Path,
    problem_id: str,
    *,
    original_problem: dict[str, Any] | None,
) -> dict[str, Any]:
    dimensions: dict[str, dict[str, Any]] = {}
    source = ""
    for dimension in TUPLE_DIMENSIONS:
        raw_path = raw_dir / f"{problem_id}_{dimension}.json"
        if not raw_path.exists():
            raise WorkflowError(f"缺少四元组 raw 结果：{raw_path}")
        try:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WorkflowError(f"四元组 raw JSON 解析失败：{raw_path}；{exc.msg}") from exc
        if payload.get("status") != "success":
            raise WorkflowError(f"四元组 raw 结果不是 success：{raw_path}")
        result = payload.get("result", {})
        if not isinstance(result, dict):
            raise WorkflowError(f"四元组 raw result 必须是对象：{raw_path}")
        dimensions[dimension] = _final_dimension_result(result, dimension)
        if not source:
            source_value = payload.get("source", "")
            source = source_value if isinstance(source_value, str) else str(source_value)

    return {
        "problem_id": problem_id,
        "source": source,
        "input_structure": dimensions["input_structure"],
        "core_constraints": dimensions["core_constraints"],
        "objective": dimensions["objective"],
        "invariant": dimensions["invariant"],
        "original_problem": original_problem,
    }


def _load_original_problem_for_generation(input_path: Path, expected_problem_id: str) -> dict[str, Any]:
    if not input_path.exists():
        raise WorkflowError(f"原题输入 JSON 不存在，无法组装原题文本：{input_path}")
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorkflowError(f"原题输入 JSON 读取失败：{input_path}；{exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"原题输入 JSON 解析失败：{input_path}；{exc.msg}") from exc
    if not isinstance(payload, dict):
        raise WorkflowError(f"原题输入 JSON 顶层必须是对象：{input_path}")

    problem_id = str(payload.get("problem_id", "")).strip()
    if problem_id and problem_id != expected_problem_id:
        raise WorkflowError(
            "原题输入 JSON 的 problem_id 与当前题不一致："
            f"{input_path}；期望={expected_problem_id}；实际={problem_id}"
        )
    return dict(payload)


def _final_dimension_result(result: dict[str, Any], dimension: str) -> dict[str, Any]:
    if dimension == "input_structure":
        normalized = dict(result)
        normalized.setdefault("type", None)
        return normalized
    if dimension == "objective":
        normalized = dict(result)
        normalized.setdefault("type", None)
        return normalized
    if dimension == "core_constraints":
        constraints = result.get("constraints")
        return {"constraints": constraints if isinstance(constraints, list) else []}
    if dimension == "invariant":
        invariants = result.get("invariants")
        return {"invariants": invariants if isinstance(invariants, list) else []}
    return dict(result)


def _load_generation_batch_summary(artifact_dir: Path, *, expected_problem_id: str | None = None) -> dict[str, Any]:
    batch_files = sorted(artifact_dir.glob("batch_*.json"))
    if not batch_files:
        raise WorkflowError(f"生成题面阶段未产出 batch summary：{artifact_dir}")
    target = batch_files[-1]
    if expected_problem_id:
        for candidate in reversed(batch_files):
            try:
                candidate_payload = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            items = candidate_payload.get("items", []) if isinstance(candidate_payload, dict) else []
            if any(isinstance(item, dict) and item.get("problem_id") == expected_problem_id for item in items):
                target = candidate
                payload = candidate_payload
                break
        else:
            raise WorkflowError(f"生成题面 batch summary 中找不到题目：{expected_problem_id}")
        if not isinstance(payload, dict):
            raise WorkflowError(f"batch summary 顶层必须是对象：{target}")
        return payload
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WorkflowError(f"batch summary 顶层必须是对象：{target}")
    return payload


def _apply_generation_results(batch_summary: dict[str, Any], problem_map: dict[str, dict[str, Any]]) -> None:
    items = batch_summary.get("items", [])
    if not isinstance(items, list):
        raise WorkflowError("生成题面 batch summary 缺少 items 数组。")

    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        problem_id = str(item.get("problem_id", "")).strip()
        if problem_id not in problem_map:
            continue
        seen.add(problem_id)
        entry = problem_map[problem_id]
        entry["generation"] = {
            "batch_status": item.get("status", ""),
            "error_reason": item.get("error_reason", ""),
        }
        record = item.get("record")
        if item.get("status") != "completed":
            entry["status"] = "generation_failed"
            continue
        if not isinstance(record, dict) or not record:
            entry["status"] = "generation_failed"
            entry["generation"]["error_reason"] = "生成题面 batch item 缺少 record。"
            continue
        entry["generation"].update(_build_generation_entry(record))
        entry["status"] = "generated"

    for problem_id, entry in problem_map.items():
        if entry.get("status") == "ready_for_generation" and problem_id not in seen:
            entry["status"] = "generation_failed"
            entry["generation"] = {"error_reason": "生成题面 batch summary 中缺少该题记录。"}


def _build_generation_entry(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "generated",
        "artifact_path": str(record.get("artifact_path", "")),
        "markdown_path": str(record.get("markdown_path", "")),
        "quality_report_json_path": str(record.get("quality_report_json_path", "")),
        "quality_report_md_path": str(record.get("quality_report_md_path", "")),
        "iteration_summary_path": str(record.get("iteration_summary_path", "")),
        "generated_status": str(record.get("generated_status", "")),
        "final_round_index": record.get("final_round_index"),
    }


def _run_verification_for_single_problem(
    *,
    config: WorkflowConfig,
    runner: CommandRunner,
    paths: dict[str, Path],
    summary: dict[str, Any],
    problem: dict[str, Any],
    order: int,
    progress: Callable[[str], None],
) -> None:
    generation = problem.get("generation", {})
    if not isinstance(generation, dict):
        problem["status"] = "generation_failed"
        problem["generation"] = {"status": "generation_failed", "error_reason": "generation 必须是对象。"}
        return

    problem_id = str(problem["problem_id"])
    artifact_path = Path(str(generation["artifact_path"]))
    output_path = _verification_output_path(paths["verification"], problem_id, artifact_path)
    progress(f"[stage 5/5] 验证输入 artifact={artifact_path}")
    progress(f"[stage 5/5] 验证输出={output_path}")
    command = [
        config.python_executable,
        str(VERIFICATION_RUNNER_SCRIPT),
        "--artifact",
        str(artifact_path),
        "--output",
        str(output_path),
    ]
    result = runner(
        command,
        cwd=PROJECT_ROOT,
        log_path=paths["logs"]
        / f"04_verify_{order:03d}_{_safe_path_part(problem_id)}_{_safe_path_part(artifact_path.stem)}.log",
        env=_stage_env(config, paths, problem_id=problem_id, stage="verification"),
        timeout_seconds=None,
    )
    stage_name = f"verification:{problem_id}:{artifact_path.stem}"
    _append_stage(summary, stage_name, result)
    generation["verification_result_path"] = str(output_path)
    generation["verification_log_path"] = result.log_path
    if result.ok:
        generation["status"] = "verified"
        problem["status"] = "verified"
        progress("[stage 5/5] 验证完成；结果=verified。")
    else:
        generation["status"] = "verification_failed"
        generation["verification_error"] = "验证阶段失败或超时，详见日志。"
        problem["status"] = "verification_failed"
        if result.timed_out:
            progress("[stage 5/5] 验证超时，已记为 verification_failed。")
        else:
            progress("[stage 5/5] 验证失败，已记为 verification_failed。")


def _run_verification_for_quality_passed_generations(
    *,
    config: WorkflowConfig,
    runner: CommandRunner,
    paths: dict[str, Path],
    summary: dict[str, Any],
    problem_map: dict[str, dict[str, Any]],
    progress: Callable[[str], None],
) -> None:
    for problem in summary["problems"]:
        if problem.get("status") != "generated":
            continue
        generation = problem.get("generation", {})
        if not isinstance(generation, dict):
            problem["status"] = "generation_failed"
            problem["generation"] = {"status": "generation_failed", "error_reason": "generation 必须是对象。"}
            continue

        gate = _quality_gate_result(generation)
        generation["quality_gate"] = gate
        if not gate["passed"]:
            progress(f"[workflow] {problem['problem_id']} 未通过质量门槛，跳过验证。")
            generation["status"] = "quality_gate_failed"
            problem["status"] = "quality_gate_failed"
            continue

        artifact_path = Path(generation["artifact_path"])
        output_path = _verification_output_path(paths["verification"], problem["problem_id"], artifact_path)
        progress(
            f"[workflow] {problem['problem_id']} 通过质量门槛，开始验证：{artifact_path.name}，"
            f"输出={output_path.name}。"
        )
        command = [
            config.python_executable,
            str(VERIFICATION_RUNNER_SCRIPT),
            "--artifact",
            str(artifact_path),
            "--output",
            str(output_path),
        ]
        result = runner(
            command,
            cwd=PROJECT_ROOT,
            log_path=paths["logs"]
            / f"04_verify_{_safe_path_part(problem['problem_id'])}_{_safe_path_part(artifact_path.stem)}.log",
            env=config.runtime_env(),
            timeout_seconds=None,
        )
        stage_name = f"verification:{problem['problem_id']}:{artifact_path.stem}"
        _append_stage(summary, stage_name, result)
        generation["verification_result_path"] = str(output_path)
        generation["verification_log_path"] = result.log_path
        if result.ok:
            generation["status"] = "verified"
            problem["status"] = "verified"
            progress(f"[workflow] {problem['problem_id']} 验证完成，结果=verified。")
        else:
            generation["status"] = "verification_failed"
            generation["verification_error"] = "验证阶段失败或超时，详见日志。"
            problem["status"] = "verification_failed"
            if result.timed_out:
                progress(f"[workflow] {problem['problem_id']} 验证超时，已记为失败。")
            else:
                progress(f"[workflow] {problem['problem_id']} 验证失败，已记为失败。")


def _quality_gate_result(generation: dict[str, Any]) -> dict[str, Any]:
    generated_status = str(generation.get("generated_status", "") or "").strip()
    if generated_status and generated_status != "ok":
        return {
            "passed": False,
            "reason": f"生成状态为 {generated_status}，未进入质量评价。",
            "generated_status": generated_status,
        }
    quality_path_text = str(generation.get("quality_report_json_path", "")).strip()
    iteration_summary_path_text = str(generation.get("iteration_summary_path", "")).strip()
    if not quality_path_text:
        return {"passed": False, "reason": "缺少质量报告路径。"}
    if not iteration_summary_path_text:
        return {"passed": False, "reason": "缺少迭代摘要路径。"}

    quality_path = Path(quality_path_text)
    iteration_summary_path = Path(iteration_summary_path_text)
    if not quality_path.exists():
        return {"passed": False, "reason": f"缺少质量报告：{quality_path}"}
    if not iteration_summary_path.exists():
        return {"passed": False, "reason": f"缺少迭代摘要：{iteration_summary_path}"}

    quality_report = json.loads(quality_path.read_text(encoding="utf-8"))
    iteration_summary = json.loads(iteration_summary_path.read_text(encoding="utf-8"))
    overall = quality_report.get("overall", {}) if isinstance(quality_report, dict) else {}
    quality_status = str(overall.get("status", ""))
    generated_status = str(overall.get("generated_status", generation.get("generated_status", "")))
    stop_reason = str(iteration_summary.get("stop_reason", ""))
    passed = (
        generated_status == "ok"
        and quality_status == "pass"
        and stop_reason == "pass"
    )
    return {
        "passed": passed,
        "quality_status": quality_status,
        "generated_status": generated_status,
        "stop_reason": stop_reason,
        "reason": "" if passed else "质量门槛未通过。",
    }


def _verification_output_path(verification_root: Path, problem_id: str, artifact_path: Path) -> Path:
    problem_dir = verification_root / _safe_path_part(problem_id)
    problem_dir.mkdir(parents=True, exist_ok=True)
    return problem_dir / f"{artifact_path.stem}_verified_artifacts.json"


def _derive_overall_status(problems: list[dict[str, Any]]) -> str:
    if problems and all(problem.get("status") == "verified" for problem in problems):
        return "completed"
    return "completed_with_failures"


def _finalize_summary(summary_path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
    summary["counts"] = _build_counts(summary.get("problems", []))
    _write_summary(summary_path, summary)
    return summary


def _build_counts(problems: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {"total": len(problems)}
    for problem in problems:
        status = str(problem.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
        generation = problem.get("generation", {})
        if isinstance(generation, dict) and generation.get("status"):
            generation_status = "generation_" + str(generation.get("status", "unknown"))
            counts[generation_status] = counts.get(generation_status, 0) + 1
    return counts


def _emit_final_progress(
    progress: Callable[[str], None],
    summary: dict[str, Any],
    summary_path: Path,
    llm_trace_path: Path,
) -> None:
    counts = _build_counts(summary.get("problems", []))
    skipped = sum(1 for problem in summary.get("problems", []) if problem.get("skipped_this_run"))
    processed = sum(1 for problem in summary.get("problems", []) if problem.get("processed_this_run"))
    failed_problem_ids = [
        str(problem.get("problem_id", ""))
        for problem in summary.get("problems", [])
        if problem.get("status") not in {"verified"}
    ]
    progress("=" * 80)
    progress("[workflow] 运行结束")
    progress(f"[workflow] status={summary.get('status')}")
    progress(
        f"[workflow] total={counts.get('total', 0)}；skipped_verified={skipped}；processed_this_run={processed}"
    )
    progress(
        "[workflow] 状态计数="
        + "，".join(f"{key}={value}" for key, value in sorted(counts.items()) if key != "total")
    )
    if failed_problem_ids:
        progress(f"[workflow] 未验证题目={', '.join(failed_problem_ids)}")
    progress(f"[workflow] summary={summary_path}")
    progress(f"[workflow] LLM 详细调用日志={llm_trace_path}")


def _write_summary(summary_path: Path, summary: dict[str, Any]) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def _stage_env(
    config: WorkflowConfig,
    paths: dict[str, Path],
    *,
    problem_id: str,
    stage: str,
) -> dict[str, str]:
    env = config.runtime_env()
    env.update(
        {
            WORKFLOW_LLM_TRACE_PATH: str(paths["llm_trace"]),
            WORKFLOW_CURRENT_PROBLEM_ID: problem_id,
            WORKFLOW_CURRENT_STAGE: stage,
            WORKFLOW_RUN_ID: str(paths["run_dir"].name),
        }
    )
    return env


def _safe_path_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_." else "_" for char in value)
    return cleaned or "unknown_problem"


def _format_command(command: list[str]) -> str:
    return " ".join(str(part) for part in command)


def _ensure_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_config_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _reject_removed_workflow_keys(values: dict[str, str], *, source: str) -> None:
    removed = [key for key in ("THEME", "VARIANTS") if key in values]
    if removed:
        names = "、".join(removed)
        raise RuntimeConfigError(
            f"{source} 配置 {names} 已移除：主题由生成模块内部随机选择，每题固定生成 1 个结果。"
        )


def _optional_text(values: dict[str, str], key: str) -> str | None:
    value = values.get(key, "").strip()
    return value or None


def _require_text(values: dict[str, str], key: str, *, source: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise RuntimeConfigError(f"{source} 缺少必要配置 {key}。")
    return value


def _read_int(values: dict[str, str], key: str, default: int, *, source: str) -> int:
    raw = values.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeConfigError(f"{source} 配置 {key} 必须是整数。") from exc


def _read_positive_int(values: dict[str, str], key: str, default: int, *, source: str) -> int:
    value = _read_int(values, key, default, source=source)
    if value <= 0:
        raise RuntimeConfigError(f"{source} 配置 {key} 必须大于 0。")
    return value


def _read_positive_float(values: dict[str, str], key: str, default: float, *, source: str) -> float:
    value = _read_float(values, key, default, source=source)
    if value <= 0:
        raise RuntimeConfigError(f"{source} 配置 {key} 必须大于 0。")
    return value


def _read_float(values: dict[str, str], key: str, default: float, *, source: str) -> float:
    raw = values.get(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeConfigError(f"{source} 配置 {key} 必须是数字。") from exc
