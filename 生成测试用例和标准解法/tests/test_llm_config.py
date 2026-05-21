from __future__ import annotations

import json
import os
import unittest
from unittest import mock

import path_setup  # noqa: F401
from llm_config import DEFAULT_TEMPERATURE, LLMConfig
from runtime_config import LLMEndpointConfig, RUNTIME_GENERATION_LLM_ENV


class LLMConfigTests(unittest.TestCase):
    def test_from_endpoint_maps_runtime_config(self) -> None:
        endpoint = LLMEndpointConfig(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
            temperature=0.7,
            timeout_seconds=15,
            max_retries=4,
        )

        config = LLMConfig.from_endpoint(endpoint)

        self.assertEqual(config.api_key, "test-key")
        self.assertEqual(config.model, "test-model")
        self.assertEqual(config.base_url, "https://example.test/v1")
        self.assertEqual(config.temperature, 0.7)
        self.assertEqual(config.timeout_seconds, 15)
        self.assertEqual(config.max_retries, 4)

    def test_from_runtime_env_reads_total_workflow_payload(self) -> None:
        payload = {
            "api_key": "runtime-key",
            "base_url": "https://runtime.test/v1",
            "model": "runtime-model",
            "timeout_seconds": 30,
            "max_retries": 5,
        }

        with mock.patch.dict(os.environ, {RUNTIME_GENERATION_LLM_ENV: json.dumps(payload)}, clear=False):
            config = LLMConfig.from_runtime_env(RUNTIME_GENERATION_LLM_ENV)

        self.assertEqual(config.api_key, "runtime-key")
        self.assertEqual(config.model, "runtime-model")
        self.assertEqual(config.base_url, "https://runtime.test/v1")
        self.assertEqual(config.temperature, DEFAULT_TEMPERATURE)
        self.assertEqual(config.timeout_seconds, 30)
        self.assertEqual(config.max_retries, 5)


if __name__ == "__main__":
    unittest.main()
