from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import path_setup  # noqa: F401
from experiment_core.manifest import ManifestError, build_manifest, load_and_validate_manifest
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

    def test_manifest_rejects_changed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            generation_path, _, _ = create_workflow_fixture(root)
            output = root / "manifest.json"
            build_manifest(root, output)
            generation_path.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "hash 已变化"):
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


if __name__ == "__main__":
    unittest.main()
