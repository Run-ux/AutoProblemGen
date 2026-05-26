from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / "总流程"
if str(WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_DIR))

from runtime_config import LLMEndpointConfig, RuntimeConfigError, llm_config_from_runtime_env


DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_LLM_PROMPT_CHARS = 600_000


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    model: str
    base_url: str | None = None
    temperature: float = DEFAULT_TEMPERATURE
    timeout_seconds: float = 360.0
    max_retries: int = 3
    max_prompt_chars: int = DEFAULT_MAX_LLM_PROMPT_CHARS

    @classmethod
    def from_endpoint(cls, endpoint: LLMEndpointConfig) -> "LLMConfig":
        return cls(
            api_key=endpoint.api_key,
            model=endpoint.model,
            base_url=endpoint.base_url,
            temperature=endpoint.temperature,
            timeout_seconds=endpoint.timeout_seconds,
            max_retries=endpoint.max_retries,
        )

    @classmethod
    def from_runtime_env(cls, name: str) -> "LLMConfig":
        return cls.from_endpoint(llm_config_from_runtime_env(name))

    def with_max_prompt_chars(self, max_prompt_chars: int) -> "LLMConfig":
        if max_prompt_chars <= 0:
            raise RuntimeConfigError("MAX_LLM_PROMPT_CHARS 必须大于 0。")
        return replace(self, max_prompt_chars=max_prompt_chars)


ConfigError = RuntimeConfigError
