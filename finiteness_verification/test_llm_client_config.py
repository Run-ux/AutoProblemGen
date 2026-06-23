from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from finiteness_verification.llm_client import LLMClient


class LLMClientConfigTests(unittest.TestCase):
    def test_loads_model_config_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "LLM_BASE_URL=https://example.test/v1",
                        "LLM_API_KEY=file-chat-key",
                        "LLM_MODEL=file-chat-model",
                        "EMBEDDING_BASE_URL=https://embedding.example.test/v1",
                        "EMBEDDING_API_KEY=file-embedding-key",
                        "EMBEDDING_MODEL=file-embedding-model",
                        "LLM_TIMEOUT_S=123",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"LLM_ENV_FILE": str(env_file)}, clear=True):
                client = LLMClient()

        self.assertEqual(client.base_url, "https://example.test/v1")
        self.assertEqual(client.api_key, "file-chat-key")
        self.assertEqual(client.model, "file-chat-model")
        self.assertEqual(client.embedding_base_url, "https://embedding.example.test/v1")
        self.assertEqual(client.embedding_api_key, "file-embedding-key")
        self.assertEqual(client.embedding_model, "file-embedding-model")
        self.assertEqual(client.timeout_s, 123)

    def test_system_environment_overrides_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "LLM_BASE_URL=https://file.test/v1",
                        "LLM_API_KEY=file-chat-key",
                        "LLM_MODEL=file-chat-model",
                        "EMBEDDING_BASE_URL=https://embedding-file.test/v1",
                        "EMBEDDING_API_KEY=file-embedding-key",
                        "EMBEDDING_MODEL=file-embedding-model",
                    ]
                ),
                encoding="utf-8",
            )
            env = {
                "LLM_ENV_FILE": str(env_file),
                "LLM_BASE_URL": "https://system.test/v1",
                "LLM_API_KEY": "system-chat-key",
                "LLM_MODEL": "system-chat-model",
                "EMBEDDING_BASE_URL": "https://embedding-system.test/v1",
                "EMBEDDING_API_KEY": "system-embedding-key",
                "EMBEDDING_MODEL": "system-embedding-model",
            }

            with patch.dict(os.environ, env, clear=True):
                client = LLMClient()

        self.assertEqual(client.base_url, "https://system.test/v1")
        self.assertEqual(client.api_key, "system-chat-key")
        self.assertEqual(client.model, "system-chat-model")
        self.assertEqual(client.embedding_base_url, "https://embedding-system.test/v1")
        self.assertEqual(client.embedding_api_key, "system-embedding-key")
        self.assertEqual(client.embedding_model, "system-embedding-model")
        self.assertEqual(client.timeout_s, 300)

    def test_missing_required_config_fails_fast_without_provider_name(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "finiteness_verification.llm_client.load_env_file_values",
            return_value={},
        ):
            with self.assertRaises(RuntimeError) as ctx:
                LLMClient()

        message = str(ctx.exception)
        self.assertIn("LLM_BASE_URL", message)
        self.assertIn("LLM_API_KEY", message)
        self.assertIn("LLM_MODEL", message)
        self.assertIn("EMBEDDING_BASE_URL", message)
        self.assertIn("EMBEDDING_API_KEY", message)
        self.assertIn("EMBEDDING_MODEL", message)
        forbidden_names = [
            "Q" + "wen",
            "q" + "wen",
            "DASH" + "SCOPE",
            "Q" + "WEN",
            "\u5343\u95ee",
        ]
        for forbidden_name in forbidden_names:
            self.assertNotIn(forbidden_name, message)


if __name__ == "__main__":
    unittest.main()
