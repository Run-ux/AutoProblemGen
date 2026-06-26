from __future__ import annotations

import json
import shutil
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

try:
    from . import path_setup  # noqa: F401
except ImportError:
    import path_setup  # noqa: F401
from main import main as cli_main
from ablation_core.manifest import build_manifest
from ablation_core.pipeline import _evaluate_problem
from ablation_core.problem_selection import select_manifest_problem_range
from ablation_core.reporting import generate_report
from ablation_core.submission_execution import (
    EXECUTION_ERROR,
    EXECUTION_OK,
    EXECUTION_TIMEOUT,
    evaluate_submission_on_cases,
    run_submission_script,
)
from ablation_core.suites import baseline_cases, build_suites, ours_cases
from ablation_core.utils import read_json, write_json
from ablation_core.wrong_pool_backfill import backfill_wrong_pool_run


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

    def test_build_manifest_filters_language_and_excludes_existing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            problems = []
            submissions = []
            for index, problem_id in enumerate(["excludedA", "cpp17A", "cpp20A"]):
                problems.append(
                    {
                        "problem_id": problem_id,
                        "url": "",
                        "title": problem_id,
                        "rating": 1200,
                        "tags": ["implementation"],
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
                language = "C++20 (GCC 13-64)" if problem_id == "cpp20A" else "C++17 (GCC 7-32)"
                submissions.extend(
                    [
                        {
                            "id": index * 1000 + 1,
                            "language": language,
                            "problem_id": problem_id,
                            "type": "right_submission",
                        },
                        {
                            "id": index * 1000 + 2,
                            "language": language,
                            "problem_id": problem_id,
                            "type": "wrong_submission",
                        },
                    ]
                )
            problem_path = root / "problem.parquet"
            submission_path = root / "submission.parquet"
            exclude_path = root / "exclude.json"
            pd.DataFrame(problems).to_parquet(problem_path)
            pd.DataFrame(submissions).to_parquet(submission_path)
            write_json(
                exclude_path,
                {
                    "schema_version": 1,
                    "content_fingerprint": "base-fingerprint",
                    "problems": [{"problem_id": "excludedA"}],
                },
            )

            manifest = build_manifest(
                output_path=root / "manifest.json",
                sample_size=1,
                min_right=1,
                min_wrong=1,
                language_regex=r"C\+\+14|C\+\+17",
                exclude_manifest_path=exclude_path,
                problem_parquet_url=str(problem_path),
                submission_parquet_url=str(submission_path),
            )

            self.assertEqual(manifest["problem_count"], 1)
            self.assertEqual(manifest["problems"][0]["problem_id"], "cpp17A")
            self.assertEqual(manifest["filters"]["language_regex"], r"C\+\+14|C\+\+17")
            self.assertEqual(manifest["filters"]["exclude_manifest_path"], str(exclude_path))
            self.assertEqual(manifest["filters"]["exclude_manifest_content_fingerprint"], "base-fingerprint")


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


class SubmissionExecutionTests(unittest.TestCase):
    def test_normal_submission_returns_ok(self) -> None:
        result = run_submission_script(
            "import sys\nprint(sys.stdin.readline().strip())",
            "hello\n",
            timeout_seconds=1.0,
            memory_limit_mb=256,
        )

        self.assertEqual(result.status, EXECUTION_OK)
        self.assertEqual(result.stdout.strip(), "hello")

    def test_infinite_loop_is_killed_by_timeout(self) -> None:
        start = time.monotonic()
        result = run_submission_script(
            "while True:\n    pass",
            "",
            timeout_seconds=0.5,
            memory_limit_mb=256,
        )

        self.assertEqual(result.status, EXECUTION_TIMEOUT)
        self.assertLess(time.monotonic() - start, 5.0)

    def test_non_reading_process_with_large_stdin_is_killed_by_timeout(self) -> None:
        start = time.monotonic()
        result = run_submission_script(
            "while True:\n    pass",
            "x" * (1024 * 1024),
            timeout_seconds=0.5,
            memory_limit_mb=256,
        )

        self.assertEqual(result.status, EXECUTION_TIMEOUT)
        self.assertLess(time.monotonic() - start, 5.0)

    def _evaluate_cpp(self, source: str, *, timeout_seconds: float = 1.0) -> dict:
        with tempfile.TemporaryDirectory() as temp_dir:
            return evaluate_submission_on_cases(
                submission={
                    "id": 1,
                    "language": "C++17 (GCC 7-32)",
                    "type": "right_submission",
                    "source": source,
                },
                suite_name="unicode_style_baseline",
                cases=[{"case_id": "case_001", "source": "random", "input": "hello\n", "output": "hello\n"}],
                timeout_seconds=timeout_seconds,
                memory_limit_mb=256,
                submission_cache_dir=Path(temp_dir),
            )

    @unittest.skipUnless(shutil.which("g++"), "需要 g++")
    def test_cpp_submission_returns_ok(self) -> None:
        result = self._evaluate_cpp(
            "#include <bits/stdc++.h>\n"
            "using namespace std;\n"
            "int main(){string s; getline(cin, s); cout << s << '\\n';}\n"
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["first_failure_kind"], "")

    @unittest.skipUnless(shutil.which("g++"), "需要 g++")
    def test_cpp_wrong_answer_is_rejected(self) -> None:
        result = self._evaluate_cpp(
            "#include <bits/stdc++.h>\n"
            "using namespace std;\n"
            "int main(){cout << \"wrong\" << '\\n';}\n"
        )

        self.assertFalse(result["accepted"])
        self.assertEqual(result["first_failure_kind"], "wrong_answer")
        self.assertTrue(result["semantic_eligible"])

    @unittest.skipUnless(shutil.which("g++"), "需要 g++")
    def test_cpp_infinite_loop_is_killed_by_timeout(self) -> None:
        start = time.monotonic()
        result = self._evaluate_cpp(
            "#include <bits/stdc++.h>\nint main(){while(true){}}\n",
            timeout_seconds=0.5,
        )

        self.assertFalse(result["accepted"])
        self.assertEqual(result["first_failure_kind"], EXECUTION_TIMEOUT)
        self.assertLess(time.monotonic() - start, 5.0)

    @unittest.skipUnless(shutil.which("g++"), "需要 g++")
    def test_cpp_compile_error_is_recorded(self) -> None:
        result = self._evaluate_cpp("#include <bits/stdc++.h>\nint main(){ syntax error }\n")

        self.assertFalse(result["accepted"])
        self.assertEqual(result["first_failure_kind"], EXECUTION_ERROR)
        self.assertIn("error", result["case_results"][0]["execution"]["stderr"].lower())


class ResumeTests(unittest.TestCase):
    def _problem(self, problem_id: str = "p1") -> dict:
        return {
            "problem_id": problem_id,
            "right_submission_ids": [1],
            "wrong_submission_ids": [],
        }

    def _runtime(self) -> dict:
        return {
            "generation_llm": object(),
            "llm_config": object(),
            "execution_config": SimpleNamespace(),
            "context_limits": object(),
        }

    def _evaluate(self, run_dir: Path, problem_id: str = "p1", resume: bool = True) -> dict:
        return _evaluate_problem(
            problem=self._problem(problem_id),
            problem_row={"problem_id": problem_id},
            submissions_by_id={
                1: {
                    "id": 1,
                    "language": "Python 3",
                    "type": "right_submission",
                    "source": "print('ok')",
                }
            },
            run_dir=run_dir,
            runtime=self._runtime(),
            resume=resume,
        )

    def test_completed_result_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            problem_dir = run_dir / "problems" / "p1"
            write_json(problem_dir / "result.json", {"status": "completed", "problem_id": "p1"})

            result = self._evaluate(run_dir)

            self.assertEqual(result["status"], "completed")

    def test_failed_result_is_skipped_without_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            problem_dir = run_dir / "problems" / "p1"
            write_json(problem_dir / "result.json", {"status": "failed", "problem_id": "p1"})

            result = self._evaluate(run_dir)

            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["existing_status"], "failed")

    def test_problem_directory_without_result_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            (run_dir / "problems" / "p1").mkdir(parents=True)

            result = self._evaluate(run_dir)

            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["skip_reason"], "problem_dir_without_result")

    def test_invalid_result_json_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            problem_dir = run_dir / "problems" / "p1"
            problem_dir.mkdir(parents=True)
            (problem_dir / "result.json").write_text("{", encoding="utf-8")

            result = self._evaluate(run_dir)

            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["skip_reason"], "invalid_result_json")

    def test_new_problem_runs_and_writes_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            verification = verification_fixture()
            with (
                patch("ablation_core.pipeline.extract_tuple_snapshot", return_value={}),
                patch("ablation_core.pipeline.artifact_from_problem", return_value={}),
                patch("ablation_core.pipeline.generate_verified_artifacts", return_value=verification),
                patch(
                    "ablation_core.pipeline.build_suites",
                    return_value={
                        "unicode_style_baseline": [{"case_id": "c1", "input": "", "output": ""}],
                        "size_control": [{"case_id": "c1", "input": "", "output": ""}],
                        "ours_pipeline": [{"case_id": "c1", "input": "", "output": ""}],
                    },
                ),
                patch(
                    "ablation_core.pipeline.evaluate_submission_on_cases",
                    return_value={
                        "suite": "unicode_style_baseline",
                        "submission_id": 1,
                        "submission_type": "right_submission",
                        "accepted": True,
                    },
                ),
            ):
                result = self._evaluate(run_dir, problem_id="fresh")

            self.assertEqual(result["status"], "completed")
            self.assertTrue((run_dir / "problems" / "fresh" / "result.json").is_file())
            self.assertTrue((run_dir / "problems" / "fresh" / "candidate_verdicts.jsonl").is_file())


class WrongPoolBackfillTests(unittest.TestCase):
    def test_backfill_updates_completed_problem_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            write_json(
                run_dir / "run_metadata.json",
                {
                    "manifest_path": str(run_dir / "manifest.json"),
                    "workflow_config_path": str(run_dir / "workflow.env"),
                },
            )
            problem_dir = run_dir / "problems" / "p1"
            failed_dir = run_dir / "problems" / "p2"
            write_json(
                problem_dir / "result.json",
                {
                    "status": "completed",
                    "problem_id": "p1",
                    "right_submission_ids": [1],
                    "wrong_submission_ids": [2],
                    "suite_case_counts": {"unicode_style_baseline": 1, "ours_pipeline": 1, "size_control": 1},
                },
            )
            write_json(failed_dir / "result.json", {"status": "failed", "problem_id": "p2"})
            write_json(problem_dir / "artifact.json", {"problem": "p1"})
            write_json(
                problem_dir / "verification.json",
                {
                    "wrong_solutions": {"fixed_categories": {}},
                    "test_inputs": {
                        "random": {"generate_test_input_code": "", "validate_test_input_code": ""},
                        "adversarial": {"generate_test_input_code": "", "validate_test_input_code": ""},
                    },
                    "checker": {"needs_checker": False},
                    "checker_verification": {},
                    "verified_test_inputs": {
                        "cases": [{"case_id": "case_001", "source": "random", "input": "1"}],
                        "count": 1,
                        "source_counts": {"random": 1},
                    },
                    "bruteforce_verification": {
                        "final_code": "def solve(input_str): return input_str",
                        "solved_cases": [{"case_id": "case_001", "source": "random", "input": "1", "output": "1"}],
                        "solved_case_count": 1,
                    },
                    "standard_solution_verification": {
                        "standard_solution_limits": {"timeout_seconds": 1.0, "memory_limit_mb": 256}
                    },
                    "wrong_solution_pool_verification": {"targeted_input_count": 0},
                    "execution_metadata": {"verified_test_input_count": 1, "solved_case_count": 1},
                },
            )
            wrong_pool_result = {
                "verification": {
                    "status": "ok",
                    "targeted_input_count": 1,
                    "killed_count": 1,
                    "survived_count": 0,
                    "invalid_count": 0,
                },
                "verified_test_inputs": {
                    "cases": [
                        {"case_id": "case_001", "source": "random", "input": "1"},
                        {"case_id": "case_002", "source": "wrong_pool_targeted", "input": "2"},
                    ],
                    "count": 2,
                    "source_counts": {"random": 1, "wrong_pool_targeted": 1},
                },
                "solved_cases": [
                    {"case_id": "case_001", "source": "random", "input": "1", "output": "1"},
                    {"case_id": "case_002", "source": "wrong_pool_targeted", "input": "2", "output": "2"},
                ],
            }
            suites = {
                "unicode_style_baseline": [{"case_id": "case_001", "source": "random", "input": "1", "output": "1"}],
                "ours_pipeline": [
                    {"case_id": "case_001", "source": "random", "input": "1", "output": "1"},
                    {"case_id": "case_002", "source": "wrong_pool_targeted", "input": "2", "output": "2"},
                ],
                "size_control": [
                    {"case_id": "case_001", "source": "random", "input": "1", "output": "1"},
                    {"case_id": "size_control_002", "source": "size_control_random:bruteforce", "input": "3", "output": "3"},
                ],
            }

            with (
                patch(
                    "ablation_core.wrong_pool_backfill.load_manifest",
                    return_value={
                        "submission_parquet_url": "submissions.parquet",
                        "problems": [
                            {
                                "problem_id": "p1",
                                "rating": 800,
                                "right_submission_ids": [1],
                                "wrong_submission_ids": [2],
                            }
                        ],
                    },
                ),
                patch(
                    "ablation_core.wrong_pool_backfill.load_runtime_config",
                    return_value={
                        "llm_config": object(),
                        "execution_config": SimpleNamespace(),
                        "context_limits": SimpleNamespace(),
                    },
                ),
                patch("ablation_core.wrong_pool_backfill.OpenAIChatLLMClient", return_value=object()),
                patch("ablation_core.wrong_pool_backfill._submission_rows", return_value={1: {"id": 1}, 2: {"id": 2}}),
                patch("ablation_core.wrong_pool_backfill.verify_wrong_solution_pool", return_value=wrong_pool_result),
                patch("ablation_core.wrong_pool_backfill.build_suites", return_value=suites),
                patch(
                    "ablation_core.wrong_pool_backfill.evaluate_submission_on_cases",
                    side_effect=lambda submission, suite_name, **kwargs: {
                        "suite": suite_name,
                        "submission_id": submission["id"],
                        "submission_type": "right_submission",
                        "accepted": True,
                    },
                ),
                patch("ablation_core.wrong_pool_backfill.generate_report", return_value={"status": "complete"}),
            ):
                summary = backfill_wrong_pool_run(run_dir=run_dir)

            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["backfilled_problem_count"], 1)
            self.assertEqual(summary["failed_problem_count"], 0)

            verification = read_json(problem_dir / "verification.json")
            self.assertEqual(verification["wrong_solution_pool_verification"]["targeted_input_count"], 1)
            self.assertEqual(verification["verified_test_inputs"]["count"], 2)
            self.assertEqual(verification["bruteforce_verification"]["solved_case_count"], 2)
            self.assertEqual(verification["execution_metadata"]["wrong_solution_pool_targeted_input_count"], 1)

            rebuilt_suites = read_json(problem_dir / "suites.json")
            self.assertEqual(len(rebuilt_suites["ours_pipeline"]), 2)
            self.assertEqual(len(rebuilt_suites["size_control"]), 2)

            result = read_json(problem_dir / "result.json")
            self.assertEqual(result["suite_case_counts"]["ours_pipeline"], 2)
            self.assertEqual(result["wrong_pool_backfill"]["suite_wrong_pool_targeted_count"], 1)
            verdict_lines = (problem_dir / "candidate_verdicts.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(verdict_lines), 6)
            self.assertEqual(read_json(failed_dir / "result.json")["status"], "failed")


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
