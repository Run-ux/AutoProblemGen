from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import path_setup  # noqa: F401
from experiment_core.models import load_model_configs
from helpers import write_json


class ModelConfigTests(unittest.TestCase):
    def test_loads_inline_api_key_without_public_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "models.json"
            write_json(
                path,
                {
                    "concurrency": 1,
                    "models": [
                        {
                            "id": "inline-key-model",
                            "model": "fake-model",
                            "base_url": "https://example.com/v1",
                            "api_key": " inline-test-key ",
                            "temperature": 0,
                        }
                    ],
                },
            )

            models, concurrency = load_model_configs(path)

            self.assertEqual(concurrency, 1)
            self.assertEqual(models[0].api_key, "inline-test-key")
            public_payload = json.dumps(models[0].public_dict(), ensure_ascii=False)
            self.assertNotIn("api_key", public_payload)
            self.assertNotIn("inline-test-key", public_payload)

    def test_inline_api_key_value_does_not_affect_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "models.json"
            payload = {
                "models": [
                    {
                        "id": "m1",
                        "model": "fake-model",
                        "base_url": "https://example.com/v1",
                        "api_key": "first-key",
                    }
                ]
            }
            write_json(path, payload)
            first_fingerprint = load_model_configs(path)[0][0].fingerprint
            payload["models"][0]["api_key"] = "second-key"
            write_json(path, payload)

            second_fingerprint = load_model_configs(path)[0][0].fingerprint

            self.assertEqual(first_fingerprint, second_fingerprint)


if __name__ == "__main__":
    unittest.main()
