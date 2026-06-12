from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import path_setup  # noqa: F401
from experiment_core.evaluation import _evaluate_case, run_experiment
from experiment_core.manifest import build_manifest
from experiment_core.models import InfrastructureError
from experiment_core.reporting import generate_reports
from helpers import create_workflow_fixture, write_json


class FakeClient:
    def __init__(self, content: str, *, fail_once: bool = False) -> None:
        self.content = content
        self.fail_once = fail_once
        self.calls = 0

    def complete(self, *, system_prompt: str, user_prompt: str) -> dict:
        self.calls += 1
        if self.fail_once and self.calls == 1:
            raise InfrastructureError("temporary network failure")
        return {
            "content": self.content,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "duration_seconds": 0.1,
            "api_attempt_count": 1,
            "failed_api_attempts": [],
            "raw_response": {"fake": True},
        }


class EvaluationAndReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["EXPERIMENT_TEST_API_KEY"] = "test-key"

    def _models_file(self, root: Path, ids: list[str]) -> Path:
        path = root / "models.json"
        write_json(
            path,
            {
                "concurrency": 1,
                "models": [
                    {
                        "id": model_id,
                        "model": "fake-model",
                        "api_key_env": "EXPERIMENT_TEST_API_KEY",
                        "temperature": 0,
                    }
                    for model_id in ids
                ],
            },
        )
        return path

    def test_case_evaluation_supports_checker_and_wrong_answer(self) -> None:
        case = {"case_id": "c1", "category": "random", "input": "x\n", "output": "ok\n"}
        checker = "def check_output(input_str, output_str):\n    return output_str.strip().lower() == 'ok'"
        accepted = _evaluate_case(
            "def solve(input_str):\n    return 'OK\\n'",
            case,
            checker_code=checker,
            timeout_seconds=1,
            memory_limit_mb=256,
            checker_timeout_seconds=1,
            checker_memory_limit_mb=256,
        )
        wrong = _evaluate_case(
            "def solve(input_str):\n    return 'bad\\n'",
            case,
            checker_code=None,
            timeout_seconds=1,
            memory_limit_mb=256,
            checker_timeout_seconds=1,
            checker_memory_limit_mb=256,
        )
        self.assertTrue(accepted["passed"])
        self.assertEqual(wrong["classification"], "wrong_answer")

    def test_infrastructure_error_is_retried_on_next_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_workflow_fixture(root / "workflow")
            manifest_path = root / "manifest.json"
            build_manifest(root / "workflow", manifest_path)
            models_path = self._models_file(root, ["m1"])
            client = FakeClient("def solve(input_str):\n    return 'ok\\n'", fail_once=True)

            first = run_experiment(
                manifest_path=manifest_path,
                models_path=models_path,
                output_root=root / "output",
                run_id="run",
                client_factory=lambda _config: client,
            )
            second = run_experiment(
                manifest_path=manifest_path,
                models_path=models_path,
                output_root=root / "output",
                run_id="run",
                client_factory=lambda _config: client,
            )

            self.assertEqual(first["infrastructure_error_count"], 1)
            self.assertEqual(second["infrastructure_error_count"], 0)
            self.assertEqual(client.calls, 2)

    def test_end_to_end_reports_pass_rate_and_difficulty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_workflow_fixture(root / "workflow")
            manifest_path = root / "manifest.json"
            build_manifest(root / "workflow", manifest_path)
            models_path = self._models_file(root, ["m1", "m2", "m3"])

            def factory(config):
                output = "ok\n" if config.model_id in {"m1", "m2"} else "bad\n"
                return FakeClient(f"def solve(input_str):\n    return {output!r}")

            run_experiment(
                manifest_path=manifest_path,
                models_path=models_path,
                output_root=root / "output",
                run_id="run",
                client_factory=factory,
            )
            run_dir = root / "output" / "run"
            summary = generate_reports(run_dir)
            difficulty_rows = (run_dir / "problem_difficulty.csv").read_text(encoding="utf-8-sig")

            self.assertEqual(summary["status"], "complete")
            self.assertTrue(summary["difficulty_available"])
            self.assertIn("easy", difficulty_rows)
            self.assertTrue((run_dir / "model_summary.csv").is_file())
            self.assertTrue((run_dir / "group_summary.csv").is_file())
            self.assertTrue((run_dir / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
