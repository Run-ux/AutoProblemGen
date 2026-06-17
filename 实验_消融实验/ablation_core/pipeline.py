from __future__ import annotations

import json
import logging
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from .config import VERIFICATION_DIR, load_runtime_config
from .manifest import load_manifest
from .problem_adapter import artifact_from_problem, load_problem_rows, write_tuple_input
from .submission_execution import evaluate_submission_on_cases
from .suites import build_suites
from .tuple_extraction import extract_tuple_snapshot
from .utils import read_json, safe_name, write_json

if str(VERIFICATION_DIR) in sys.path:
    sys.path.remove(str(VERIFICATION_DIR))
sys.path.insert(0, str(VERIFICATION_DIR))

from generation_pipeline import generate_verified_artifacts  # noqa: E402


logger = logging.getLogger(__name__)


def _submission_rows(submission_parquet_url: str, ids: set[int]) -> dict[int, dict[str, Any]]:
    frame = pd.read_parquet(
        submission_parquet_url,
        columns=["id", "language", "verdict", "source", "problem_id", "type"],
    )
    selected = frame[frame["id"].astype(int).isin(ids)]
    return {int(row["id"]): row for row in selected.to_dict("records")}


def _standard_timeout(problem: dict[str, Any], verification: dict[str, Any]) -> float:
    limits = verification.get("standard_solution_verification", {}).get("standard_solution_limits", {})
    try:
        return float(limits.get("timeout_seconds"))
    except (TypeError, ValueError):
        return max(1.0, float(problem.get("rating", 0) or 0) / 1000.0)


def _standard_memory(verification: dict[str, Any]) -> int:
    limits = verification.get("standard_solution_verification", {}).get("standard_solution_limits", {})
    try:
        return int(limits.get("memory_limit_mb"))
    except (TypeError, ValueError):
        return 512


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _evaluate_problem(
    *,
    problem: dict[str, Any],
    problem_row: dict[str, Any],
    submissions_by_id: dict[int, dict[str, Any]],
    run_dir: Path,
    runtime: dict[str, Any],
    resume: bool,
) -> dict[str, Any]:
    problem_id = str(problem["problem_id"])
    problem_dir = run_dir / "problems" / safe_name(problem_id)
    problem_dir.mkdir(parents=True, exist_ok=True)
    result_path = problem_dir / "result.json"
    if resume and result_path.is_file():
        return read_json(result_path)

    try:
        write_tuple_input(problem_dir / "tuple_input.json", problem_row)
        tuple_snapshot = extract_tuple_snapshot(
            problem_row=problem_row,
            output_dir=problem_dir,
            generation_llm=runtime["generation_llm"],
            resume=resume,
        )
        artifact = artifact_from_problem(problem_row, tuple_snapshot)
        write_json(problem_dir / "artifact.json", artifact)

        verification_path = problem_dir / "verification.json"
        if resume and verification_path.is_file():
            verification = read_json(verification_path)
        else:
            verification = generate_verified_artifacts(
                artifact,
                runtime["llm_config"],
                execution_config=runtime["execution_config"],
                context_limits=runtime["context_limits"],
                test_generation_config=SimpleNamespace(
                    random_count=20,
                    adversarial_count=20,
                    small_challenge_count=10,
                ),
            )
            write_json(verification_path, verification)

        suites = build_suites(verification, execution_config=runtime["execution_config"])
        write_json(problem_dir / "suites.json", suites)

        timeout_seconds = _standard_timeout(problem, verification)
        memory_limit_mb = _standard_memory(verification)
        submission_results: list[dict[str, Any]] = []
        for suite_name, cases in suites.items():
            for submission_id in [*problem["right_submission_ids"], *problem["wrong_submission_ids"]]:
                submission = submissions_by_id[int(submission_id)]
                submission_results.append(
                    evaluate_submission_on_cases(
                        submission=submission,
                        suite_name=suite_name,
                        cases=cases,
                        timeout_seconds=timeout_seconds,
                        memory_limit_mb=memory_limit_mb,
                    )
                )
        _write_jsonl(problem_dir / "candidate_verdicts.jsonl", submission_results)

        payload = {
            "status": "completed",
            "problem_id": problem_id,
            "suite_case_counts": {name: len(cases) for name, cases in suites.items()},
            "right_submission_ids": problem["right_submission_ids"],
            "wrong_submission_ids": problem["wrong_submission_ids"],
            "result_path": str(result_path),
            "candidate_verdicts_path": str(problem_dir / "candidate_verdicts.jsonl"),
        }
    except Exception as exc:
        payload = {
            "status": "failed",
            "problem_id": problem_id,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "result_path": str(result_path),
        }
    write_json(result_path, payload)
    return payload


def run_ablation(
    *,
    manifest_path: Path,
    output_root: Path,
    run_id: str,
    workflow_config_path: Path | None = None,
    limit: int | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    runtime = load_runtime_config(workflow_config_path)
    run_dir = output_root.resolve() / safe_name(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run_dir / "run_metadata.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "manifest_path": str(manifest_path.resolve()),
            "manifest_content_fingerprint": manifest.get("content_fingerprint", ""),
            "problem_count": manifest["problem_count"],
            "test_generation_config": {"random_count": 20, "adversarial_count": 20, "small_challenge_count": 10},
            "workflow_config_path": str((workflow_config_path or Path("D:/AutoProblemGen/总流程/workflow.env")).resolve()),
        },
    )

    problems = manifest["problems"][: limit or None]
    problem_rows = load_problem_rows(manifest["problem_parquet_url"])
    selected_submission_ids = {
        int(submission_id)
        for problem in problems
        for submission_id in [*problem["right_submission_ids"], *problem["wrong_submission_ids"]]
    }
    submissions_by_id = _submission_rows(manifest["submission_parquet_url"], selected_submission_ids)

    outcomes: list[dict[str, Any]] = []
    for index, problem in enumerate(problems, start=1):
        print(f"[ablation {index}/{len(problems)}] {problem['problem_id']} {problem.get('title', '')}", flush=True)
        outcomes.append(
            _evaluate_problem(
                problem=problem,
                problem_row=problem_rows[str(problem["problem_id"])],
                submissions_by_id=submissions_by_id,
                run_dir=run_dir,
                runtime=runtime,
                resume=resume,
            )
        )
    write_json(run_dir / "run_summary.json", {"run_dir": str(run_dir), "outcomes": outcomes})
    return {
        "run_dir": str(run_dir),
        "problem_count": len(problems),
        "completed_count": sum(item.get("status") == "completed" for item in outcomes),
        "failed_count": sum(item.get("status") == "failed" for item in outcomes),
    }
