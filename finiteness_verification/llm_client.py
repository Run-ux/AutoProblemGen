"""
通用 OpenAI-compatible LLM API 客户端

用法：
    from finiteness_verification.llm_client import LLMClient

    client = LLMClient()
    result = client.chat_json(system_prompt, user_prompt)
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


ENV_KEYS = {
    "base_url": "LLM_BASE_URL",
    "api_key": "LLM_API_KEY",
    "model": "LLM_MODEL",
    "embedding_base_url": "EMBEDDING_BASE_URL",
    "embedding_api_key": "EMBEDDING_API_KEY",
    "embedding_model": "EMBEDDING_MODEL",
    "timeout_s": "LLM_TIMEOUT_S",
}


@dataclass
class LLMConfig:
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    timeout_s: int | None = None


class LLMJSONError(RuntimeError):
    def __init__(self, message: str, raw_text: str = ""):
        super().__init__(message)
        self.raw_text = raw_text


class LLMClient:
    def __init__(self, cfg: Optional[LLMConfig] = None):
        cfg = cfg or LLMConfig()
        env_file_values = load_env_file_values()

        self.base_url = _resolve_config_value(
            cfg.base_url, ENV_KEYS["base_url"], env_file_values
        )
        self.api_key = _resolve_config_value(
            cfg.api_key, ENV_KEYS["api_key"], env_file_values
        )
        self.model = _resolve_config_value(
            cfg.model, ENV_KEYS["model"], env_file_values
        )
        self.embedding_base_url = _resolve_config_value(
            cfg.embedding_base_url, ENV_KEYS["embedding_base_url"], env_file_values
        )
        self.embedding_api_key = _resolve_config_value(
            cfg.embedding_api_key, ENV_KEYS["embedding_api_key"], env_file_values
        )
        self.embedding_model = _resolve_config_value(
            cfg.embedding_model, ENV_KEYS["embedding_model"], env_file_values
        )
        self.timeout_s = _resolve_timeout(cfg.timeout_s, env_file_values)

        missing = [
            key
            for key, value in [
                ("LLM_BASE_URL", self.base_url),
                ("LLM_API_KEY", self.api_key),
                ("LLM_MODEL", self.model),
                ("EMBEDDING_BASE_URL", self.embedding_base_url),
                ("EMBEDDING_API_KEY", self.embedding_api_key),
                ("EMBEDDING_MODEL", self.embedding_model),
            ]
            if not value
        ]
        if missing:
            raise RuntimeError(
                "缺少 LLM 配置：请在系统环境变量或 .env 文件中设置 "
                + ", ".join(missing)
            )

    def chat_json(
        self,
        system: str,
        user: str,
        max_retries: int = 3,
        temperature: float = 0.2,
        request_label: str = "",
    ) -> Dict[str, Any]:
        last_err: Exception | None = None
        last_raw_text = ""
        label = request_label or "unnamed-request"
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "[LLM] %s: 主请求第 %d/%d 次，timeout=%ss",
                    label,
                    attempt,
                    max_retries,
                    self.timeout_s,
                )
                content = self._chat_text(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                )
                last_raw_text = content
                try:
                    return _extract_first_json_object(content)
                except ValueError:
                    logger.warning(
                        "[LLM] %s: 主请求返回内容不是合法 JSON，进入 JSON 修复",
                        label,
                    )
                    repaired = self._repair_json_content(content, request_label=label)
                    last_raw_text = repaired
                    return _extract_first_json_object(repaired)
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
                    "[LLM] %s: 第 %d/%d 次失败，错误=%s: %s；%s %.1f 秒后重试",
                    label,
                    attempt,
                    max_retries,
                    type(e).__name__,
                    e,
                    "检测到超时，" if isinstance(e, (TimeoutError, socket.timeout)) else "",
                    delay,
                )
                time.sleep(delay)
            except LLMJSONError as e:
                last_err = e
                last_raw_text = e.raw_text
                delay = self._retry_delay_seconds(e, attempt)
                logger.warning(
                    "[LLM] %s: 第 %d/%d 次失败，错误=%s: %s；%.1f 秒后重试",
                    label,
                    attempt,
                    max_retries,
                    type(e).__name__,
                    e,
                    delay,
                )
                time.sleep(delay)

        raise LLMJSONError(f"调用 LLM 失败：{last_err}", raw_text=last_raw_text)

    def embed_texts(
        self, texts: list[str], model: str | None = None, batch_size: int = 10
    ) -> list[list[float]]:
        """调用 embedding API，自动分批，避免单次请求过大。"""
        if not texts:
            return []
        url = self.embedding_base_url.rstrip("/") + "/embeddings"
        headers = {
            "Authorization": f"Bearer {self.embedding_api_key}",
            "Content-Type": "application/json",
        }
        use_model = model or self.embedding_model
        all_embeddings: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            payload = {
                "model": use_model,
                "input": batch,
            }
            request = urllib.request.Request(
                url=url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
            batch_embeddings = [
                item.get("embedding", []) for item in data.get("data", [])
            ]
            all_embeddings.extend(batch_embeddings)
            # 避免触发服务端限速。
            if start + batch_size < len(texts):
                time.sleep(0.3)
        return all_embeddings

    def _chat_text(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        model: str | None = None,
    ) -> str:
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
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

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
            logger.info(
                "[LLM] %s: 发起 JSON 修复请求，timeout=%ss",
                request_label or "unnamed-request",
                self.timeout_s,
            )
            return self._chat_text(
                messages=[
                    {"role": "system", "content": repair_system},
                    {"role": "user", "content": repair_user},
                ],
                temperature=0.0,
            )
        except Exception as exc:
            raise LLMJSONError(f"JSON 修复失败：{exc}", raw_text=broken_text) from exc

    def _retry_delay_seconds(self, error: Exception, attempt: int) -> float:
        if isinstance(error, (TimeoutError, socket.timeout)):
            return 5.0 * attempt
        return 1.5 * attempt


def load_env_file_values() -> dict[str, str]:
    env_path = _find_env_file()
    if env_path is None:
        return {}
    return _parse_env_file(env_path)


def _find_env_file() -> Path | None:
    explicit = os.getenv("LLM_ENV_FILE")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(Path.cwd() / ".env")
    candidates.append(Path(__file__).resolve().parent / ".env")

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved
    return None


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            raise ValueError(f"{path}:{line_no} 不是合法的 .env 配置行")
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"{path}:{line_no} 缺少配置名")
        values[key] = _normalize_env_value(value.strip())
    return values


def _normalize_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def _resolve_config_value(
    explicit_value: str | None,
    env_key: str,
    env_file_values: dict[str, str],
) -> str | None:
    if explicit_value is not None:
        return explicit_value
    if env_key in os.environ:
        return os.environ[env_key]
    return env_file_values.get(env_key)


def _resolve_timeout(
    explicit_value: int | None,
    env_file_values: dict[str, str],
) -> int:
    if explicit_value is not None:
        return explicit_value
    raw_value = os.getenv(ENV_KEYS["timeout_s"]) or env_file_values.get(
        ENV_KEYS["timeout_s"]
    )
    if raw_value is None or raw_value == "":
        return 300
    try:
        timeout = int(raw_value)
    except ValueError as exc:
        raise ValueError("LLM_TIMEOUT_S 必须是整数") from exc
    if timeout <= 0:
        raise ValueError("LLM_TIMEOUT_S 必须大于 0")
    return timeout


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
