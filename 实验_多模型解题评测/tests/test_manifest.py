from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import path_setup  # noqa: F401
from experiment_core.manifest import (
    ManifestError,
    build_manifest,
    load_and_validate_manifest,
    load_successful_output_problem_set,
)
from helpers import create_successful_output_fixture, create_workflow_fixture, verification_artifact, write_json


class ManifestTests(unittest.TestCase):
    def test_build_manifest_freezes_verified_problem(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_workflow_fixture(root)
            output = root / "manifest.json"

            result = build_manifest(root, output)

            self.assertEqual(result["manifest"]["problem_count"], 1)
            problem = result["manifest"]["problems"][0]
            self.assertEqual(problem["problem_id"], "generated_p1")
            self.assertEqual(problem["pair_id"], "seed_p1")
            self.assertEqual(problem["source"], "codeforces")
            self.assertEqual(problem["test_case_counts"]["large_scale"], 1)
            self.assertTrue(Path(result["exclusion_path"]).is_file())

    def test_build_manifest_excludes_missing_category(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, verification_path, _ = create_workflow_fixture(root)
            payload = verification_artifact()
            payload["bruteforce_verification"]["solved_cases"] = [
                case
                for case in payload["bruteforce_verification"]["solved_cases"]
                if case["source"] != "adversarial"
            ]
            write_json(verification_path, payload)

            result = build_manifest(root, root / "manifest.json")

            self.assertEqual(result["manifest"]["problem_count"], 0)
            self.assertEqual(result["excluded_count"], 1)

    def test_manifest_allows_changed_artifact_without_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            generation_path, _, _ = create_workflow_fixture(root)
            output = root / "manifest.json"
            build_manifest(root, output)
            generation_path.write_text("{}", encoding="utf-8")

            loaded, _ = load_and_validate_manifest(output)

            self.assertEqual(loaded["problem_count"], 1)

    def test_manifest_rejects_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_workflow_fixture(root)
            output = root / "manifest.json"
            build_manifest(root, output)
            manifest_payload = json.loads(output.read_text(encoding="utf-8"))
            manifest_payload["problems"][0]["generation_artifact_path"] = str(root / "missing.json")
            write_json(output, manifest_payload)

            with self.assertRaisesRegex(ManifestError, "冻结产物不存在"):
                load_and_validate_manifest(output)

    def test_duplicate_problem_keeps_latest_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_workflow_fixture(root / "old")
            create_workflow_fixture(root / "new")

            result = build_manifest(root, root / "manifest.json")

            self.assertEqual(result["manifest"]["problem_count"], 1)
            self.assertGreaterEqual(result["excluded_count"], 1)

    def test_build_manifest_from_successful_output_uses_local_copies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            generation_path, verification_path, input_path = create_successful_output_fixture(
                root,
                source_problem_id="seed_success",
                artifact_problem_id="generated_success",
                source="codeforces",
            )
            output = root / "manifest.json"

            result = build_manifest(root, output)
            loaded, _ = load_and_validate_manifest(output)

            self.assertEqual(result["manifest"]["problem_count"], 1)
            self.assertEqual(loaded["problem_count"], 1)
            problem = result["manifest"]["problems"][0]
            self.assertEqual(problem["problem_id"], "generated_success")
            self.assertEqual(problem["artifact_problem_id"], "generated_success")
            self.assertEqual(problem["pair_id"], "seed_success")
            self.assertEqual(problem["source"], "codeforces")
            self.assertEqual(problem["generation_artifact_path"], str(generation_path.resolve()))
            self.assertEqual(problem["verification_artifact_path"], str(verification_path.resolve()))
            self.assertEqual(problem["source_input_path"], str(input_path.resolve()))
            self.assertEqual(result["excluded_count"], 0)

    def test_build_manifest_streams_large_verification_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            create_successful_output_fixture(root)

            with patch("experiment_core.manifest.STREAMING_VERIFICATION_THRESHOLD_BYTES", 1):
                result = build_manifest(root, root / "manifest.json")

            self.assertEqual(result["manifest"]["problem_count"], 1)
            problem = result["manifest"]["problems"][0]
            self.assertEqual(problem["test_case_counts"]["random"], 1)
            self.assertEqual(problem["test_case_counts"]["adversarial"], 1)
            self.assertEqual(problem["test_case_counts"]["small_challenge"], 1)
            self.assertEqual(problem["test_case_counts"]["large_scale"], 1)

    def test_streaming_manifest_excludes_missing_category(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            _, verification_path, _ = create_successful_output_fixture(root)
            payload = verification_artifact()
            payload["bruteforce_verification"]["solved_cases"] = [
                case
                for case in payload["bruteforce_verification"]["solved_cases"]
                if case["source"] != "adversarial"
            ]
            write_json(verification_path, payload)

            with patch("experiment_core.manifest.STREAMING_VERIFICATION_THRESHOLD_BYTES", 1):
                result = build_manifest(root, root / "manifest.json")

            self.assertEqual(result["manifest"]["problem_count"], 0)
            self.assertEqual(result["excluded_count"], 1)

    def test_successful_output_duplicate_artifact_problem_ids_are_kept(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            create_successful_output_fixture(
                root,
                source_problem_id="seed_a",
                artifact_problem_id="duplicate_generated",
            )
            create_successful_output_fixture(
                root,
                source_problem_id="seed_b",
                artifact_problem_id="duplicate_generated",
            )

            result = build_manifest(root, root / "manifest.json")

            problems = result["manifest"]["problems"]
            self.assertEqual(result["manifest"]["problem_count"], 2)
            self.assertEqual({problem["problem_id"] for problem in problems}, {
                "duplicate_generated__seed_a",
                "duplicate_generated__seed_b",
            })
            self.assertEqual({problem["artifact_problem_id"] for problem in problems}, {"duplicate_generated"})

    def test_load_successful_output_problem_set_uses_lightweight_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            generation_path, verification_path, _ = create_successful_output_fixture(root)
            # 直接运行模式不预读验证 JSON 内部真值；内容损坏会在真正评测读取时暴露。
            verification_path.write_text("{", encoding="utf-8")

            problem_set, fingerprint = load_successful_output_problem_set(root)

            self.assertEqual(problem_set["problem_source_type"], "successful_output")
            self.assertEqual(problem_set["problem_count"], 1)
            self.assertTrue(fingerprint)
            problem = problem_set["problems"][0]
            self.assertEqual(problem["problem_id"], "generated_p1")
            self.assertEqual(problem["generation_artifact_path"], str(generation_path.resolve()))
            self.assertEqual(problem["verification_artifact_path"], str(verification_path.resolve()))
            self.assertIn("verification_artifact_mtime_ns", problem)
            self.assertNotIn("test_case_counts", problem)

    def test_load_successful_output_problem_set_excludes_invalid_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            create_successful_output_fixture(root, source_problem_id="valid", artifact_problem_id="generated_valid")
            create_successful_output_fixture(
                root,
                source_problem_id="pending",
                artifact_problem_id="generated_pending",
                problem_status="pending",
            )
            (root / "missing_metadata").mkdir(parents=True)

            problem_set, _ = load_successful_output_problem_set(root)

            self.assertEqual(problem_set["problem_count"], 1)
            self.assertEqual(problem_set["excluded_count"], 2)
            self.assertEqual(problem_set["problems"][0]["problem_id"], "generated_valid")

    def test_load_successful_output_problem_set_duplicate_artifact_ids_are_kept(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            create_successful_output_fixture(root, source_problem_id="seed_a", artifact_problem_id="same_generated")
            create_successful_output_fixture(root, source_problem_id="seed_b", artifact_problem_id="same_generated")

            problem_set, _ = load_successful_output_problem_set(root)

            self.assertEqual({problem["problem_id"] for problem in problem_set["problems"]}, {
                "same_generated__seed_a",
                "same_generated__seed_b",
            })


if __name__ == "__main__":
    unittest.main()
