from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import path_setup  # noqa: F401
from experiment_core.models import ModelConfigError, load_model_configs
from helpers import write_json


class ModelConfigTests(unittest.TestCase):
    def _write_models(self, path: Path, concurrency: Any) -> None:
        write_json(
            path,
            {
                "concurrency": concurrency,
                "models": [
                    {
                        "id": "m1",
                        "model": "fake-model",
                        "base_url": "https://example.com/v1",
                        "api_key": "test-key",
                    }
                ],
            },
        )

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

            self.assertEqual(concurrency.problem_workers, 1)
            self.assertEqual(concurrency.models_per_problem, 1)
            self.assertEqual(models[0].api_key, "inline-test-key")
            public_payload = json.dumps(models[0].public_dict(), ensure_ascii=False)
            self.assertNotIn("api_key", public_payload)
            self.assertNotIn("inline-test-key", public_payload)

    def test_loads_object_concurrency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "models.json"
            self._write_models(path, {"problems": 200, "models_per_problem": 6})

            _models, concurrency = load_model_configs(path)

            self.assertEqual(concurrency.problem_workers, 200)
            self.assertEqual(concurrency.models_per_problem, 6)
            self.assertEqual(
                concurrency.public_dict(),
                {
                    "raw": {"problems": 200, "models_per_problem": 6},
                    "problems": 200,
                    "models_per_problem": 6,
                },
            )

    def test_rejects_invalid_concurrency(self) -> None:
        invalid_values = [
            0,
            True,
            "2",
            {"problems": 1},
            {"problems": 0, "models_per_problem": 1},
            {"problems": 1, "models_per_problem": "6"},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index, concurrency in enumerate(invalid_values):
                path = root / f"models_{index}.json"
                self._write_models(path, concurrency)

                with self.assertRaises(ModelConfigError):
                    load_model_configs(path)

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
