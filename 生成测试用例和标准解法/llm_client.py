from __future__ import annotations

import logging
import json
import sys
import time
from pathlib import Path
from typing import Protocol

try:  # 兼容包内导入与当前目录直接运行两种方式。
    from .llm_config import LLMConfig
except ImportError:  # pragma: no cover - 当前测试以顶层模块方式导入。
    from llm_config import LLMConfig

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / "总流程"
if str(WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_DIR))

from llm_trace import (
    fail_call,
    finish_call,
    new_call_id,
    retry_call,
    start_call,
    summarize_value,
    usage_from_openai_response,
)


logger = logging.getLogger(__name__)


class LLMCallError(RuntimeError):
    """表示 LLM 调用失败或响应结构不可用。"""


class ChatLLMClient(Protocol):
    def complete_json(self, *, task_name: str, system_prompt: str, user_prompt: str) -> str:
        """调用模型并返回原始 JSON 字符串。"""


class OpenAIChatLLMClient:
    """OpenAI 兼容 Chat Completions 客户端。"""

    def __init__(self, config: LLMConfig) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - 需要真实依赖环境覆盖。
            raise LLMCallError("缺少 openai 包，请先安装 requirements.txt 中的依赖。") from exc

        self.config = config
        client_kwargs = {
            "api_key": config.api_key,
            "timeout": config.timeout_seconds,
            # 重试由本模块显式处理，确保每次 attempt 都进入统一 LLM 日志。
            "max_retries": 0,
        }
        if config.base_url:
            client_kwargs["base_url"] = config.base_url
        self._client = OpenAI(**client_kwargs)

    def complete_json(self, *, task_name: str, system_prompt: str, user_prompt: str) -> str:
        logger.info(
            "开始调用 LLM: task=%s model=%s base_url_configured=%s",
            task_name,
            self.config.model,
            bool(self.config.base_url),
        )
        call_id = new_call_id()
        self._ensure_prompt_budget(
            call_id=call_id,
            task_name=task_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        attempts = max(1, self.config.max_retries)
        for attempt in range(1, attempts + 1):
            started = start_call(
                call_id=call_id,
                task_name=task_name,
                model=self.config.model,
                endpoint=str(self.config.base_url or "openai-default"),
                temperature=self.config.temperature,
                timeout_seconds=self.config.timeout_seconds,
                attempt=attempt,
                max_retries=attempts,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                payload=payload,
            )
            try:
                response = self._client.chat.completions.create(
                    model=self.config.model,
                    temperature=self.config.temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )

                choices = getattr(response, "choices", None)
                if not choices:
                    raise LLMCallError(f"LLM 响应缺少 choices: {task_name}")

                content = getattr(choices[0].message, "content", None)
                if not isinstance(content, str) or not content.strip():
                    raise LLMCallError(f"LLM 响应内容为空: {task_name}")

                logger.info("LLM 调用成功: task=%s model=%s", task_name, self.config.model)
                try:
                    parsed = json.loads(content)
                    json_parse = "success"
                except json.JSONDecodeError:
                    parsed = content
                    json_parse = "failed"
                finish_call(
                    call_id=call_id,
                    task_name=task_name,
                    elapsed_seconds=time.perf_counter() - started,
                    http_status="sdk",
                    response_text=content,
                    raw_response=parsed,
                    usage=usage_from_openai_response(response),
                    json_parse=json_parse,
                    summary=summarize_value(parsed),
                )
                return content
            except Exception as exc:
                elapsed = time.perf_counter() - started
                if _is_context_length_error(exc):
                    logger.exception(
                        "LLM 调用失败且不重试: task=%s model=%s reason=context_length",
                        task_name,
                        self.config.model,
                    )
                    fail_call(
                        call_id=call_id,
                        task_name=task_name,
                        attempt=attempt,
                        max_retries=attempts,
                        elapsed_seconds=elapsed,
                        error=exc,
                    )
                    raise LLMCallError(f"LLM 调用失败: {task_name}") from exc
                if attempt < attempts:
                    delay = 1.5 * attempt
                    logger.warning(
                        "LLM 调用第 %d/%d 次失败: task=%s model=%s error=%s",
                        attempt,
                        attempts,
                        task_name,
                        self.config.model,
                        exc,
                    )
                    retry_call(
                        call_id=call_id,
                        task_name=task_name,
                        attempt=attempt,
                        max_retries=attempts,
                        elapsed_seconds=elapsed,
                        error=exc,
                        retry_delay_seconds=delay,
                    )
                    time.sleep(delay)
                    continue

                logger.exception("LLM 调用失败: task=%s model=%s", task_name, self.config.model)
                fail_call(
                    call_id=call_id,
                    task_name=task_name,
                    attempt=attempt,
                    max_retries=attempts,
                    elapsed_seconds=elapsed,
                    error=exc,
                )
                raise LLMCallError(f"LLM 调用失败: {task_name}") from exc

        raise LLMCallError(f"LLM 调用失败: {task_name}")

    def _ensure_prompt_budget(
        self,
        *,
        call_id: str,
        task_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> None:
        prompt_chars = len(system_prompt) + len(user_prompt)
        if prompt_chars <= self.config.max_prompt_chars:
            return
        error = LLMCallError(
            "LLM prompt 超过本地预算："
            f"task={task_name}；prompt_chars={prompt_chars}；"
            f"max_prompt_chars={self.config.max_prompt_chars}"
        )
        fail_call(
            call_id=call_id,
            task_name=task_name,
            attempt=0,
            max_retries=max(1, self.config.max_retries),
            elapsed_seconds=0.0,
            error=error,
        )
        raise error


def _is_context_length_error(error: BaseException) -> bool:
    text = str(error).lower()
    return (
        "maximum context length" in text
        or "context length" in text
        or "reduce the length of the messages" in text
        or "too many tokens" in text
    )
