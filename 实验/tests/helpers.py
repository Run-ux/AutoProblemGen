from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generation_artifact(problem_id: str = "generated_p1") -> dict[str, Any]:
    return {
        "problem_id": problem_id,
        "source_problem_ids": ["seed_p1"],
        "applied_rule": "rule_a",
        "changed_axes_realized": ["objective", "invariant"],
        "generated_problem": {
            "title": "测试题",
            "description": "读取一个字符串并输出 ok。",
            "input_format": "一行字符串。",
            "output_format": "输出 ok。",
            "constraints": ["字符串长度至少为 1"],
            "samples": [{"input": "x", "output": "ok"}],
            "notes": "",
            "status": "ok",
        },
    }


def verification_artifact(*, needs_checker: bool = False) -> dict[str, Any]:
    solved_cases = []
    for source in ("random", "adversarial", "small_challenge"):
        solved_cases.append(
            {
                "case_id": f"{source}_1",
                "source": source,
                "input": "x\n",
                "output": "ok\n",
            }
        )
    checker = {"needs_checker": needs_checker, "reason": "test"}
    if needs_checker:
        checker["verified_checker_code"] = (
            "def check_output(input_str, output_str):\n"
            "    return output_str.strip().lower() == 'ok'\n"
        )
    return {
        "checker": checker,
        "bruteforce_verification": {"solved_cases": solved_cases},
        "large_scale_truth_outputs": {
            "status": "ok",
            "cases": [
                {
                    "case_id": "large_1",
                    "source": "large_scale",
                    "classification": "stress",
                    "input": "large\n",
                    "output": "ok\n",
                }
            ],
            "count": 1,
            "failure_count": 0,
        },
        "standard_solution_verification": {
            "standard_solution_limits": {"timeout_seconds": 1.0, "memory_limit_mb": 256}
        },
        "execution_metadata": {
            "execution_config": {"checker_timeout_seconds": 1.0, "checker_memory_limit_mb": 256}
        },
    }


def create_workflow_fixture(root: Path, *, problem_status: str = "verified") -> tuple[Path, Path, Path]:
    run_dir = root / "run_1"
    generation_path = run_dir / "generation" / "artifacts" / "p1.json"
    verification_path = run_dir / "verification" / "p1_verified_artifacts.json"
    input_path = run_dir / "input" / "p1.json"
    write_json(generation_path, generation_artifact())
    write_json(verification_path, verification_artifact())
    write_json(input_path, {"problem_id": "seed_p1", "source": "codeforces"})
    write_json(
        run_dir / "workflow_summary.json",
        {
            "problems": [
                {
                    "problem_id": "seed_p1",
                    "status": problem_status,
                    "input_path": str(input_path),
                    "generation": {
                        "artifact_path": str(generation_path),
                        "verification_result_path": str(verification_path),
                    },
                }
            ]
        },
    )
    return generation_path, verification_path, input_path
