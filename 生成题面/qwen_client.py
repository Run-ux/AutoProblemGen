from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / "总流程"
if str(WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_DIR))

from runtime_config import LLMEndpointConfig
from llm_trace import fail_call, finish_call, new_call_id, retry_call, start_call, summarize_value


DEFAULT_DISTANCE_CACHE_DIR = Path(__file__).resolve().parent / ".cache"


class QwenClient:
    def __init__(
        self,
        generation_config: LLMEndpointConfig | None = None,
        embedding_config: LLMEndpointConfig | None = None,
        distance_cache_path: Path | None = None,
    ):
        if generation_config is None:
            raise RuntimeError("缺少 generation LLM 配置：请通过总流程 generation_llm.env 注入。")
        if embedding_config is None:
            raise RuntimeError("缺少 embedding LLM 配置：请通过总流程 embedding_llm.env 注入。")

        self.generation_config = generation_config
        self.embedding_config = embedding_config
        if not self.generation_config.api_key:
            raise RuntimeError("缺少 API Key：请通过总流程 generation_llm.env 配置 API_KEY。")
        if not self.embedding_config.api_key:
            raise RuntimeError("缺少 API Key：请通过总流程 embedding_llm.env 配置 API_KEY。")

        self.api_key = self.generation_config.api_key
        self.model = self.generation_config.model
        self.base_url = self.generation_config.base_url.rstrip("/")
        self.timeout_s = self.generation_config.timeout_seconds
        self.embedding_model = self.embedding_config.model
        self.embedding_base_url = self.embedding_config.base_url.rstrip("/")
        self.embedding_timeout_s = self.embedding_config.timeout_seconds
        self.distance_cache_path = distance_cache_path or (DEFAULT_DISTANCE_CACHE_DIR / "schema_distance_embeddings.json")

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_retries: int | None = None,
        request_label: str = "chat_json",
    ) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        raw = self._post_json(
            url=url,
            payload=payload,
            api_key=self.api_key,
            timeout_s=self.timeout_s,
            max_retries=max_retries or self.generation_config.max_retries,
            model=self.model,
            task_name=request_label,
        )
        content = json.loads(raw)["choices"][0]["message"]["content"]
        return _extract_json_object(content)

    def embed_texts(
        self,
        texts: list[str],
        model: str | None = None,
        dimensions: int | None = None,
        max_retries: int | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        active_model = model or self.embedding_model
        payload: dict[str, Any] = {
            "model": active_model,
            "input": texts,
        }
        if dimensions is not None:
            payload["dimensions"] = dimensions

        url = f"{self.embedding_base_url}/embeddings"
        raw = self._post_json(
            url=url,
            payload=payload,
            api_key=self.embedding_config.api_key,
            timeout_s=self.embedding_timeout_s,
            max_retries=max_retries or self.embedding_config.max_retries,
            model=active_model,
            task_name="embedding",
        )
        data = json.loads(raw).get("data", [])
        if not isinstance(data, list):
            raise RuntimeError("Embedding 接口返回结构异常，缺少 data 列表。")

        ordered: list[tuple[int, list[float]]] = []
        for index, item in enumerate(data):
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise RuntimeError("Embedding 接口返回结构异常，缺少 embedding 向量。")
            raw_index = item.get("index")
            vector_index = raw_index if isinstance(raw_index, int) else index
            ordered.append((vector_index, [float(value) for value in item["embedding"]]))

        ordered.sort(key=lambda item: item[0])
        vectors = [vector for _, vector in ordered]
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding 返回数量与请求文本数量不一致。")
        return vectors

    def _post_json(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        api_key: str,
        timeout_s: float,
        max_retries: int,
        model: str,
        task_name: str,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        payload_json = json.dumps(payload, ensure_ascii=False)
        payload_size = len(payload_json.encode("utf-8"))
        call_id = new_call_id()
        system_prompt, user_prompt = _extract_prompts(payload)
        for attempt in range(1, max_retries + 1):
            started = start_call(
                call_id=call_id,
                task_name=task_name,
                model=model,
                endpoint=url,
                temperature=_payload_temperature(payload),
                timeout_seconds=timeout_s,
                attempt=attempt,
                max_retries=max_retries,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                payload=payload,
            )
            try:
                request = urllib.request.Request(
                    url=url,
                    data=payload_json.encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=timeout_s) as response:
                    http_status = response.getcode()
                    raw_text = response.read().decode("utf-8")
                summary, response_text, usage, json_parse = _summarize_raw_response(raw_text, payload)
                finish_call(
                    call_id=call_id,
                    task_name=task_name,
                    elapsed_seconds=time.perf_counter() - started,
                    http_status=http_status,
                    response_text=response_text,
                    raw_response=_safe_json_loads(raw_text),
                    usage=usage,
                    json_parse=json_parse,
                    summary=summary,
                )
                return raw_text
            except (
                TimeoutError,
                socket.timeout,
                urllib.error.URLError,
                urllib.error.HTTPError,
                KeyError,
                ValueError,
            ) as exc:
                last_error = exc
                delay = 1.5 * attempt
                if attempt < max_retries:
                    retry_call(
                        call_id=call_id,
                        task_name=task_name,
                        attempt=attempt,
                        max_retries=max_retries,
                        elapsed_seconds=time.perf_counter() - started,
                        error=exc,
                        retry_delay_seconds=delay,
                    )
                else:
                    fail_call(
                        call_id=call_id,
                        task_name=task_name,
                        attempt=attempt,
                        max_retries=max_retries,
                        elapsed_seconds=time.perf_counter() - started,
                        error=exc,
                    )
                time.sleep(delay)
        raise RuntimeError(
            "调用 LLM 失败: "
            f"model={model}; url={url}; timeout_s={timeout_s}; "
            f"max_retries={max_retries}; payload_bytes={payload_size}; error={last_error}"
        )

def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)

    if "```" in text:
        for block in text.split("```"):
            candidate = block.strip().removeprefix("json").strip()
            if candidate.startswith("{"):
                return json.loads(candidate)

    start = text.find("{")
    if start < 0:
        raise ValueError("模型返回内容中未找到 JSON 对象。")

    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise ValueError("模型返回的 JSON 对象不完整。")


def _extract_prompts(payload: dict[str, Any]) -> tuple[str, str]:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return "", ""
    system_prompt = ""
    user_prompt = ""
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", ""))
        content = str(message.get("content", ""))
        if role == "system" and not system_prompt:
            system_prompt = content
        elif role == "user" and not user_prompt:
            user_prompt = content
    return system_prompt, user_prompt


def _payload_temperature(payload: dict[str, Any]) -> float | None:
    value = payload.get("temperature")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _summarize_raw_response(raw_text: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any], str]:
    data = _safe_json_loads(raw_text)
    if not isinstance(data, dict):
        return summarize_value(data), raw_text, {}, "failed"
    usage = data.get("usage", {}) if isinstance(data.get("usage", {}), dict) else {}
    if "embeddings" in str(payload.get("model", "")).lower() or "input" in payload and "messages" not in payload:
        return summarize_value(data), raw_text, usage, "success"
    try:
        content = str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        return summarize_value(data), raw_text, usage, "failed"
    try:
        parsed = _extract_json_object(content)
    except Exception:
        return summarize_value(data), content, usage, "failed"
    return summarize_value(parsed), content, usage, "success"
