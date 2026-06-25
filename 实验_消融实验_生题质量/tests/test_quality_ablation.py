from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))

from quality_ablation.generation import build_custom_generation_prompts, condition_quality_iterations, run_generations
from quality_ablation.judging import build_blind_items, build_judge_prompt, run_judging
from quality_ablation.manifest import build_manifest
from quality_ablation.reporting import build_report
from quality_ablation.utils import limited_rows, read_jsonl, sharded_rows, validate_shard, write_json, write_jsonl


class QualityAblationTests(unittest.TestCase):
    def test_sharded_rows_are_disjoint_and_cover_limited_rows(self) -> None:
        rows = list(range(7))

        shards = [sharded_rows(rows, shard_count=3, shard_index=index) for index in range(3)]

        self.assertEqual(shards, [[0, 3, 6], [1, 4], [2, 5]])
        self.assertEqual(sorted(item for shard in shards for item in shard), rows)
        limited = limited_rows(rows, 5)
        self.assertEqual(sharded_rows(limited, shard_count=2, shard_index=1), [1, 3])

    def test_shard_validation_rejects_invalid_arguments(self) -> None:
        with self.assertRaisesRegex(ValueError, "--shard-count"):
            validate_shard(shard_count=0, shard_index=0)
        with self.assertRaisesRegex(ValueError, "--shard-index"):
            validate_shard(shard_count=2, shard_index=2)

    def test_manifest_identifies_final_full_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            problem_dir = _make_successful_problem(root, problem_id="p1")
            manifest_path = Path(temp_dir) / "manifest.json"

            manifest = build_manifest(successful_root=root, output_path=manifest_path)

            self.assertEqual(manifest["eligible_count"], 1)
            item = manifest["problems"][0]
            self.assertEqual(item["problem_id"], "p1")
            self.assertEqual(Path(item["full"]["artifact_path"]).name, "final_artifact.json")
            self.assertEqual(Path(item["full"]["markdown_path"]).name, "final_problem.md")
            self.assertEqual(item["full"]["full_source_dir"], str(problem_dir.resolve()))

    def test_manifest_includes_dirs_missing_from_upstream_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            p1 = _make_successful_problem(root, problem_id="p1")
            _make_successful_problem(root, problem_id="p2")
            write_json(root / "_manifest.json", {"problems": [{"problem_id": "p1", "target_dir": str(p1)}]})
            manifest_path = Path(temp_dir) / "manifest.json"

            manifest = build_manifest(successful_root=root, output_path=manifest_path)

            self.assertEqual(manifest["eligible_count"], 2)
            self.assertEqual([item["problem_id"] for item in manifest["problems"]], ["p1", "p2"])

    def test_no_tuple_prompt_does_not_include_external_tuple_values(self) -> None:
        source = _source_payload(problem_id="p1", unique_tuple_value="UNIQUE_TUPLE_SECRET")

        _system_prompt, user_prompt = build_custom_generation_prompts(
            condition="no_tuple",
            source_payload=source,
            rules_summary=[{"id": "rule_a", "summary": "改变问题目标"}],
        )

        self.assertIn("原题标题", user_prompt)
        self.assertNotIn("UNIQUE_TUPLE_SECRET", user_prompt)
        self.assertNotIn("tuple_raw", user_prompt)

    def test_no_rules_prompt_keeps_tuple_but_not_rule_specific_payload(self) -> None:
        source = _source_payload(problem_id="p1", unique_tuple_value="UNIQUE_TUPLE_SECRET")

        _system_prompt, user_prompt = build_custom_generation_prompts(
            condition="no_rules",
            source_payload=source,
            rules_summary=[{"id": "RULE_SECRET", "summary": "不应进入 no_rules"}],
        )

        self.assertIn("UNIQUE_TUPLE_SECRET", user_prompt)
        self.assertNotIn("RULE_SECRET", user_prompt)
        self.assertNotIn("available_rule_summaries", user_prompt)

    def test_no_quality_loop_uses_zero_quality_iterations(self) -> None:
        self.assertEqual(condition_quality_iterations("no_quality_loop"), 0)
        self.assertEqual(condition_quality_iterations("no_tuple"), 3)
        self.assertEqual(condition_quality_iterations("no_rules"), 3)

    def test_run_generations_shard_materializes_only_assigned_full_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            for problem_id in ("p0", "p1", "p2"):
                _make_successful_problem(root, problem_id=problem_id)
            manifest_path = Path(temp_dir) / "manifest.json"
            build_manifest(successful_root=root, output_path=manifest_path)
            output_root = Path(temp_dir) / "output"

            result = run_generations(
                manifest_path=manifest_path,
                output_root=output_root,
                run_id="quality",
                conditions=["full"],
                client=object(),
                shard_count=2,
                shard_index=1,
            )

            run_dir = output_root / "quality"
            self.assertEqual(result["problem_count"], 1)
            self.assertTrue((run_dir / "run_metadata_shard_1_of_2.json").is_file())
            self.assertTrue((run_dir / "run_summary_shard_1_of_2.json").is_file())
            self.assertFalse((run_dir / "run_summary.json").exists())
            self.assertFalse((run_dir / "generations" / "full" / "p0" / "result.json").exists())
            self.assertTrue((run_dir / "generations" / "full" / "p1" / "result.json").is_file())
            self.assertFalse((run_dir / "generations" / "full" / "p2" / "result.json").exists())

    def test_blind_judge_payload_does_not_leak_condition_or_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            _make_successful_problem(root, problem_id="p1")
            manifest_path = Path(temp_dir) / "manifest.json"
            manifest = build_manifest(successful_root=root, output_path=manifest_path)
            run_dir = Path(temp_dir) / "run"
            generation_dir = run_dir / "generations" / "no_tuple" / "p1"
            markdown_path = generation_dir / "output" / "new.md"
            markdown_path.parent.mkdir(parents=True)
            markdown_path.write_text("# 新题\n\n> 生成任务：`p1` / theme `x`\n\n题面内容。", encoding="utf-8")
            write_json(
                generation_dir / "result.json",
                {
                    "status": "completed",
                    "generated_status": "ok",
                    "markdown_path": str(markdown_path),
                },
            )

            items = build_blind_items(
                manifest=manifest,
                run_dir=run_dir,
                conditions=["no_tuple"],
                problems=manifest["problems"],
                blind_seed=1,
            )

            payload_text = json.dumps(items[0]["judge_payload"], ensure_ascii=False)
            prompt = build_judge_prompt(**items[0]["judge_payload"])
            self.assertNotIn("no_tuple", payload_text)
            self.assertNotIn(str(run_dir), payload_text)
            self.assertNotIn("生成任务", payload_text)
            self.assertNotIn("quality_report", prompt)

    def test_run_judging_shard_writes_isolated_score_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            for problem_id in ("p0", "p1", "p2"):
                _make_successful_problem(root, problem_id=problem_id)
            manifest_path = Path(temp_dir) / "manifest.json"
            build_manifest(successful_root=root, output_path=manifest_path)
            run_dir = Path(temp_dir) / "run"
            client = _FakeJudgeClient()

            result = run_judging(
                manifest_path=manifest_path,
                run_dir=run_dir,
                conditions=["full"],
                client=client,
                shard_count=2,
                shard_index=0,
            )

            scores_path = run_dir / "scores_shard_0_of_2.jsonl"
            self.assertEqual(result["problem_count"], 2)
            self.assertEqual(client.call_count, 2)
            self.assertTrue(scores_path.is_file())
            self.assertFalse((run_dir / "scores.jsonl").exists())
            self.assertTrue((run_dir / "judging" / "blind_items_shard_0_of_2.jsonl").is_file())
            self.assertTrue((run_dir / "judging" / "judge_summary_shard_0_of_2.jsonl").is_file())
            self.assertEqual(len(read_jsonl(scores_path)), 2)

    def test_report_handles_paired_delta_and_missing_scores(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            _make_successful_problem(root, problem_id="p1")
            _make_successful_problem(root, problem_id="p2")
            manifest_path = Path(temp_dir) / "manifest.json"
            manifest = build_manifest(successful_root=root, output_path=manifest_path)
            run_dir = Path(temp_dir) / "run"
            _write_generation_result(run_dir, "no_tuple", "p1", "completed")
            _write_generation_result(run_dir, "no_tuple", "p2", "failed")
            for condition in ("no_rules", "no_quality_loop"):
                _write_generation_result(run_dir, condition, "p1", "completed")
                _write_generation_result(run_dir, condition, "p2", "completed")
            write_jsonl(
                run_dir / "scores.jsonl",
                [
                    _score("p1", "full", 80),
                    _score("p1", "no_tuple", 70),
                    _score("p2", "full", 60),
                    {
                        "problem_id": "p2",
                        "condition": "no_tuple",
                        "judge_status": "missing",
                        "overall_score": None,
                    },
                ],
            )

            result = build_report(manifest_path=manifest_path, run_dir=run_dir, bootstrap_samples=10)

            self.assertTrue(Path(result["summary_path"]).is_file())
            delta = result["comparisons"]["full-no_tuple"]["overall_score"]
            self.assertEqual(delta["n"], 1)
            self.assertEqual(delta["mean"], 10.0)

    def test_report_merges_sharded_scores_before_legacy_scores(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "successful_output"
            _make_successful_problem(root, problem_id="p1")
            _make_successful_problem(root, problem_id="p2")
            manifest_path = Path(temp_dir) / "manifest.json"
            build_manifest(successful_root=root, output_path=manifest_path)
            run_dir = Path(temp_dir) / "run"
            write_jsonl(
                run_dir / "scores.jsonl",
                [
                    _score("p1", "full", 10),
                    _score("p1", "no_tuple", 0),
                ],
            )
            write_jsonl(
                run_dir / "scores_shard_0_of_2.jsonl",
                [
                    _score("p1", "full", 80),
                    _score("p1", "no_tuple", 70),
                ],
            )
            write_jsonl(
                run_dir / "scores_shard_1_of_2.jsonl",
                [
                    _score("p2", "full", 60),
                    _score("p2", "no_tuple", 50),
                ],
            )

            result = build_report(manifest_path=manifest_path, run_dir=run_dir, bootstrap_samples=10)

            delta = result["comparisons"]["full-no_tuple"]["overall_score"]
            self.assertEqual(delta["n"], 2)
            self.assertEqual(delta["mean"], 10.0)


def _make_successful_problem(root: Path, *, problem_id: str) -> Path:
    problem_dir = root / problem_id
    for name in ("source", "metadata", "artifacts", "output", "reports"):
        (problem_dir / name).mkdir(parents=True, exist_ok=True)
    write_json(
        root / "_manifest.json",
        {
            "problems": [
                {"problem_id": path.name, "target_dir": str(path)}
                for path in sorted(root.iterdir())
                if path.is_dir()
            ],
        },
    )
    write_json(problem_dir / "source" / f"{problem_id}.json", _source_payload(problem_id=problem_id))
    write_json(
        problem_dir / "metadata" / "problem_record.json",
        {
            "problem": {
                "problem_id": problem_id,
                "status": "verified",
                "generation": {
                    "artifact_path": f"/remote/{problem_id}/final_artifact.json",
                    "markdown_path": f"/remote/{problem_id}/final_problem.md",
                    "quality_report_json_path": f"/remote/{problem_id}/final_quality.json",
                    "iteration_summary_path": f"/remote/{problem_id}/final_iteration.json",
                    "generated_status": "ok",
                    "final_round_index": 3,
                },
            }
        },
    )
    write_json(problem_dir / "artifacts" / "final_artifact.json", {"generated_problem": {"status": "ok"}})
    write_json(problem_dir / "artifacts" / "final_iteration.json", {"rounds": []})
    write_json(problem_dir / "reports" / "final_quality.json", {"overall": {"status": "pass"}})
    (problem_dir / "output" / "final_problem.md").write_text("# 最终题面\n\n内容。", encoding="utf-8")
    return problem_dir


def _source_payload(*, problem_id: str, unique_tuple_value: str = "tuple_value") -> dict[str, object]:
    return {
        "problem_id": problem_id,
        "source": "unit-test",
        "original_problem": {
            "title": "原题标题",
            "statement": "给定一个数组，求答案。",
            "input": "输入格式。",
            "output": "输出格式。",
        },
        "input_structure": {"kind": unique_tuple_value},
        "core_constraints": {"constraints": [{"description": unique_tuple_value}]},
        "objective": {"type": unique_tuple_value},
        "invariant": {"invariants": [{"description": unique_tuple_value}]},
        "tuple_raw": {"secret": unique_tuple_value},
    }


def _write_generation_result(run_dir: Path, condition: str, problem_id: str, status: str) -> None:
    result_dir = run_dir / "generations" / condition / problem_id
    result_dir.mkdir(parents=True, exist_ok=True)
    write_json(result_dir / "result.json", {"status": status, "generated_status": "ok"})


def _score(problem_id: str, condition: str, value: int) -> dict[str, object]:
    return {
        "problem_id": problem_id,
        "condition": condition,
        "judge_status": "completed",
        "solvability": value,
        "clarity": value,
        "novelty": value,
        "difficulty": value,
        "overall_score": value,
    }


class _FakeJudgeClient:
    def __init__(self) -> None:
        self.call_count = 0

    def chat_json(self, **_kwargs: object) -> dict[str, object]:
        self.call_count += 1
        return {
            "solvability": 80,
            "clarity": 80,
            "novelty": 80,
            "difficulty": 80,
            "solvability_reasoning": "可解。",
            "clarity_reasoning": "清晰。",
            "novelty_reasoning": "有差异。",
            "difficulty_reasoning": "难度合适。",
            "overall_comment": "整体可用。",
        }


if __name__ == "__main__":
    unittest.main()
