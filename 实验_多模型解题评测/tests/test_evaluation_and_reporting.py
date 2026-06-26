from __future__ import annotations

from collections import Counter
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from threading import Condition
from typing import Any

import path_setup  # noqa: F401
from experiment_core.evaluation import _evaluate_case, run_experiment
from experiment_core.manifest import build_manifest
from experiment_core.models import InfrastructureError
from experiment_core.reporting import generate_reports
from experiment_core.utils import sha256_file
from helpers import create_workflow_fixture, generation_artifact, verification_artifact, write_json


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


class ParallelProbe:
    def __init__(self, expected_calls: int, wait_seconds: float = 2.0) -> None:
        self.expected_calls = expected_calls
        self.wait_seconds = wait_seconds
        self.condition = Condition()
        self.started = 0
        self.active = 0
        self.active_by_problem: Counter[str] = Counter()
        self.max_active = 0
        self.max_active_problem_count = 0


class ParallelProbeClient:
    def __init__(self, probe: ParallelProbe) -> None:
        self.probe = probe

    def complete(self, *, system_prompt: str, user_prompt: str) -> dict:
        problem_title = "unknown"
        for title in ("concurrent-p1", "concurrent-p2"):
            if title in user_prompt:
                problem_title = title
                break
        try:
            with self.probe.condition:
                self.probe.started += 1
                self.probe.active += 1
                self.probe.active_by_problem[problem_title] += 1
                self.probe.max_active = max(self.probe.max_active, self.probe.active)
                active_problem_count = sum(1 for count in self.probe.active_by_problem.values() if count > 0)
                self.probe.max_active_problem_count = max(
                    self.probe.max_active_problem_count,
                    active_problem_count,
                )
                if self.probe.started >= self.probe.expected_calls:
                    self.probe.condition.notify_all()

                deadline = time.monotonic() + self.probe.wait_seconds
                while self.probe.started < self.probe.expected_calls:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self.probe.condition.wait(remaining)
        finally:
            with self.probe.condition:
                self.probe.active -= 1
                self.probe.active_by_problem[problem_title] -= 1
        return {
            "content": "x = 1",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "duration_seconds": 0.1,
            "api_attempt_count": 1,
            "failed_api_attempts": [],
            "raw_response": {"fake": True},
        }


class EvaluationAndReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["EXPERIMENT_TEST_API_KEY"] = "test-key"

    def _models_file(self, root: Path, ids: list[str], *, concurrency: Any = 1) -> Path:
        path = root / "models.json"
        write_json(
            path,
            {
                "concurrency": concurrency,
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

    def _manifest_file(self, root: Path, problem_count: int) -> Path:
        problems = []
        for index in range(1, problem_count + 1):
            problem_id = f"generated_p{index}"
            generation = generation_artifact(problem_id)
            generation["generated_problem"]["title"] = f"concurrent-p{index}"
            generation_path = root / "artifacts" / f"{problem_id}_generation.json"
            verification_path = root / "artifacts" / f"{problem_id}_verification.json"
            write_json(generation_path, generation)
            write_json(verification_path, verification_artifact())
            problems.append(
                {
                    "problem_id": problem_id,
                    "problem_kind": "generated",
                    "pair_id": f"seed_p{index}",
                    "source": "unit-test",
                    "title": generation["generated_problem"]["title"],
                    "applied_rule": "rule_a",
                    "changed_axes": [],
                    "algorithm_tags": [],
                    "generation_artifact_path": str(generation_path),
                    "generation_artifact_sha256": sha256_file(generation_path),
                    "verification_artifact_path": str(verification_path),
                    "verification_artifact_sha256": sha256_file(verification_path),
                }
            )
        manifest_path = root / "manifest.json"
        write_json(
            manifest_path,
            {
                "schema_version": 1,
                "created_at": "2026-01-01T00:00:00+00:00",
                "workflow_output_root": str(root),
                "problem_count": len(problems),
                "problems": problems,
                "content_fingerprint": "unit-test",
            },
        )
        return manifest_path

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

    def test_two_level_concurrency_runs_multiple_problems_and_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = self._manifest_file(root, 2)
            models_path = self._models_file(
                root,
                ["m1", "m2", "m3"],
                concurrency={"problems": 2, "models_per_problem": 3},
            )
            probe = ParallelProbe(expected_calls=6)

            summary = run_experiment(
                manifest_path=manifest_path,
                models_path=models_path,
                output_root=root / "output",
                run_id="run",
                client_factory=lambda _config: ParallelProbeClient(probe),
            )
            metadata = json.loads((root / "output" / "run" / "run_metadata.json").read_text(encoding="utf-8"))

            self.assertEqual(summary["job_count"], 6)
            self.assertEqual(summary["completed_count"], 6)
            self.assertEqual(summary["infrastructure_error_count"], 0)
            self.assertEqual(probe.max_active, 6)
            self.assertEqual(probe.max_active_problem_count, 2)
            self.assertEqual(metadata["concurrency"]["effective"]["problem_workers"], 2)
            self.assertEqual(metadata["concurrency"]["effective"]["models_per_problem"], 3)
            self.assertEqual(metadata["concurrency"]["effective"]["max_model_workers"], 6)

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
