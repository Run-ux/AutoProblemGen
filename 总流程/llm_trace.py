from __future__ import annotations

import itertools
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


WORKFLOW_LLM_TRACE_PATH = "WORKFLOW_LLM_TRACE_PATH"
WORKFLOW_CURRENT_PROBLEM_ID = "WORKFLOW_CURRENT_PROBLEM_ID"
WORKFLOW_CURRENT_STAGE = "WORKFLOW_CURRENT_STAGE"
WORKFLOW_RUN_ID = "WORKFLOW_RUN_ID"

_COUNTER = itertools.count(1)


def trace_enabled() -> bool:
    return bool(os.environ.get(WORKFLOW_LLM_TRACE_PATH, "").strip())


def new_call_id() -> str:
    """生成跨子进程可读的调用编号。"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{timestamp}-{os.getpid()}-{next(_COUNTER):04d}"


def start_call(
    *,
    call_id: str,
    task_name: str,
    model: str,
    endpoint: str,
    temperature: float | None,
    timeout_seconds: float | int | None,
    attempt: int,
    max_retries: int,
    system_prompt: str = "",
    user_prompt: str = "",
    payload: dict[str, Any] | None = None,
) -> float:
    started = time.perf_counter()
    if not trace_enabled():
        return started

    payload_bytes = len(json.dumps(payload or {}, ensure_ascii=False).encode("utf-8"))
    event = _base_event(call_id=call_id, event="start", task_name=task_name)
    event.update(
        {
            "model": model,
            "endpoint": endpoint,
            "temperature": temperature,
            "timeout_seconds": timeout_seconds,
            "attempt": attempt,
            "max_retries": max_retries,
            "system_chars": len(system_prompt),
            "user_chars": len(user_prompt),
            "payload_bytes": payload_bytes,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "payload": _scrub(payload or {}),
        }
    )
    _write_event(event)
    return started


def retry_call(
    *,
    call_id: str,
    task_name: str,
    attempt: int,
    max_retries: int,
    elapsed_seconds: float,
    error: BaseException | str,
    retry_delay_seconds: float,
) -> None:
    if not trace_enabled():
        return
    error_type, error_text = _error_parts(error)
    event = _base_event(call_id=call_id, event="retry", task_name=task_name)
    event.update(
        {
            "attempt": attempt,
            "max_retries": max_retries,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "error_type": error_type,
            "error": error_text,
            "retry_delay_seconds": retry_delay_seconds,
        }
    )
    _write_event(event)
    _emit(
        [
            f"[llm call {call_id}] 第 {attempt}/{max_retries} 次未成功",
            (
                f"[llm] 错误={error_type}；耗时={elapsed_seconds:.2f}s；"
                f"{retry_delay_seconds:.1f}s 后重试"
            ),
        ]
    )


def finish_call(
    *,
    call_id: str,
    task_name: str,
    elapsed_seconds: float,
    http_status: int | str | None = None,
    response_text: str = "",
    raw_response: Any = None,
    usage: dict[str, Any] | None = None,
    json_parse: str = "success",
    summary: dict[str, Any] | None = None,
) -> None:
    if not trace_enabled():
        return
    event = _base_event(call_id=call_id, event="success", task_name=task_name)
    event.update(
        {
            "elapsed_seconds": round(elapsed_seconds, 3),
            "http_status": http_status,
            "response_chars": len(response_text),
            "usage": usage or {},
            "json_parse": json_parse,
            "summary": summary or summarize_value(raw_response),
            "response_text": response_text,
            "raw_response": _scrub(raw_response),
        }
    )
    _write_event(event)


def fail_call(
    *,
    call_id: str,
    task_name: str,
    attempt: int,
    max_retries: int,
    elapsed_seconds: float,
    error: BaseException | str,
) -> None:
    if not trace_enabled():
        return
    error_type, error_text = _error_parts(error)
    event = _base_event(call_id=call_id, event="failed", task_name=task_name)
    event.update(
        {
            "attempt": attempt,
            "max_retries": max_retries,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "error_type": error_type,
            "error": error_text,
        }
    )
    _write_event(event)
    _emit(
        [
            f"[llm call {call_id}] 调用失败",
            (
                f"[llm] 错误={error_type}；耗时={elapsed_seconds:.2f}s；"
                f"完整详情={_trace_path_text()}"
            ),
        ]
    )


def summarize_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {"keys": list(value.keys())[:12]}
        for key in ("status", "verdict", "generated_status", "stop_reason", "applied_rule"):
            if key in value:
                result[key] = value.get(key)
        if isinstance(value.get("overall"), dict):
            overall = value["overall"]
            result["overall_status"] = overall.get("status")
            result["quality_score"] = overall.get("quality_score")
            result["generated_status"] = overall.get("generated_status")
        if isinstance(value.get("constraints"), list):
            result["constraints_count"] = len(value["constraints"])
        if isinstance(value.get("invariants"), list):
            result["invariants_count"] = len(value["invariants"])
        if isinstance(value.get("scores"), dict):
            result["score_dimensions"] = list(value["scores"].keys())
        if isinstance(value.get("data"), list):
            result["data_count"] = len(value["data"])
            first = value["data"][0] if value["data"] else {}
            if isinstance(first, dict) and isinstance(first.get("embedding"), list):
                result["embedding_dimensions"] = len(first["embedding"])
        return result
    if isinstance(value, list):
        return {"type": "list", "count": len(value)}
    if value is None:
        return {"type": "none"}
    return {"type": type(value).__name__}


def _base_event(*, call_id: str, event: str, task_name: str) -> dict[str, Any]:
    return {
        "event": event,
        "call_id": call_id,
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "run_id": os.environ.get(WORKFLOW_RUN_ID, ""),
        "stage": os.environ.get(WORKFLOW_CURRENT_STAGE, ""),
        "task_name": task_name,
        "problem_id": os.environ.get(WORKFLOW_CURRENT_PROBLEM_ID, ""),
    }


def _write_event(event: dict[str, Any]) -> None:
    trace_path_text = os.environ.get(WORKFLOW_LLM_TRACE_PATH, "").strip()
    if not trace_path_text:
        return
    trace_path = Path(trace_path_text)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def _emit(lines: list[str]) -> None:
    for line in lines:
        print(line, flush=True)


def _trace_path_text() -> str:
    return os.environ.get(WORKFLOW_LLM_TRACE_PATH, "").strip()


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in {"api_key", "authorization"} or "api_key" in key_text:
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = _scrub(item)
        return cleaned
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _error_parts(error: BaseException | str) -> tuple[str, str]:
    if isinstance(error, BaseException):
        return type(error).__name__, str(error)
    return "Error", str(error)


def _format_summary(summary: dict[str, Any]) -> str:
    if not summary:
        return "无"
    parts = []
    for key, value in summary.items():
        if isinstance(value, list):
            value_text = ",".join(str(item) for item in value[:8])
        else:
            value_text = str(value)
        parts.append(f"{key}={value_text}")
    return "；".join(parts)


def _format_usage(usage: dict[str, Any]) -> str:
    if not usage:
        return ""
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    total = usage.get("total_tokens")
    return f"；usage.prompt={prompt}；usage.completion={completion}；usage.total={total}"


def usage_from_openai_response(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    result: dict[str, Any] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if value is not None:
            result[key] = value
    return result
