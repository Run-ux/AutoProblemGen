from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


RUNTIME_GENERATION_LLM_ENV = "AUTOPROBLEMGEN_GENERATION_LLM_CONFIG"
RUNTIME_EMBEDDING_LLM_ENV = "AUTOPROBLEMGEN_EMBEDDING_LLM_CONFIG"
RUNTIME_EXECUTION_ENV = "AUTOPROBLEMGEN_EXECUTION_CONFIG"
RUNTIME_CONTEXT_ENV = "AUTOPROBLEMGEN_CONTEXT_CONFIG"

DEFAULT_TEMPERATURE = 0.2
DEFAULT_LLM_TIMEOUT_SECONDS = 360.0
DEFAULT_LLM_MAX_RETRIES = 3

DEFAULT_TEST_INPUT_TIMEOUT_SECONDS = 5.0
DEFAULT_TEST_INPUT_MEMORY_LIMIT_MB = 512
DEFAULT_BRUTEFORCE_TIMEOUT_SECONDS = 5.0
DEFAULT_BRUTEFORCE_MEMORY_LIMIT_MB = 512
DEFAULT_CHECKER_TIMEOUT_SECONDS = 5.0
DEFAULT_CHECKER_MEMORY_LIMIT_MB = 512

DEFAULT_LLM_CASE_MAX_CHARS = 40_000
DEFAULT_LLM_CASE_INPUT_MAX_CHARS = 24_000
DEFAULT_LLM_CASE_OUTPUT_MAX_CHARS = 16_000
DEFAULT_LLM_CASE_TOTAL_CHARS = 160_000
DEFAULT_LLM_CASE_MAX_COUNT = 10
DEFAULT_MAX_LLM_PROMPT_CHARS = 600_000
DEFAULT_LLM_TRACE_MAX_TEXT_CHARS = 30_000


class RuntimeConfigError(ValueError):
    """表示总流程运行时配置缺失或格式不合法。"""


@dataclass(frozen=True)
class LLMEndpointConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_LLM_MAX_RETRIES
    temperature: float = DEFAULT_TEMPERATURE

    @classmethod
    def from_values(cls, values: dict[str, str], *, source: str) -> "LLMEndpointConfig":
        return cls(
            api_key=_require_text(values, "API_KEY", source=source),
            base_url=_require_text(values, "BASE_URL", source=source).rstrip("/"),
            model=_require_text(values, "MODEL", source=source),
            timeout_seconds=_read_positive_float(
                values,
                "TIMEOUT_SECONDS",
                DEFAULT_LLM_TIMEOUT_SECONDS,
                source=source,
            ),
            max_retries=_read_positive_int(
                values,
                "MAX_RETRIES",
                DEFAULT_LLM_MAX_RETRIES,
                source=source,
            ),
            temperature=_read_float(
                values,
                "TEMPERATURE",
                DEFAULT_TEMPERATURE,
                source=source,
            ),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, source: str) -> "LLMEndpointConfig":
        # 运行时 JSON 使用 dataclass 字段名；dotenv 文件使用大写配置名。
        # 这里显式归一化，避免子进程把总流程注入的合法 payload 误判为缺项。
        values = {
            "API_KEY": _payload_text(payload, "api_key", "API_KEY"),
            "BASE_URL": _payload_text(payload, "base_url", "BASE_URL"),
            "MODEL": _payload_text(payload, "model", "MODEL"),
            "TIMEOUT_SECONDS": _payload_text(payload, "timeout_seconds", "TIMEOUT_SECONDS"),
            "MAX_RETRIES": _payload_text(payload, "max_retries", "MAX_RETRIES"),
            "TEMPERATURE": _payload_text(payload, "temperature", "TEMPERATURE"),
        }
        return cls.from_values(values, source=source)

    def to_runtime_payload(self) -> dict[str, Any]:
        return asdict(self)

    def to_safe_summary(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "base_url_configured": bool(self.base_url),
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "temperature": self.temperature,
            "api_key_configured": bool(self.api_key),
        }


@dataclass(frozen=True)
class ExecutionLimits:
    test_input_timeout_seconds: float = DEFAULT_TEST_INPUT_TIMEOUT_SECONDS
    test_input_memory_limit_mb: int = DEFAULT_TEST_INPUT_MEMORY_LIMIT_MB
    bruteforce_timeout_seconds: float = DEFAULT_BRUTEFORCE_TIMEOUT_SECONDS
    bruteforce_memory_limit_mb: int = DEFAULT_BRUTEFORCE_MEMORY_LIMIT_MB
    checker_timeout_seconds: float = DEFAULT_CHECKER_TIMEOUT_SECONDS
    checker_memory_limit_mb: int = DEFAULT_CHECKER_MEMORY_LIMIT_MB

    @classmethod
    def from_values(cls, values: dict[str, str], *, source: str) -> "ExecutionLimits":
        return cls(
            test_input_timeout_seconds=_read_positive_float(
                values,
                "EXECUTION_TEST_INPUT_TIMEOUT_SECONDS",
                DEFAULT_TEST_INPUT_TIMEOUT_SECONDS,
                source=source,
            ),
            test_input_memory_limit_mb=_read_positive_int(
                values,
                "EXECUTION_TEST_INPUT_MEMORY_LIMIT_MB",
                DEFAULT_TEST_INPUT_MEMORY_LIMIT_MB,
                source=source,
            ),
            bruteforce_timeout_seconds=_read_positive_float(
                values,
                "EXECUTION_BRUTEFORCE_TIMEOUT_SECONDS",
                DEFAULT_BRUTEFORCE_TIMEOUT_SECONDS,
                source=source,
            ),
            bruteforce_memory_limit_mb=_read_positive_int(
                values,
                "EXECUTION_BRUTEFORCE_MEMORY_LIMIT_MB",
                DEFAULT_BRUTEFORCE_MEMORY_LIMIT_MB,
                source=source,
            ),
            checker_timeout_seconds=_read_positive_float(
                values,
                "EXECUTION_CHECKER_TIMEOUT_SECONDS",
                DEFAULT_CHECKER_TIMEOUT_SECONDS,
                source=source,
            ),
            checker_memory_limit_mb=_read_positive_int(
                values,
                "EXECUTION_CHECKER_MEMORY_LIMIT_MB",
                DEFAULT_CHECKER_MEMORY_LIMIT_MB,
                source=source,
            ),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, source: str) -> "ExecutionLimits":
        values = {
            "EXECUTION_TEST_INPUT_TIMEOUT_SECONDS": _payload_text(
                payload,
                "test_input_timeout_seconds",
                "EXECUTION_TEST_INPUT_TIMEOUT_SECONDS",
            ),
            "EXECUTION_TEST_INPUT_MEMORY_LIMIT_MB": _payload_text(
                payload,
                "test_input_memory_limit_mb",
                "EXECUTION_TEST_INPUT_MEMORY_LIMIT_MB",
            ),
            "EXECUTION_BRUTEFORCE_TIMEOUT_SECONDS": _payload_text(
                payload,
                "bruteforce_timeout_seconds",
                "EXECUTION_BRUTEFORCE_TIMEOUT_SECONDS",
            ),
            "EXECUTION_BRUTEFORCE_MEMORY_LIMIT_MB": _payload_text(
                payload,
                "bruteforce_memory_limit_mb",
                "EXECUTION_BRUTEFORCE_MEMORY_LIMIT_MB",
            ),
            "EXECUTION_CHECKER_TIMEOUT_SECONDS": _payload_text(
                payload,
                "checker_timeout_seconds",
                "EXECUTION_CHECKER_TIMEOUT_SECONDS",
            ),
            "EXECUTION_CHECKER_MEMORY_LIMIT_MB": _payload_text(
                payload,
                "checker_memory_limit_mb",
                "EXECUTION_CHECKER_MEMORY_LIMIT_MB",
            ),
        }
        return cls.from_values(values, source=source)

    def to_runtime_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextLimits:
    """控制进入 LLM 上下文和 trace 日志的文本规模。"""

    llm_case_max_chars: int = DEFAULT_LLM_CASE_MAX_CHARS
    llm_case_input_max_chars: int = DEFAULT_LLM_CASE_INPUT_MAX_CHARS
    llm_case_output_max_chars: int = DEFAULT_LLM_CASE_OUTPUT_MAX_CHARS
    llm_case_total_chars: int = DEFAULT_LLM_CASE_TOTAL_CHARS
    llm_case_max_count: int = DEFAULT_LLM_CASE_MAX_COUNT
    max_llm_prompt_chars: int = DEFAULT_MAX_LLM_PROMPT_CHARS
    llm_trace_max_text_chars: int = DEFAULT_LLM_TRACE_MAX_TEXT_CHARS

    @classmethod
    def from_values(cls, values: dict[str, str], *, source: str) -> "ContextLimits":
        return cls(
            llm_case_max_chars=_read_positive_int(
                values,
                "LLM_CASE_MAX_CHARS",
                DEFAULT_LLM_CASE_MAX_CHARS,
                source=source,
            ),
            llm_case_input_max_chars=_read_positive_int(
                values,
                "LLM_CASE_INPUT_MAX_CHARS",
                DEFAULT_LLM_CASE_INPUT_MAX_CHARS,
                source=source,
            ),
            llm_case_output_max_chars=_read_positive_int(
                values,
                "LLM_CASE_OUTPUT_MAX_CHARS",
                DEFAULT_LLM_CASE_OUTPUT_MAX_CHARS,
                source=source,
            ),
            llm_case_total_chars=_read_positive_int(
                values,
                "LLM_CASE_TOTAL_CHARS",
                DEFAULT_LLM_CASE_TOTAL_CHARS,
                source=source,
            ),
            llm_case_max_count=_read_positive_int(
                values,
                "LLM_CASE_MAX_COUNT",
                DEFAULT_LLM_CASE_MAX_COUNT,
                source=source,
            ),
            max_llm_prompt_chars=_read_positive_int(
                values,
                "MAX_LLM_PROMPT_CHARS",
                DEFAULT_MAX_LLM_PROMPT_CHARS,
                source=source,
            ),
            llm_trace_max_text_chars=_read_positive_int(
                values,
                "LLM_TRACE_MAX_TEXT_CHARS",
                DEFAULT_LLM_TRACE_MAX_TEXT_CHARS,
                source=source,
            ),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, source: str) -> "ContextLimits":
        values = {
            "LLM_CASE_MAX_CHARS": _payload_text(payload, "llm_case_max_chars", "LLM_CASE_MAX_CHARS"),
            "LLM_CASE_INPUT_MAX_CHARS": _payload_text(
                payload,
                "llm_case_input_max_chars",
                "LLM_CASE_INPUT_MAX_CHARS",
            ),
            "LLM_CASE_OUTPUT_MAX_CHARS": _payload_text(
                payload,
                "llm_case_output_max_chars",
                "LLM_CASE_OUTPUT_MAX_CHARS",
            ),
            "LLM_CASE_TOTAL_CHARS": _payload_text(
                payload,
                "llm_case_total_chars",
                "LLM_CASE_TOTAL_CHARS",
            ),
            "LLM_CASE_MAX_COUNT": _payload_text(payload, "llm_case_max_count", "LLM_CASE_MAX_COUNT"),
            "MAX_LLM_PROMPT_CHARS": _payload_text(payload, "max_llm_prompt_chars", "MAX_LLM_PROMPT_CHARS"),
            "LLM_TRACE_MAX_TEXT_CHARS": _payload_text(
                payload,
                "llm_trace_max_text_chars",
                "LLM_TRACE_MAX_TEXT_CHARS",
            ),
        }
        return cls.from_values(values, source=source)

    def to_runtime_payload(self) -> dict[str, Any]:
        return asdict(self)


def load_env_values(path: str | Path) -> dict[str, str]:
    """读取总流程使用的简单 KEY=VALUE 配置文件。"""
    target = Path(path)
    if not target.exists():
        raise RuntimeConfigError(f"配置文件不存在：{target}")
    if not target.is_file():
        raise RuntimeConfigError(f"配置路径不是文件：{target}")

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        parsed = _parse_env_line(raw_line, line_number=line_number, source=str(target))
        if parsed is None:
            continue
        key, value = parsed
        values[key] = value
    return values


def load_llm_endpoint_config(path: str | Path) -> LLMEndpointConfig:
    target = Path(path)
    return LLMEndpointConfig.from_values(load_env_values(target), source=str(target))


def llm_config_from_runtime_env(name: str) -> LLMEndpointConfig:
    payload = _runtime_payload_from_env(name)
    return LLMEndpointConfig.from_payload(payload, source=f"环境变量 {name}")


def execution_limits_from_runtime_env() -> ExecutionLimits:
    payload = _runtime_payload_from_env(RUNTIME_EXECUTION_ENV)
    return ExecutionLimits.from_payload(payload, source=f"环境变量 {RUNTIME_EXECUTION_ENV}")


def context_limits_from_runtime_env() -> ContextLimits:
    payload = _runtime_payload_from_env(RUNTIME_CONTEXT_ENV)
    return ContextLimits.from_payload(payload, source=f"环境变量 {RUNTIME_CONTEXT_ENV}")


def runtime_env_payload(
    *,
    generation_llm: LLMEndpointConfig,
    embedding_llm: LLMEndpointConfig,
    execution_limits: ExecutionLimits,
    context_limits: ContextLimits,
) -> dict[str, str]:
    return {
        RUNTIME_GENERATION_LLM_ENV: json.dumps(generation_llm.to_runtime_payload(), ensure_ascii=False),
        RUNTIME_EMBEDDING_LLM_ENV: json.dumps(embedding_llm.to_runtime_payload(), ensure_ascii=False),
        RUNTIME_EXECUTION_ENV: json.dumps(execution_limits.to_runtime_payload(), ensure_ascii=False),
        RUNTIME_CONTEXT_ENV: json.dumps(context_limits.to_runtime_payload(), ensure_ascii=False),
        "PYTHONIOENCODING": "utf-8",
    }


def _runtime_payload_from_env(name: str) -> dict[str, Any]:
    import os

    raw = os.environ.get(name, "").strip()
    if not raw:
        raise RuntimeConfigError(f"缺少总流程运行时配置环境变量：{name}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeConfigError(f"运行时配置环境变量不是合法 JSON：{name}") from exc
    if not isinstance(payload, dict):
        raise RuntimeConfigError(f"运行时配置环境变量必须是 JSON 对象：{name}")
    return payload


def _parse_env_line(line: str, *, line_number: int, source: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].lstrip()
    if "=" not in stripped:
        raise RuntimeConfigError(f"{source} 第 {line_number} 行格式错误，应为 KEY=VALUE。")

    key, raw_value = stripped.split("=", 1)
    key = key.strip()
    if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
        raise RuntimeConfigError(f"{source} 第 {line_number} 行配置名非法：{key!r}")
    return key, _parse_env_value(raw_value, line_number=line_number, source=source)


def _parse_env_value(raw_value: str, *, line_number: int, source: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if value[0] in {"'", '"'}:
        quote = value[0]
        end_index = value.find(quote, 1)
        if end_index == -1:
            raise RuntimeConfigError(f"{source} 第 {line_number} 行引号未闭合。")
        tail = value[end_index + 1 :].strip()
        if tail and not tail.startswith("#"):
            raise RuntimeConfigError(f"{source} 第 {line_number} 行引号后只能为空或注释。")
        return value[1:end_index]

    for index, char in enumerate(value):
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].strip()
    return value


def _require_text(values: dict[str, str], key: str, *, source: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise RuntimeConfigError(f"{source} 缺少必要配置 {key}。")
    return value


def _payload_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in payload and payload[key] is not None:
            return str(payload[key])
    return ""


def _read_float(values: dict[str, str], key: str, default: float, *, source: str) -> float:
    raw = values.get(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeConfigError(f"{source} 配置 {key} 必须是数字。") from exc


def _read_positive_float(values: dict[str, str], key: str, default: float, *, source: str) -> float:
    value = _read_float(values, key, default, source=source)
    if value <= 0:
        raise RuntimeConfigError(f"{source} 配置 {key} 必须大于 0。")
    return value


def _read_positive_int(values: dict[str, str], key: str, default: int, *, source: str) -> int:
    raw = values.get(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeConfigError(f"{source} 配置 {key} 必须是整数。") from exc
    if value <= 0:
        raise RuntimeConfigError(f"{source} 配置 {key} 必须大于 0。")
    return value


def ensure_workflow_runtime_on_path() -> None:
    """供子模块脚本复用：把总流程目录加入 import path。"""
    workflow_dir = Path(__file__).resolve().parent
    workflow_dir_text = str(workflow_dir)
    if workflow_dir_text not in sys.path:
        sys.path.insert(0, workflow_dir_text)
