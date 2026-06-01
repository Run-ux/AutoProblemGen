from __future__ import annotations

import json
from typing import Any, Callable

try:  # 兼容包内导入与当前目录直接运行两种方式。
    from .llm_client import ChatLLMClient
    from .llm_json import LLMResponseError, parse_json_object
except ImportError:  # pragma: no cover - 当前测试以顶层模块方式导入。
    from llm_client import ChatLLMClient
    from llm_json import LLMResponseError, parse_json_object


Validator = Callable[[dict[str, Any]], dict[str, Any]]

DEFAULT_CONTRACT_RETRY_ROUNDS = 2
DEFAULT_RAW_RESPONSE_LIMIT = 4000


def call_prompt_with_contract_retry(
    client: ChatLLMClient,
    *,
    task_name: str,
    system_prompt: str,
    user_prompt: str,
    validator: Validator,
    max_contract_retries: int = DEFAULT_CONTRACT_RETRY_ROUNDS,
    raw_response_limit: int = DEFAULT_RAW_RESPONSE_LIMIT,
) -> dict[str, Any]:
    """调用 JSON prompt，并仅对 JSON/字段合同错误做定向重试。"""

    original_user_prompt = user_prompt
    history: list[dict[str, Any]] = []
    total_attempts = max(0, max_contract_retries) + 1

    for attempt in range(1, total_attempts + 1):
        raw_response = client.complete_json(
            task_name=task_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        try:
            parsed = parse_json_object(raw_response, task_name)
            return validator(parsed)
        except LLMResponseError as exc:
            history.append(
                {
                    "attempt": attempt,
                    "error": str(exc),
                    "raw_response": _truncate_text(str(raw_response), raw_response_limit),
                }
            )
            if attempt >= total_attempts:
                raise LLMResponseError(
                    _format_contract_failure(
                        task_name=task_name,
                        max_contract_retries=max_contract_retries,
                        history=history,
                    )
                ) from exc
            user_prompt = _build_contract_retry_prompt(
                original_user_prompt=original_user_prompt,
                task_name=task_name,
                history=history,
            )

    raise AssertionError("unreachable")


def _build_contract_retry_prompt(
    *,
    original_user_prompt: str,
    task_name: str,
    history: list[dict[str, Any]],
) -> str:
    history_json = json.dumps(history, ensure_ascii=False, indent=2)
    return (
        f"{original_user_prompt}\n\n"
        "# JSON 合同修复重试\n"
        f"任务 `{task_name}` 上一次返回未通过 JSON 合同校验，请基于同一任务重新输出完整 JSON 对象。\n"
        "必须遵守：\n"
        "- 只输出单个严格合法 JSON 对象，不要输出 Markdown、解释、前后缀或多余文本。\n"
        "- 字段必须完整，字段类型必须与本 prompt 的 JSON 合同一致。\n"
        "- 如果字段包含代码，代码必须放在 JSON 字符串字段中，不要使用 Markdown 代码块。\n"
        "- 重新生成整份 JSON，不要只返回局部字段或差异片段。\n\n"
        "此前失败历史如下，`raw_response` 已截断，仅用于定位合同错误：\n"
        f"{history_json}"
    )


def _format_contract_failure(
    *,
    task_name: str,
    max_contract_retries: int,
    history: list[dict[str, Any]],
) -> str:
    history_json = json.dumps(history, ensure_ascii=False, indent=2)
    return (
        f"{task_name} JSON 合同连续失败，已额外重试 {max(0, max_contract_retries)} 轮。"
        f"失败历史：{history_json}"
    )


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    marker = "\n...<truncated>...\n"
    if limit <= len(marker):
        return value[:limit]
    keep_each_side = (limit - len(marker)) // 2
    return value[:keep_each_side] + marker + value[-keep_each_side:]
