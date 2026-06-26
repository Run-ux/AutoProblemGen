from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import VERIFICATION_DIR
from .utils import output_matches, safe_name, sha256_text

if str(VERIFICATION_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFICATION_DIR))

from local_execution import EXECUTION_ERROR, EXECUTION_MEMORY_LIMIT, EXECUTION_OK, EXECUTION_TIMEOUT  # noqa: E402
from local_execution import _read_process_memory_mb  # noqa: E402


PYTHON_LANGUAGE_RE = r"Python 3|PyPy 3"
CPP_COMPILE_TIMEOUT_SECONDS = 20.0
CPP_COMPILE_MEMORY_LIMIT_MB = 1024


@dataclass
class ScriptResult:
    status: str
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    duration_seconds: float = 0.0
    timeout_seconds: float = 0.0
    memory_limit_mb: int = 0
    peak_memory_mb: float | None = None
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreparedSubmission:
    command: list[str] | None
    preparation_result: ScriptResult | None = None


def _kill_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        process.kill()
    except OSError:
        pass


def _monitor_memory(
    process: subprocess.Popen[str],
    *,
    memory_limit_mb: int,
    killed_by_memory: dict[str, bool],
    peak_memory: dict[str, float | None],
) -> None:
    while process.poll() is None:
        memory_mb = _read_process_memory_mb(process.pid)
        if memory_mb is not None:
            current_peak = peak_memory.get("value")
            if current_peak is None or memory_mb > current_peak:
                peak_memory["value"] = memory_mb
            if memory_mb > memory_limit_mb:
                killed_by_memory["value"] = True
                _kill_process(process)
                return
        time.sleep(0.02)


def _python_command(code: str) -> list[str]:
    python_args = [sys.executable, "-c", code]
    if sys.version_info >= (3, 11):
        python_args = [sys.executable, "-P", "-c", code]
    return python_args


def _run_process(
    command: list[str],
    input_string: str,
    *,
    timeout_seconds: float,
    memory_limit_mb: int,
    cwd: Path,
) -> ScriptResult:
    start = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd),
        )
    except OSError as exc:
        return ScriptResult(
            status=EXECUTION_ERROR,
            duration_seconds=time.monotonic() - start,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            error_message=str(exc),
        )
    killed_by_memory = {"value": False}
    peak_memory: dict[str, float | None] = {"value": None}
    monitor = threading.Thread(
        target=_monitor_memory,
        kwargs={
            "process": process,
            "memory_limit_mb": memory_limit_mb,
            "killed_by_memory": killed_by_memory,
            "peak_memory": peak_memory,
        },
        daemon=True,
    )
    monitor.start()

    communication: dict[str, Any] = {"stdout": "", "stderr": "", "error": None}

    def communicate() -> None:
        try:
            stdout, stderr = process.communicate(input_string)
            communication["stdout"] = stdout
            communication["stderr"] = stderr
        except BaseException as exc:  # noqa: BLE001 - 子线程异常需要带回主线程归类。
            communication["error"] = exc

    # communicate(input) 在 Windows 上可能卡在 stdin 管道写入阶段；
    # 主线程独立执行墙钟超时，确保低效提交不会无限挂住实验分片。
    communication_thread = threading.Thread(target=communicate, daemon=True)
    communication_thread.start()
    communication_thread.join(max(0.0, timeout_seconds))
    timed_out = communication_thread.is_alive()
    if timed_out:
        _kill_process(process)
        communication_thread.join(5.0)

    stdout = str(communication["stdout"])
    stderr = str(communication["stderr"])
    duration = time.monotonic() - start
    if timed_out:
        return ScriptResult(
            status=EXECUTION_TIMEOUT,
            stdout=stdout,
            stderr=stderr,
            returncode=process.returncode,
            duration_seconds=duration,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            peak_memory_mb=peak_memory["value"],
            error_message=f"执行超过 {timeout_seconds} 秒。",
        )
    if killed_by_memory["value"]:
        return ScriptResult(
            status=EXECUTION_MEMORY_LIMIT,
            stdout=stdout,
            stderr=stderr,
            returncode=process.returncode,
            duration_seconds=duration,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            peak_memory_mb=peak_memory["value"],
            error_message=f"执行内存超过 {memory_limit_mb} MB。",
        )
    if communication["error"] is not None:
        return ScriptResult(
            status=EXECUTION_ERROR,
            stdout=stdout,
            stderr=stderr,
            returncode=process.returncode,
            duration_seconds=duration,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            peak_memory_mb=peak_memory["value"],
            error_message=str(communication["error"]),
        )
    if process.returncode != 0:
        return ScriptResult(
            status=EXECUTION_ERROR,
            stdout=stdout,
            stderr=stderr,
            returncode=process.returncode,
            duration_seconds=duration,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            peak_memory_mb=peak_memory["value"],
            error_message=stderr[-2000:],
        )
    return ScriptResult(
        status=EXECUTION_OK,
        stdout=stdout,
        stderr=stderr,
        returncode=process.returncode,
        duration_seconds=duration,
        timeout_seconds=timeout_seconds,
        memory_limit_mb=memory_limit_mb,
        peak_memory_mb=peak_memory["value"],
    )


def run_submission_script(
    code: str,
    input_string: str,
    *,
    timeout_seconds: float,
    memory_limit_mb: int,
) -> ScriptResult:
    return _run_process(
        _python_command(code),
        input_string,
        timeout_seconds=timeout_seconds,
        memory_limit_mb=memory_limit_mb,
        cwd=Path.cwd(),
    )


def _language_matches(language: str, pattern: str) -> bool:
    return re.search(pattern, language, flags=re.IGNORECASE) is not None


def _cpp_standards(language: str) -> list[str]:
    if _language_matches(language, r"C\+\+14"):
        return ["gnu++14"]
    if _language_matches(language, r"C\+\+17"):
        return ["gnu++17", "gnu++14"]
    return []


def _cache_key(submission: dict[str, Any]) -> str:
    return ":".join(
        [
            str(submission["id"]),
            safe_name(str(submission["language"])),
            sha256_text(str(submission["source"])),
        ]
    )


def _compile_cpp_submission(
    *,
    submission: dict[str, Any],
    standards: list[str],
    submission_cache_dir: Path,
) -> PreparedSubmission:
    submission_cache_dir.mkdir(parents=True, exist_ok=True)
    source_hash = sha256_text(str(submission["source"]))[:16]
    base_name = f"submission_{safe_name(str(submission['id']))}_{source_hash}"
    source_path = submission_cache_dir / f"{base_name}.cpp"
    executable_suffix = ".exe" if sys.platform.startswith("win") else ""
    executable_path = submission_cache_dir / f"{base_name}{executable_suffix}"
    source_path.write_text(str(submission["source"]), encoding="utf-8")
    if executable_path.is_file():
        return PreparedSubmission(command=[str(executable_path)])

    failed_results: list[tuple[str, ScriptResult]] = []
    for standard in standards:
        compile_result = _run_process(
            ["g++", f"-std={standard}", "-O2", str(source_path), "-o", str(executable_path)],
            "",
            timeout_seconds=CPP_COMPILE_TIMEOUT_SECONDS,
            memory_limit_mb=CPP_COMPILE_MEMORY_LIMIT_MB,
            cwd=submission_cache_dir,
        )
        if compile_result.status == EXECUTION_OK:
            return PreparedSubmission(command=[str(executable_path)])
        failed_results.append((standard, compile_result))

    last_standard, last_result = failed_results[-1]
    last_result.stderr = "\n\n".join(
        f"[{standard}]\n{result.stderr[-2000:] or result.error_message}" for standard, result in failed_results
    )
    last_result.error_message = f"C++ 编译失败，最后一次标准为 {last_standard}。"
    return PreparedSubmission(command=None, preparation_result=last_result)


def _prepare_submission(
    *,
    submission: dict[str, Any],
    submission_cache_dir: Path | None,
) -> PreparedSubmission:
    language = str(submission["language"])
    source = str(submission["source"])
    if _language_matches(language, PYTHON_LANGUAGE_RE):
        return PreparedSubmission(command=_python_command(source))

    cpp_standards = _cpp_standards(language)
    if not cpp_standards:
        return PreparedSubmission(
            command=None,
            preparation_result=ScriptResult(
                status=EXECUTION_ERROR,
                error_message=f"不支持的提交语言：{language}",
            ),
        )
    if submission_cache_dir is None:
        return PreparedSubmission(
            command=None,
            preparation_result=ScriptResult(
                status=EXECUTION_ERROR,
                error_message="C++ 提交需要编译缓存目录。",
            ),
        )
    return _compile_cpp_submission(
        submission=submission,
        standards=cpp_standards,
        submission_cache_dir=submission_cache_dir,
    )


def evaluate_submission_on_cases(
    *,
    submission: dict[str, Any],
    suite_name: str,
    cases: list[dict[str, Any]],
    timeout_seconds: float,
    memory_limit_mb: int,
    submission_cache_dir: Path | None = None,
    prepared_submissions: dict[str, PreparedSubmission] | None = None,
) -> dict[str, Any]:
    cache_key = _cache_key(submission)
    if prepared_submissions is None:
        prepared_submission = _prepare_submission(submission=submission, submission_cache_dir=submission_cache_dir)
    else:
        if cache_key not in prepared_submissions:
            prepared_submissions[cache_key] = _prepare_submission(
                submission=submission,
                submission_cache_dir=submission_cache_dir,
            )
        prepared_submission = prepared_submissions[cache_key]

    case_results: list[dict[str, Any]] = []
    accepted = True
    first_failure: dict[str, Any] | None = None
    for case in cases:
        if prepared_submission.command is None:
            result = prepared_submission.preparation_result or ScriptResult(
                status=EXECUTION_ERROR,
                error_message="提交准备失败。",
            )
        else:
            result = _run_process(
                prepared_submission.command,
                str(case["input"]),
                timeout_seconds=timeout_seconds,
                memory_limit_mb=memory_limit_mb,
                cwd=Path.cwd(),
            )
        if result.status != EXECUTION_OK:
            passed = False
            classification = result.status
        else:
            passed = output_matches(result.stdout, str(case["output"]))
            classification = "accepted" if passed else "wrong_answer"
        record = {
            "suite": suite_name,
            "submission_id": int(submission["id"]),
            "submission_type": str(submission["type"]),
            "language": str(submission["language"]),
            "case_id": str(case["case_id"]),
            "case_source": str(case.get("source", "")),
            "passed": passed,
            "classification": classification,
            "input_sha256": sha256_text(str(case["input"])),
            "expected_output_sha256": sha256_text(str(case["output"])),
            "actual_output_sha256": sha256_text(result.stdout) if result.status == EXECUTION_OK else "",
            "execution": result.to_dict(),
        }
        case_results.append(record)
        if not passed and first_failure is None:
            first_failure = record
            accepted = False
            break
    semantic_eligible = first_failure is None or first_failure["classification"] == "wrong_answer"
    return {
        "suite": suite_name,
        "submission_id": int(submission["id"]),
        "submission_type": str(submission["type"]),
        "language": str(submission["language"]),
        "accepted": accepted,
        "rejected": not accepted,
        "semantic_eligible": semantic_eligible,
        "first_failure_kind": "" if first_failure is None else first_failure["classification"],
        "first_kill_source": "" if first_failure is None else first_failure["case_source"],
        "checked_case_count": len(case_results),
        "case_results": case_results,
    }
