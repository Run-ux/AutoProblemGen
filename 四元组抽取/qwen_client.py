"""
千问大模型 API 客户端

参考 ICPC题目提取schema/icpc_schema_extractor/qwen_client.py
修正 lstrip bug: 使用 removeprefix 替代 lstrip

用法：
    from qwen_client import QwenClient

    client = QwenClient(llm_config=generation_llm_config)
    result = client.chat_json(system_prompt, user_prompt)
"""

from __future__ import annotations

import ast
import json
import logging
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / "总流程"
if str(WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_DIR))

from runtime_config import LLMEndpointConfig
from llm_trace import fail_call, finish_call, new_call_id, retry_call, start_call, summarize_value


logger = logging.getLogger(__name__)


@dataclass
class QwenConfig:
    stage: str = "default"
    timeout_s: int | None = None


class QwenJSONError(RuntimeError):
    def __init__(self, message: str, raw_text: str = ""):
        super().__init__(message)
        self.raw_text = raw_text


class QwenClient:
    def __init__(
        self,
        cfg: Optional[QwenConfig] = None,
        llm_config: LLMEndpointConfig | None = None,
    ):
        cfg = cfg or QwenConfig()
        if llm_config is None:
            raise RuntimeError(
                "缺少 generation LLM 配置：请通过总流程 generation_llm.env 配置，"
                "并由调用方显式传入 QwenClient。"
            )
        resolved = llm_config

        if not resolved.api_key:
            raise RuntimeError(
                "缺少 API Key：请通过总流程 generation_llm.env 配置 API_KEY。"
            )

        self.base_url = resolved.base_url
        self.api_key = resolved.api_key
        self.model = resolved.model
        self.timeout_s = cfg.timeout_s or resolved.timeout_seconds
        self.max_retries = resolved.max_retries

    def chat_json(
        self,
        system: str,
        user: str,
        max_retries: int | None = None,
        temperature: float = 0.2,
        request_label: str = "",
    ) -> Dict[str, Any]:
        last_err: Exception | None = None
        last_raw_text = ""
        label = request_label or "unnamed-request"
        retries = max_retries or self.max_retries
        call_id = new_call_id()
        for attempt in range(1, retries + 1):
            started = start_call(
                call_id=call_id,
                task_name=label,
                model=self.model,
                endpoint=self.base_url.rstrip("/") + "/chat/completions",
                temperature=temperature,
                timeout_seconds=self.timeout_s,
                attempt=attempt,
                max_retries=retries,
                system_prompt=system,
                user_prompt=user,
                payload={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                },
            )
            try:
                logger.info(
                    "[Qwen] %s: 主请求第 %d/%d 次，timeout=%ss",
                    label,
                    attempt,
                    retries,
                    self.timeout_s,
                )
                response_meta = self._chat_text(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                )
                content = str(response_meta["content"])
                last_raw_text = content
                try:
                    parsed = _extract_first_json_object(content)
                    finish_call(
                        call_id=call_id,
                        task_name=label,
                        elapsed_seconds=time.perf_counter() - started,
                        http_status=response_meta.get("http_status"),
                        response_text=content,
                        raw_response=response_meta.get("raw_response"),
                        usage=response_meta.get("usage", {}),
                        json_parse="success",
                        summary=summarize_value(parsed),
                    )
                    return parsed
                except ValueError:
                    logger.warning("[Qwen] %s: 主请求返回内容不是合法 JSON，进入 JSON 修复", label)
                    retry_call(
                        call_id=call_id,
                        task_name=label,
                        attempt=attempt,
                        max_retries=retries,
                        elapsed_seconds=time.perf_counter() - started,
                        error="模型返回内容不是合法 JSON，进入 JSON 修复",
                        retry_delay_seconds=0.0,
                    )
                    repaired = self._repair_json_content(content, request_label=label)
                    last_raw_text = repaired
                    parsed = _extract_first_json_object(repaired)
                    finish_call(
                        call_id=call_id,
                        task_name=label,
                        elapsed_seconds=time.perf_counter() - started,
                        http_status=response_meta.get("http_status"),
                        response_text=repaired,
                        raw_response={"original": content, "repaired": repaired},
                        usage=response_meta.get("usage", {}),
                        json_parse="repaired",
                        summary=summarize_value(parsed),
                    )
                    return parsed
            except (
                urllib.error.URLError,
                urllib.error.HTTPError,
                KeyError,
                ValueError,
                TimeoutError,
                socket.timeout,
            ) as e:
                last_err = e
                delay = self._retry_delay_seconds(e, attempt)
                logger.warning(
                    "[Qwen] %s: 第 %d/%d 次失败，错误=%s: %s；%s %.1f 秒后重试",
                    label,
                    attempt,
                    retries,
                    type(e).__name__,
                    e,
                    "检测到超时，" if isinstance(e, (TimeoutError, socket.timeout)) else "",
                    delay,
                )
                if attempt < retries:
                    retry_call(
                        call_id=call_id,
                        task_name=label,
                        attempt=attempt,
                        max_retries=retries,
                        elapsed_seconds=time.perf_counter() - started,
                        error=e,
                        retry_delay_seconds=delay,
                    )
                else:
                    fail_call(
                        call_id=call_id,
                        task_name=label,
                        attempt=attempt,
                        max_retries=retries,
                        elapsed_seconds=time.perf_counter() - started,
                        error=e,
                    )
                time.sleep(delay)
            except QwenJSONError as e:
                last_err = e
                last_raw_text = e.raw_text
                delay = self._retry_delay_seconds(e, attempt)
                logger.warning(
                    "[Qwen] %s: 第 %d/%d 次失败，错误=%s: %s；%.1f 秒后重试",
                    label,
                    attempt,
                    retries,
                    type(e).__name__,
                    e,
                    delay,
                )
                if attempt < retries:
                    retry_call(
                        call_id=call_id,
                        task_name=label,
                        attempt=attempt,
                        max_retries=retries,
                        elapsed_seconds=time.perf_counter() - started,
                        error=e,
                        retry_delay_seconds=delay,
                    )
                else:
                    fail_call(
                        call_id=call_id,
                        task_name=label,
                        attempt=attempt,
                        max_retries=retries,
                        elapsed_seconds=time.perf_counter() - started,
                        error=e,
                    )
                time.sleep(delay)

        raise QwenJSONError(f"调用千问失败：{last_err}", raw_text=last_raw_text)

    def _chat_text(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        model: str | None = None,
    ) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
        }
        request = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            http_status = response.getcode()
            data = json.loads(response.read().decode("utf-8"))
        return {
            "content": data["choices"][0]["message"]["content"],
            "raw_response": data,
            "http_status": http_status,
            "usage": data.get("usage", {}) if isinstance(data, dict) else {},
        }

    def _repair_json_content(self, broken_text: str, request_label: str = "") -> str:
        repair_system = (
            "你是 JSON 修复器。你的唯一任务是把用户提供的内容转换为严格合法的 JSON。"
            "不要补充解释，不要输出 Markdown 代码块，只输出一个 JSON 对象。"
        )
        repair_user = (
            "下面是一段本应为 JSON 但格式不合法的文本。"
            "请在不改变语义的前提下修复为严格 JSON：\n\n"
            f"{broken_text}"
        )
        try:
            logger.info("[Qwen] %s: 发起 JSON 修复请求，timeout=%ss", request_label or "unnamed-request", self.timeout_s)
            label = f"{request_label or 'unnamed-request'}.json_repair"
            call_id = new_call_id()
            started = start_call(
                call_id=call_id,
                task_name=label,
                model=self.model,
                endpoint=self.base_url.rstrip("/") + "/chat/completions",
                temperature=0.0,
                timeout_seconds=self.timeout_s,
                attempt=1,
                max_retries=1,
                system_prompt=repair_system,
                user_prompt=repair_user,
                payload={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": repair_system},
                        {"role": "user", "content": repair_user},
                    ],
                    "temperature": 0.0,
                },
            )
            response_meta = self._chat_text(
                messages=[
                    {"role": "system", "content": repair_system},
                    {"role": "user", "content": repair_user},
                ],
                temperature=0.0,
            )
            content = str(response_meta["content"])
            finish_call(
                call_id=call_id,
                task_name=label,
                elapsed_seconds=time.perf_counter() - started,
                http_status=response_meta.get("http_status"),
                response_text=content,
                raw_response=response_meta.get("raw_response"),
                usage=response_meta.get("usage", {}),
                json_parse="unchecked",
                summary={"repair_response_chars": len(content)},
            )
            return content
        except Exception as exc:
            fail_call(
                call_id=call_id if "call_id" in locals() else new_call_id(),
                task_name=f"{request_label or 'unnamed-request'}.json_repair",
                attempt=1,
                max_retries=1,
                elapsed_seconds=time.perf_counter() - started if "started" in locals() else 0.0,
                error=exc,
            )
            raise QwenJSONError(f"JSON 修复失败：{exc}", raw_text=broken_text) from exc

    def _retry_delay_seconds(self, error: Exception, attempt: int) -> float:
        if isinstance(error, (TimeoutError, socket.timeout)):
            return 5.0 * attempt
        return 1.5 * attempt


def _extract_first_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()

    if "```" in text:
        parts = text.split("```")
        candidate = max(parts, key=len).strip()
        candidate = candidate.removeprefix("json").strip()
        try:
            return json.loads(_normalize_json_candidate(candidate))
        except Exception:
            pass

    normalized = _normalize_json_candidate(text)
    try:
        return json.loads(normalized)
    except Exception:
        pass

    start = text.find("{")
    if start == -1:
        raise ValueError("模型输出未包含JSON对象")

    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                snippet = text[start : i + 1]
                try:
                    return json.loads(_normalize_json_candidate(snippet))
                except Exception:
                    normalized_snippet = _normalize_json_candidate(snippet)
                    return json.loads(normalized_snippet)

    raise ValueError("JSON对象不完整")


def _normalize_json_candidate(text: str) -> str:
    replacements = {
        "“": '"',
        "”": '"',
        "‘": '"',
        "’": '"',
        "，": ",",
        "：": ":",
        "\u00a0": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = _replace_numeric_expressions(text)
    return text


def _replace_numeric_expressions(text: str) -> str:
    pattern = re.compile(r'(:\s*)(-?[0-9][0-9\s\+\-\*\/\(\)]*)(\s*[,}\]])')

    def repl(match: re.Match[str]) -> str:
        prefix, expr, suffix = match.groups()
        compact = expr.strip()
        if not compact:
            return match.group(0)
        try:
            value = _safe_eval_arithmetic(compact)
        except ValueError:
            return match.group(0)
        return f"{prefix}{value}{suffix}"

    previous = None
    while previous != text:
        previous = text
        text = pattern.sub(repl, text)
    return text


def _safe_eval_arithmetic(expr: str) -> int:
    try:
        node = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid arithmetic expression: {expr}") from exc
    return _eval_ast_node(node.body)


def _eval_ast_node(node: ast.AST) -> int:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_ast_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(
        node.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Div, ast.Pow, ast.Mod)
    ):
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Pow):
            return left**right
        if right == 0:
            raise ValueError("Division by zero")
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Div):
            if left % right != 0:
                raise ValueError("Non-integer division result")
            return left // right
        return left // right
    raise ValueError(f"Unsupported arithmetic node: {type(node).__name__}")
