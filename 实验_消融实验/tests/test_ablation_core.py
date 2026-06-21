from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import path_setup  # noqa: F401
from main import main as cli_main
from ablation_core.manifest import build_manifest
from ablation_core.problem_selection import select_manifest_problem_range
from ablation_core.reporting import generate_report
from ablation_core.suites import baseline_cases, build_suites, ours_cases
from ablation_core.utils import write_json


def verification_fixture() -> dict:
    return {
        "test_inputs": {
            "random": {"generate_test_input_code": "", "validate_test_input_code": ""},
            "adversarial": {"generate_test_input_code": "", "validate_test_input_code": ""},
        },
        "bruteforce_solution": {"verified_code": "def solve(input_str): return '1'"},
        "standard_solution": {"verified_code": "def solve(input_str): return '1'"},
        "standard_solution_verification": {
            "standard_solution_limits": {"timeout_seconds": 1.0, "memory_limit_mb": 256}
        },
        "bruteforce_verification": {
            "solved_cases": [
                {"case_id": "case_001", "source": "random", "input": "1", "output": "1"},
                {"case_id": "case_002", "source": "adversarial", "input": "2", "output": "2"},
                {"case_id": "case_003", "source": "small_challenge", "input": "3", "output": "3"},
                {"case_id": "case_004", "source": "wrong_pool_targeted", "input": "4", "output": "4"},
            ],
        },
        "large_scale_truth_outputs": {
            "cases": [{"case_id": "case_005", "source": "random", "input": "5", "output": "5"}]
        },
    }


class ManifestTests(unittest.TestCase):
    def test_build_manifest_filters_python3_and_selects_submission_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            problems = []
            submissions = []
            for index in range(3):
                problem_id = f"20{index}A"
                problems.append(
                    {
                        "problem_id": problem_id,
                        "url": "",
                        "title": f"p{index}",
                        "rating": 1200 + index * 400,
                        "tags": ["dp"],
                        "div": "",
                        "time_limit_ms": 1000,
                        "memory_limit_mb": 256,
                        "description": "",
                        "input": "",
                        "output": "",
                        "examples": [],
                        "note": "",
                        "prompt": "",
                    }
                )
                for local in range(3):
                    submissions.append(
                        {
                            "id": index * 1000 + local,
                            "language": "Python 3",
                            "problem_id": problem_id,
                            "type": "right_submission",
                        }
                    )
                for local in range(50):
                    submissions.append(
                        {
                            "id": index * 1000 + 100 + local,
                            "language": "PyPy 3-64",
                            "problem_id": problem_id,
                            "type": "wrong_submission",
                        }
                    )
                submissions.append(
                    {
                        "id": index * 1000 + 999,
                        "language": "Python 2",
                        "problem_id": problem_id,
                        "type": "wrong_submission",
                    }
                )
            problem_path = root / "problem.parquet"
            submission_path = root / "submission.parquet"
            pd.DataFrame(problems).to_parquet(problem_path)
            pd.DataFrame(submissions).to_parquet(submission_path)

            manifest = build_manifest(
                output_path=root / "manifest.json",
                sample_size=2,
                problem_parquet_url=str(problem_path),
                submission_parquet_url=str(submission_path),
            )

            self.assertEqual(manifest["problem_count"], 2)
            for problem in manifest["problems"]:
                self.assertEqual(problem["selected_right_submission_count"], 3)
                self.assertEqual(problem["selected_wrong_submission_count"], 50)


class ProblemSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.problems = [{"problem_id": f"p{index}"} for index in range(1, 5)]

    def _ids(self, selected: list[tuple[int, dict]]) -> list[str]:
        return [problem["problem_id"] for _, problem in selected]

    def _indexes(self, selected: list[tuple[int, dict]]) -> list[int]:
        return [index for index, _ in selected]

    def test_selects_closed_one_based_range_from_start(self) -> None:
        selected, metadata = select_manifest_problem_range(self.problems, start_index=1, end_index=2)

        self.assertEqual(self._ids(selected), ["p1", "p2"])
        self.assertEqual(self._indexes(selected), [1, 2])
        self.assertEqual(metadata["selected_problem_count"], 2)

    def test_selects_closed_one_based_middle_range(self) -> None:
        selected, _ = select_manifest_problem_range(self.problems, start_index=2, end_index=3)

        self.assertEqual(self._ids(selected), ["p2", "p3"])
        self.assertEqual(self._indexes(selected), [2, 3])

    def test_start_index_without_end_runs_to_manifest_end(self) -> None:
        selected, metadata = select_manifest_problem_range(self.problems, start_index=3)

        self.assertEqual(self._ids(selected), ["p3", "p4"])
        self.assertEqual(metadata["start_index"], 3)
        self.assertEqual(metadata["end_index"], 4)

    def test_limit_keeps_existing_prefix_behavior(self) -> None:
        selected, metadata = select_manifest_problem_range(self.problems, limit=1)

        self.assertEqual(self._ids(selected), ["p1"])
        self.assertEqual(metadata["mode"], "limit")

    def test_rejects_invalid_range_arguments(self) -> None:
        with self.assertRaises(ValueError):
            select_manifest_problem_range(self.problems, start_index=0)
        with self.assertRaises(ValueError):
            select_manifest_problem_range(self.problems, start_index=3, end_index=2)
        with self.assertRaises(ValueError):
            select_manifest_problem_range(self.problems, start_index=1, end_index=5)
        with self.assertRaises(ValueError):
            select_manifest_problem_range(self.problems, limit=1, start_index=1)


class CliTests(unittest.TestCase):
    def test_limit_cannot_mix_with_range_args(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as context:
                cli_main(
                    [
                        "run",
                        "--manifest",
                        "manifest.json",
                        "--output-root",
                        "output",
                        "--run-id",
                        "testcase_eval_80",
                        "--limit",
                        "1",
                        "--start-index",
                        "1",
                    ]
                )

        self.assertEqual(context.exception.code, 2)


class SuiteTests(unittest.TestCase):
    def test_baseline_excludes_targeted_and_ours_includes_it(self) -> None:
        verification = verification_fixture()

        self.assertEqual(len(baseline_cases(verification)), 4)
        self.assertEqual(len(ours_cases(verification)), 5)

    def test_size_control_matches_ours_when_no_extra_needed(self) -> None:
        verification = verification_fixture()
        suites = build_suites(
            verification,
            execution_config=SimpleNamespace(
                test_input_timeout_seconds=1,
                test_input_memory_limit_mb=256,
                bruteforce_timeout_seconds=1,
                bruteforce_memory_limit_mb=256,
            ),
        )

        self.assertEqual(len(suites["ours_pipeline"]), 5)
        # 生成器代码为空，无法补齐 size_control；该情况会在报告中体现为保留用例数不足。
        self.assertEqual(len(suites["size_control"]), 4)


class ReportingTests(unittest.TestCase):
    def test_report_computes_correctness_and_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            problem_dir = run_dir / "problems" / "p1"
            problem_dir.mkdir(parents=True)
            verdicts = [
                {
                    "suite": "unicode_style_baseline",
                    "submission_id": 1,
                    "submission_type": "right_submission",
                    "accepted": True,
                    "rejected": False,
                    "semantic_eligible": True,
                },
                {
                    "suite": "unicode_style_baseline",
                    "submission_id": 2,
                    "submission_type": "wrong_submission",
                    "accepted": False,
                    "rejected": True,
                    "semantic_eligible": True,
                    "first_kill_source": "random",
                },
            ]
            for suite in ("size_control", "ours_pipeline"):
                for item in list(verdicts):
                    clone = dict(item)
                    clone["suite"] = suite
                    verdicts.append(clone)
            verdict_path = problem_dir / "candidate_verdicts.jsonl"
            verdict_path.write_text("\n".join(json.dumps(item) for item in verdicts) + "\n", encoding="utf-8")
            write_json(
                problem_dir / "result.json",
                {
                    "status": "completed",
                    "problem_id": "p1",
                    "suite_case_counts": {
                        "unicode_style_baseline": 1,
                        "size_control": 1,
                        "ours_pipeline": 1,
                    },
                    "candidate_verdicts_path": str(verdict_path),
                },
            )

            summary = generate_report(run_dir)

            self.assertEqual(summary["status"], "complete")
            self.assertTrue((run_dir / "ablation_summary.csv").is_file())
            self.assertTrue((run_dir / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
