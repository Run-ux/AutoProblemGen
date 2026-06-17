from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import VERIFICATION_DIR
from .utils import output_matches, sha256_text

if str(VERIFICATION_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFICATION_DIR))

from local_execution import EXECUTION_ERROR, EXECUTION_MEMORY_LIMIT, EXECUTION_OK, EXECUTION_TIMEOUT  # noqa: E402
from local_execution import _read_process_memory_mb  # noqa: E402


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
                process.kill()
                return
        time.sleep(0.02)


def run_submission_script(
    code: str,
    input_string: str,
    *,
    timeout_seconds: float,
    memory_limit_mb: int,
) -> ScriptResult:
    python_args = [sys.executable, "-c", code]
    if sys.version_info >= (3, 11):
        python_args = [sys.executable, "-P", "-c", code]
    start = time.monotonic()
    process = subprocess.Popen(
        python_args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(Path.cwd()),
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
    try:
        stdout, stderr = process.communicate(input_string, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        return ScriptResult(
            status=EXECUTION_TIMEOUT,
            stdout=stdout,
            stderr=stderr,
            returncode=process.returncode,
            duration_seconds=time.monotonic() - start,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            peak_memory_mb=peak_memory["value"],
            error_message=f"执行超过 {timeout_seconds} 秒。",
        )
    duration = time.monotonic() - start
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


def evaluate_submission_on_cases(
    *,
    submission: dict[str, Any],
    suite_name: str,
    cases: list[dict[str, Any]],
    timeout_seconds: float,
    memory_limit_mb: int,
) -> dict[str, Any]:
    case_results: list[dict[str, Any]] = []
    accepted = True
    first_failure: dict[str, Any] | None = None
    for case in cases:
        result = run_submission_script(
            str(submission["source"]),
            str(case["input"]),
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
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
