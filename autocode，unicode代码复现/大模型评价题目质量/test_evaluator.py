import contextlib
import io
import json
import os
import sys
import tempfile
import types
import unittest


sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
sys.modules.setdefault("openai", types.SimpleNamespace(OpenAI=lambda *args, **kwargs: None))

from evaluator import EvaluationResult, ProblemEvaluator


class FakeEvaluator(ProblemEvaluator):
    """测试用评估器，避免单元测试调用真实 LLM。"""

    def __init__(self):
        self.calls = []

    def evaluate(self, seed_problem, new_problem):
        self.calls.append((seed_problem, new_problem))
        call_index = len(self.calls)
        return EvaluationResult(
            solvability=80 + call_index,
            clarity=70 + call_index,
            novelty=60 + call_index,
            difficulty=50 + call_index,
            overall_score=65 + call_index,
            solvability_reasoning="",
            clarity_reasoning="",
            novelty_reasoning="",
            difficulty_reasoning="",
            overall_comment=""
        )


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_text(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def create_problem(root_dir, batch_name, problem_name, complete=True):
    problem_dir = os.path.join(root_dir, batch_name, problem_name)
    write_json(
        os.path.join(problem_dir, "original_input", "seed.json"),
        {"title": f"seed-{problem_name}", "description": "seed"}
    )

    if complete:
        write_json(
            os.path.join(problem_dir, "other_methods", "autocode.json"),
            {"title": "autocode", "description": "candidate"}
        )
        write_json(
            os.path.join(problem_dir, "other_methods", "unicode.json"),
            {"title": "unicode", "description": "candidate"}
        )
        write_text(os.path.join(problem_dir, "output", "a.md"), "# a\nold")
        write_text(os.path.join(problem_dir, "output", "b.md"), "# b\nlatest")

    return problem_dir


def run_silently(evaluator, root_dir, batch_name):
    with contextlib.redirect_stdout(io.StringIO()):
        return evaluator.batch_evaluate(root_dir, batch_name)


class BatchEvaluationTests(unittest.TestCase):
    def test_batch_selection_and_last_md_by_filename(self):
        with tempfile.TemporaryDirectory() as root_dir:
            batch1_problem = create_problem(root_dir, "batch1", "problem_a")
            batch2_problem = create_problem(root_dir, "batch2", "problem_b")

            evaluator = FakeEvaluator()
            summary = run_silently(evaluator, root_dir, "batch1")

            scores_path = os.path.join(batch1_problem, "scores.json")
            self.assertTrue(os.path.exists(scores_path))
            self.assertFalse(os.path.exists(os.path.join(batch2_problem, "scores.json")))
            self.assertEqual(summary["total"], 1)
            self.assertEqual(summary["success"], 1)
            self.assertEqual(len(evaluator.calls), 3)
            self.assertEqual(evaluator.calls[2][1], "# b\nlatest")

            with open(scores_path, "r", encoding="utf-8") as f:
                scores = json.load(f)

            self.assertEqual(set(scores), {"autocode", "unicode", "output_md"})
            for candidate_score in scores.values():
                self.assertEqual(
                    set(candidate_score),
                    {"solvability", "clarity", "novelty", "difficulty", "overall_score"}
                )

    def test_missing_candidate_files_write_errors_and_continue(self):
        with tempfile.TemporaryDirectory() as root_dir:
            missing_problem = create_problem(root_dir, "batch1", "problem_missing", complete=False)
            valid_problem = create_problem(root_dir, "batch1", "problem_valid", complete=True)

            evaluator = FakeEvaluator()
            summary = run_silently(evaluator, root_dir, "batch1")

            self.assertEqual(summary["total"], 2)
            self.assertEqual(summary["success"], 1)
            self.assertEqual(summary["failed"], 1)
            self.assertEqual(len(evaluator.calls), 3)

            with open(os.path.join(missing_problem, "scores.json"), "r", encoding="utf-8") as f:
                missing_scores = json.load(f)
            self.assertIn("error", missing_scores["autocode"])
            self.assertIn("error", missing_scores["unicode"])
            self.assertIn("error", missing_scores["output_md"])

            self.assertTrue(os.path.exists(os.path.join(valid_problem, "scores.json")))


if __name__ == "__main__":
    unittest.main()
