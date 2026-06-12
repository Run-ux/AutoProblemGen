import json
import tempfile
import unittest
from pathlib import Path

from taco_prepare_sample import load_excluded_problem_ids_from_dirs


class LoadExcludedProblemIdsFromDirsTest(unittest.TestCase):
    def test_merge_multiple_directories_and_count_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_dir = root / "first"
            second_dir = root / "second"
            first_dir.mkdir()
            second_dir.mkdir()

            self._write_problem(first_dir / "001.json", "problem-a")
            self._write_problem(first_dir / "002.json", "problem-a")
            self._write_problem(first_dir / "003.json", "problem-b")
            self._write_problem(second_dir / "001.json", "problem-b")
            self._write_problem(second_dir / "002.json", "problem-c")

            problem_ids, report = load_excluded_problem_ids_from_dirs(
                [first_dir, second_dir]
            )

            self.assertEqual(problem_ids, {"problem-a", "problem-b", "problem-c"})
            self.assertEqual(report["json_file_count"], 5)
            self.assertEqual(report["unique_problem_id_count"], 3)
            self.assertEqual(report["duplicate_problem_id_count"], 2)
            self.assertEqual(len(report["directory_reports"]), 2)

    @staticmethod
    def _write_problem(path: Path, problem_id: str) -> None:
        path.write_text(
            json.dumps({"problem_id": problem_id}, ensure_ascii=False),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
