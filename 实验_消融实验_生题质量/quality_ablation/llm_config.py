from __future__ import annotations

from pathlib import Path

from .utils import DEFAULT_LLM_ENV

from qwen_client import QwenClient
from runtime_config import LLMEndpointConfig, RuntimeConfigError, load_env_values


REQUIRED_ENDPOINT_KEYS = ("API_KEY", "BASE_URL", "MODEL")
OPTIONAL_ENDPOINT_KEYS = ("TIMEOUT_SECONDS", "MAX_RETRIES", "TEMPERATURE")


def load_llm_endpoint_configs(env_path: str | Path = DEFAULT_LLM_ENV) -> tuple[LLMEndpointConfig, LLMEndpointConfig]:
    values = load_env_values(env_path)
    source = str(Path(env_path))
    generation_config = _endpoint_from_prefix(values, prefix="GENERATION", source=source)
    embedding_config = _endpoint_from_prefix(values, prefix="EMBEDDING", source=source)
    return generation_config, embedding_config


def load_qwen_client(env_path: str | Path = DEFAULT_LLM_ENV) -> QwenClient:
    generation_config, embedding_config = load_llm_endpoint_configs(env_path)
    return QwenClient(generation_config=generation_config, embedding_config=embedding_config)


def _endpoint_from_prefix(values: dict[str, str], *, prefix: str, source: str) -> LLMEndpointConfig:
    missing = [
        f"{prefix}_{key}"
        for key in REQUIRED_ENDPOINT_KEYS
        if not values.get(f"{prefix}_{key}", "").strip()
    ]
    if missing:
        raise RuntimeConfigError(f"{source} 缺少必要配置 {', '.join(missing)}。")

    endpoint_values: dict[str, str] = {}
    for key in (*REQUIRED_ENDPOINT_KEYS, *OPTIONAL_ENDPOINT_KEYS):
        prefixed_key = f"{prefix}_{key}"
        if prefixed_key in values:
            endpoint_values[key] = values[prefixed_key]
    return LLMEndpointConfig.from_values(endpoint_values, source=f"{source} 的 {prefix}_* 配置")
