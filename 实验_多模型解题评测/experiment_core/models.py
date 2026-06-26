from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .utils import stable_hash


class ModelConfigError(ValueError):
    """模型配置不完整或不合法。"""


class InfrastructureError(RuntimeError):
    """API、网络或服务端失败，不应计为模型答题失败。"""

    def __init__(self, message: str, *, attempts: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts or []


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class ExperimentConcurrency:
    """实验调度并发配置。"""

    problem_workers: int
    models_per_problem: int
    raw_config: Any

    def public_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw_config,
            "problems": self.problem_workers,
            "models_per_problem": self.models_per_problem,
        }


@dataclass(frozen=True)
class ModelConfig:
    model_id: str
    model: str
    api_key: str
    base_url: str | None
    temperature: float
    timeout_seconds: float
    max_retries: int
    input_price_per_million: float | None
    output_price_per_million: float | None
    fingerprint: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, base_dir: Path) -> "ModelConfig":
        file_values: dict[str, str] = {}
        config_file = payload.get("config_file")
        if config_file:
            config_path = Path(str(config_file))
            if not config_path.is_absolute():
                config_path = (base_dir / config_path).resolve()
            if not config_path.is_file():
                raise ModelConfigError(f"模型配置文件不存在: {config_path}")
            file_values = _read_env_file(config_path)

        model_id = str(payload.get("id") or payload.get("model_id") or "").strip()
        model = str(payload.get("model") or file_values.get("MODEL") or "").strip()
        base_url = str(payload.get("base_url") or file_values.get("BASE_URL") or "").strip() or None
        api_key_env = str(payload.get("api_key_env") or "").strip()
        api_key = str(payload.get("api_key") or "").strip()
        if not api_key:
            api_key = os.environ.get(api_key_env, "") if api_key_env else file_values.get("API_KEY", "")
            api_key = api_key.strip()
        if not model_id or not model or not api_key:
            raise ModelConfigError(f"模型 {model_id or '<unknown>'} 缺少 id、model 或 API Key。")
        max_retries = int(payload.get("max_retries", file_values.get("MAX_RETRIES", 3)))
        timeout_seconds = float(payload.get("timeout_seconds", file_values.get("TIMEOUT_SECONDS", 360)))
        temperature = float(payload.get("temperature", 0.0))
        if max_retries <= 0 or timeout_seconds <= 0:
            raise ModelConfigError(f"模型 {model_id} 的 max_retries 和 timeout_seconds 必须为正数。")
        public_config = {
            "id": model_id,
            "model": model,
            "base_url": base_url,
            "api_key_env": api_key_env,
            "config_file": str(config_file or ""),
            "temperature": temperature,
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries,
            "input_price_per_million": payload.get("input_price_per_million"),
            "output_price_per_million": payload.get("output_price_per_million"),
        }
        return cls(
            model_id=model_id,
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            input_price_per_million=_optional_float(payload.get("input_price_per_million")),
            output_price_per_million=_optional_float(payload.get("output_price_per_million")),
            fingerprint=stable_hash(public_config),
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.model_id,
            "model": self.model,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "input_price_per_million": self.input_price_per_million,
            "output_price_per_million": self.output_price_per_million,
            "fingerprint": self.fingerprint,
        }


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _require_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ModelConfigError(f"{field_name} 必须为正整数。")
    return value


def _parse_concurrency(value: Any) -> ExperimentConcurrency:
    if isinstance(value, bool):
        raise ModelConfigError("concurrency 必须为正整数或对象。")
    if isinstance(value, int):
        worker_count = _require_positive_int(value, "concurrency")
        return ExperimentConcurrency(
            problem_workers=worker_count,
            models_per_problem=1,
            raw_config=value,
        )
    if isinstance(value, dict):
        if "problems" not in value or "models_per_problem" not in value:
            raise ModelConfigError("concurrency 对象必须包含 problems 和 models_per_problem。")
        return ExperimentConcurrency(
            problem_workers=_require_positive_int(value["problems"], "concurrency.problems"),
            models_per_problem=_require_positive_int(
                value["models_per_problem"],
                "concurrency.models_per_problem",
            ),
            raw_config=dict(value),
        )
    raise ModelConfigError("concurrency 必须为正整数或对象。")


def load_model_configs(path: Path) -> tuple[list[ModelConfig], ExperimentConcurrency]:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise ModelConfigError("models.json 必须包含 models 数组。")
    models = [ModelConfig.from_payload(item, base_dir=path.parent) for item in payload["models"]]
    ids = [model.model_id for model in models]
    if not models or len(ids) != len(set(ids)):
        raise ModelConfigError("模型列表不能为空，且 id 不能重复。")
    concurrency = _parse_concurrency(payload.get("concurrency", 1))
    return models, concurrency


class OpenAICompatibleClient:
    def __init__(self, config: ModelConfig) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise InfrastructureError("缺少 openai 包。") from exc
        kwargs: dict[str, Any] = {
            "api_key": config.api_key,
            "timeout": config.timeout_seconds,
            "max_retries": 0,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self.config = config
        self.client = OpenAI(**kwargs)

    def complete(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        for attempt in range(1, self.config.max_retries + 1):
            started = time.perf_counter()
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    temperature=self.config.temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                choices = getattr(response, "choices", None)
                content = choices[0].message.content if choices else None
                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("模型响应为空或缺少 choices。")
                if hasattr(response, "model_dump"):
                    try:
                        raw = response.model_dump(mode="json")
                    except TypeError:
                        raw = response.model_dump()
                else:
                    raw = {}
                usage = _usage_dict(getattr(response, "usage", None))
                return {
                    "content": content,
                    "usage": usage,
                    "duration_seconds": time.perf_counter() - started,
                    "api_attempt_count": attempt,
                    "failed_api_attempts": attempts,
                    "raw_response": raw,
                }
            except Exception as exc:
                attempts.append(
                    {
                        "attempt": attempt,
                        "duration_seconds": time.perf_counter() - started,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                if attempt < self.config.max_retries:
                    time.sleep(1.5 * attempt)
        last = attempts[-1] if attempts else {"error": "未知 API 错误"}
        raise InfrastructureError(str(last.get("error", "未知 API 错误")), attempts=attempts)


def _usage_dict(usage: Any) -> dict[str, int]:
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt = int(getattr(usage, "prompt_tokens", getattr(usage, "input_tokens", 0)) or 0)
    completion = int(getattr(usage, "completion_tokens", getattr(usage, "output_tokens", 0)) or 0)
    total = int(getattr(usage, "total_tokens", prompt + completion) or prompt + completion)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}


ClientFactory = Callable[[ModelConfig], Any]
