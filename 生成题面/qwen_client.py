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
    ) -> str:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        payload_json = json.dumps(payload, ensure_ascii=False)
        payload_size = len(payload_json.encode("utf-8"))
        for attempt in range(1, max_retries + 1):
            try:
                request = urllib.request.Request(
                    url=url,
                    data=payload_json.encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=timeout_s) as response:
                    return response.read().decode("utf-8")
            except (
                TimeoutError,
                socket.timeout,
                urllib.error.URLError,
                urllib.error.HTTPError,
                KeyError,
                ValueError,
            ) as exc:
                last_error = exc
                time.sleep(1.5 * attempt)
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
