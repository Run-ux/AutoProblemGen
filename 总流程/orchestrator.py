from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = MODULE_ROOT / "output"

TUPLE_EXTRACT_DIR = PROJECT_ROOT / "四元组抽取"
PROBLEM_GENERATION_DIR = PROJECT_ROOT / "生成题面"

TUPLE_EXTRACT_SCRIPT = TUPLE_EXTRACT_DIR / "extract.py"
TUPLE_NORMALIZE_SCRIPT = TUPLE_EXTRACT_DIR / "normalize.py"
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
    output_root: Path = DEFAULT_OUTPUT_ROOT
    run_id: str | None = None
    variants: int = 1
    theme: str | None = None
    quality_iterations: int = 3
    quality_full_score_max_iterations: int = 10
    embedding_threshold: float = 0.85
    verification_timeout_seconds: float = 3600.0
    python_executable: str = sys.executable


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
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        ...


def default_command_runner(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    timeout_seconds: float | None = None,
) -> CommandResult:
    """执行外部阶段命令，并把完整 stdout/stderr 保存到总流程日志。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        result = CommandResult(
            command=list(command),
            cwd=str(cwd),
            log_path=str(log_path),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        result = CommandResult(
            command=list(command),
            cwd=str(cwd),
            log_path=str(log_path),
            returncode=-1,
            stdout=_ensure_text(exc.stdout),
            stderr=_ensure_text(exc.stderr) or f"命令超时：{timeout_seconds} 秒",
            timed_out=True,
        )

    log_text = [
        "# command",
        _format_command(command),
        "",
        "# cwd",
        str(cwd),
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
    run_id = config.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_root / run_id
    paths = _build_paths(run_dir)
    _ensure_dirs(paths)

    problems = _load_input_problem_entries(input_path)
    summary: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": "",
        "config": _config_summary(config, input_path=input_path, output_root=output_root, run_id=run_id),
        "paths": {key: str(value) for key, value in paths.items()},
        "stages": [],
        "problems": [
            {
                "problem_id": item["problem_id"],
                "input_path": item["input_path"],
                "status": "pending",
                "tuple": {},
                "generation": {},
                "variants": [],
            }
            for item in problems
        ],
        "counts": {},
    }
    problem_map = {item["problem_id"]: item for item in summary["problems"]}
    summary_path = paths["summary"]

    try:
        progress(f"[workflow] run_id={run_id}，开始四元组抽取。")
        _run_extract_stage(config, runner, paths, input_path, summary)
        _write_summary(summary_path, summary)

        tuple_status = _collect_tuple_raw_status(paths["tuple_raw"], problem_map)
        eligible_after_extract = [
            problem_id for problem_id, status in tuple_status.items() if status["success"]
        ]
        for problem_id, status in tuple_status.items():
            entry = problem_map[problem_id]
            entry["tuple"] = status
            if not status["success"]:
                entry["status"] = "skipped_before_generation"

        progress(f"[workflow] 抽取完成，四维全成功题目数={len(eligible_after_extract)}。")
        if not eligible_after_extract:
            summary["status"] = "failed"
            summary["error"] = "没有题目通过四维抽取，无法进入归一化和题面生成阶段。"
            return _finalize_summary(summary_path, summary)

        progress("[workflow] 开始四元组归一化。")
        _run_normalize_stage(config, runner, paths, summary)
        _write_summary(summary_path, summary)

        generation_problem_ids = _prepare_generation_source(
            normalized_dir=paths["tuple_normalized"],
            generation_source_dir=paths["generation_source"],
            eligible_problem_ids=eligible_after_extract,
            problem_map=problem_map,
        )
        if not generation_problem_ids:
            summary["status"] = "failed"
            summary["error"] = "没有题目通过抽取与归一化，无法进入题面生成阶段。"
            return _finalize_summary(summary_path, summary)

        progress(f"[workflow] 开始生成题面，题目数={len(generation_problem_ids)}。")
        _run_generation_stage(config, runner, paths, summary)
        _write_summary(summary_path, summary)

        batch_summary = _load_generation_batch_summary(paths["generation_artifacts"])
        _apply_generation_results(batch_summary, problem_map)

        progress("[workflow] 开始执行质量门槛与验证阶段。")
        _run_verification_for_quality_passed_variants(
            config=config,
            runner=runner,
            paths=paths,
            summary=summary,
            problem_map=problem_map,
            progress=progress,
        )
        summary["status"] = _derive_overall_status(summary["problems"])
        return _finalize_summary(summary_path, summary)
    except WorkflowError as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)
        return _finalize_summary(summary_path, summary)
    except Exception as exc:  # 兜底只负责摘要落盘，异常信息仍在 status 中暴露。
        summary["status"] = "failed"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        return _finalize_summary(summary_path, summary)


def _build_paths(run_dir: Path) -> dict[str, Path]:
    return {
        "run_dir": run_dir,
        "tuple_root": run_dir / "tuple",
        "tuple_raw": run_dir / "tuple" / "raw",
        "tuple_normalized": run_dir / "tuple" / "normalized",
        "generation_root": run_dir / "generation",
        "generation_source": run_dir / "generation" / "source",
        "generation_output": run_dir / "generation" / "output",
        "generation_artifacts": run_dir / "generation" / "artifacts",
        "generation_reports": run_dir / "generation" / "reports",
        "verification": run_dir / "verification",
        "logs": run_dir / "logs",
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
    payload = asdict(config)
    payload["input_path"] = str(input_path)
    payload["output_root"] = str(output_root)
    payload["run_id"] = run_id
    return payload


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
        entries.append({"problem_id": problem_id, "input_path": str(path)})
    return entries


def _run_extract_stage(
    config: WorkflowConfig,
    runner: CommandRunner,
    paths: dict[str, Path],
    input_path: Path,
    summary: dict[str, Any],
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
        log_path=paths["logs"] / "01_tuple_extract.log",
    )
    _append_stage(summary, "tuple_extract", result)
    if not result.ok:
        raise WorkflowError("四元组抽取阶段失败，详见日志：" + result.log_path)


def _run_normalize_stage(
    config: WorkflowConfig,
    runner: CommandRunner,
    paths: dict[str, Path],
    summary: dict[str, Any],
) -> None:
    command = [
        config.python_executable,
        str(TUPLE_NORMALIZE_SCRIPT),
        "--input",
        str(paths["tuple_raw"]),
        "--output",
        str(paths["tuple_normalized"]),
        "--embedding-threshold",
        str(config.embedding_threshold),
    ]
    result = runner(
        command,
        cwd=TUPLE_EXTRACT_DIR,
        log_path=paths["logs"] / "02_tuple_normalize.log",
    )
    _append_stage(summary, "tuple_normalize", result)
    if not result.ok:
        raise WorkflowError("四元组归一化阶段失败，详见日志：" + result.log_path)


def _run_generation_stage(
    config: WorkflowConfig,
    runner: CommandRunner,
    paths: dict[str, Path],
    summary: dict[str, Any],
) -> None:
    command = [
        config.python_executable,
        str(PROBLEM_GENERATION_SCRIPT),
        "--mode",
        "single",
        "--source-dir",
        str(paths["generation_source"]),
        "--output-dir",
        str(paths["generation_output"]),
        "--artifact-dir",
        str(paths["generation_artifacts"]),
        "--report-dir",
        str(paths["generation_reports"]),
        "--variants",
        str(config.variants),
        "--quality-iterations",
        str(config.quality_iterations),
        "--quality-full-score-max-iterations",
        str(config.quality_full_score_max_iterations),
    ]
    if config.theme:
        command.extend(["--theme", config.theme])

    result = runner(
        command,
        cwd=PROBLEM_GENERATION_DIR,
        log_path=paths["logs"] / "03_problem_generation.log",
    )
    _append_stage(summary, "problem_generation", result)
    if not result.ok:
        raise WorkflowError("生成题面阶段失败，详见日志：" + result.log_path)


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
    normalized_dir: Path,
    generation_source_dir: Path,
    eligible_problem_ids: list[str],
    problem_map: dict[str, dict[str, Any]],
) -> list[str]:
    generation_source_dir.mkdir(parents=True, exist_ok=True)
    ready: list[str] = []
    for problem_id in eligible_problem_ids:
        source = normalized_dir / f"{problem_id}.json"
        target = generation_source_dir / f"{problem_id}.json"
        entry = problem_map[problem_id]
        if not source.exists():
            entry["status"] = "normalization_failed"
            entry["tuple"]["normalized_path"] = ""
            entry["tuple"]["normalization_error"] = f"缺少归一化结果：{source}"
            continue
        shutil.copy2(source, target)
        entry["status"] = "ready_for_generation"
        entry["tuple"]["normalized_path"] = str(source)
        entry["tuple"]["generation_source_path"] = str(target)
        ready.append(problem_id)
    return ready


def _load_generation_batch_summary(artifact_dir: Path) -> dict[str, Any]:
    batch_files = sorted(artifact_dir.glob("batch_*.json"))
    if not batch_files:
        raise WorkflowError(f"生成题面阶段未产出 batch summary：{artifact_dir}")
    target = batch_files[-1]
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
        variant_records = item.get("variant_records", [])
        if item.get("status") != "completed":
            entry["status"] = "generation_failed"
            continue
        if not isinstance(variant_records, list) or not variant_records:
            entry["status"] = "generation_failed"
            entry["generation"]["error_reason"] = "生成题面 batch item 缺少 variant_records。"
            continue
        entry["variants"] = [_build_variant_entry(record) for record in variant_records if isinstance(record, dict)]
        entry["status"] = "generated"

    for problem_id, entry in problem_map.items():
        if entry.get("status") == "ready_for_generation" and problem_id not in seen:
            entry["status"] = "generation_failed"
            entry["generation"] = {"error_reason": "生成题面 batch summary 中缺少该题记录。"}


def _build_variant_entry(record: dict[str, Any]) -> dict[str, Any]:
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


def _run_verification_for_quality_passed_variants(
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
        problem_verified = True
        any_verified = False
        for variant in problem.get("variants", []):
            gate = _quality_gate_result(variant)
            variant["quality_gate"] = gate
            if not gate["passed"]:
                variant["status"] = "quality_gate_failed"
                problem_verified = False
                continue

            artifact_path = Path(variant["artifact_path"])
            output_path = _verification_output_path(paths["verification"], problem["problem_id"], artifact_path)
            progress(f"[workflow] {problem['problem_id']} 通过质量门槛，开始验证：{artifact_path.name}")
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
                timeout_seconds=config.verification_timeout_seconds,
            )
            stage_name = f"verification:{problem['problem_id']}:{artifact_path.stem}"
            _append_stage(summary, stage_name, result)
            variant["verification_result_path"] = str(output_path)
            variant["verification_log_path"] = result.log_path
            if result.ok:
                variant["status"] = "verified"
                any_verified = True
            else:
                variant["status"] = "verification_failed"
                variant["verification_error"] = "验证阶段失败或超时，详见日志。"
                problem_verified = False

        if any_verified and problem_verified:
            problem["status"] = "verified"
        elif any_verified:
            problem["status"] = "partially_verified"
        else:
            problem["status"] = _first_variant_failure_status(problem.get("variants", []))


def _quality_gate_result(variant: dict[str, Any]) -> dict[str, Any]:
    quality_path_text = str(variant.get("quality_report_json_path", "")).strip()
    iteration_summary_path_text = str(variant.get("iteration_summary_path", "")).strip()
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
    generated_status = str(overall.get("generated_status", variant.get("generated_status", "")))
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


def _first_variant_failure_status(variants: list[dict[str, Any]]) -> str:
    for variant in variants:
        status = str(variant.get("status", ""))
        if status:
            return status
    return "generation_failed"


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
        for variant in problem.get("variants", []):
            variant_status = "variant_" + str(variant.get("status", "unknown"))
            counts[variant_status] = counts.get(variant_status, 0) + 1
    return counts


def _write_summary(summary_path: Path, summary: dict[str, Any]) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


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
