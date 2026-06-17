from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .utils import rate, read_json, wilson, write_csv, write_json, write_text


SUITES = ("unicode_style_baseline", "size_control", "ours_pipeline")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_completed_problem_results(run_dir: Path) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    pairs: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for result_path in sorted((run_dir / "problems").glob("*/result.json")):
        result = read_json(result_path)
        if not isinstance(result, dict) or result.get("status") != "completed":
            continue
        verdicts = _read_jsonl(Path(result["candidate_verdicts_path"]))
        pairs.append((result, verdicts))
    return pairs


def _suite_summary(verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for suite in SUITES:
        suite_items = [item for item in verdicts if item.get("suite") == suite]
        right = [item for item in suite_items if item.get("submission_type") == "right_submission"]
        wrong = [item for item in suite_items if item.get("submission_type") == "wrong_submission"]
        correct_count = sum(1 for item in right if item.get("accepted") is True)
        covered_count = sum(1 for item in wrong if item.get("rejected") is True)
        semantic_wrong = [item for item in wrong if item.get("semantic_eligible") is True]
        semantic_covered = sum(1 for item in semantic_wrong if item.get("rejected") is True)
        correctness_low, correctness_high = wilson(correct_count, len(right))
        coverage_low, coverage_high = wilson(covered_count, len(wrong))
        rows.append(
            {
                "suite": suite,
                "right_submission_count": len(right),
                "correct_submission_count": correct_count,
                "correctness": rate(correct_count, len(right)),
                "correctness_wilson_low": correctness_low,
                "correctness_wilson_high": correctness_high,
                "wrong_submission_count": len(wrong),
                "covered_wrong_submission_count": covered_count,
                "coverage": rate(covered_count, len(wrong)),
                "coverage_wilson_low": coverage_low,
                "coverage_wilson_high": coverage_high,
                "semantic_wrong_submission_count": len(semantic_wrong),
                "semantic_covered_wrong_submission_count": semantic_covered,
                "semantic_coverage": rate(semantic_covered, len(semantic_wrong)),
            }
        )
    by_suite = {row["suite"]: row for row in rows}
    baseline = by_suite.get("unicode_style_baseline", {})
    size_control = by_suite.get("size_control", {})
    ours = by_suite.get("ours_pipeline", {})
    for row in rows:
        row["targeted_gain_vs_baseline"] = (
            float(ours.get("coverage", 0.0)) - float(baseline.get("coverage", 0.0))
            if row["suite"] == "ours_pipeline"
            else ""
        )
        row["size_controlled_gain"] = (
            float(ours.get("coverage", 0.0)) - float(size_control.get("coverage", 0.0))
            if row["suite"] == "ours_pipeline"
            else ""
        )
        row["correctness_drop_vs_baseline"] = (
            float(baseline.get("correctness", 0.0)) - float(ours.get("correctness", 0.0))
            if row["suite"] == "ours_pipeline"
            else ""
        )
    return rows


def _problem_rows(pairs: list[tuple[dict[str, Any], list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result, verdicts in pairs:
        by_suite = {row["suite"]: row for row in _suite_summary(verdicts)}
        base = by_suite.get("unicode_style_baseline", {})
        size = by_suite.get("size_control", {})
        ours = by_suite.get("ours_pipeline", {})
        rows.append(
            {
                "problem_id": result["problem_id"],
                "baseline_case_count": result["suite_case_counts"].get("unicode_style_baseline", 0),
                "size_control_case_count": result["suite_case_counts"].get("size_control", 0),
                "ours_case_count": result["suite_case_counts"].get("ours_pipeline", 0),
                "baseline_correctness": base.get("correctness", 0.0),
                "size_control_correctness": size.get("correctness", 0.0),
                "ours_correctness": ours.get("correctness", 0.0),
                "baseline_coverage": base.get("coverage", 0.0),
                "size_control_coverage": size.get("coverage", 0.0),
                "ours_coverage": ours.get("coverage", 0.0),
                "targeted_gain": float(ours.get("coverage", 0.0)) - float(base.get("coverage", 0.0)),
                "size_controlled_gain": float(ours.get("coverage", 0.0)) - float(size.get("coverage", 0.0)),
            }
        )
    return rows


def _first_kill_rows(verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str]] = Counter()
    for item in verdicts:
        if item.get("submission_type") != "wrong_submission" or item.get("rejected") is not True:
            continue
        counter[(str(item.get("suite", "")), str(item.get("first_kill_source", "")))] += 1
    return [
        {"suite": suite, "first_kill_source": source, "count": count}
        for (suite, source), count in sorted(counter.items())
    ]


def generate_report(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    pairs = _load_completed_problem_results(run_dir)
    all_verdicts = [item for _, verdicts in pairs for item in verdicts]
    suite_rows = _suite_summary(all_verdicts)
    problem_rows = _problem_rows(pairs)
    first_kill_rows = _first_kill_rows(all_verdicts)

    write_csv(run_dir / "ablation_summary.csv", list(suite_rows[0].keys()) if suite_rows else ["suite"], suite_rows)
    if problem_rows:
        write_csv(run_dir / "problem_summary.csv", list(problem_rows[0].keys()), problem_rows)
    else:
        write_csv(run_dir / "problem_summary.csv", ["problem_id"], [])
    write_csv(run_dir / "first_kill_source.csv", ["suite", "first_kill_source", "count"], first_kill_rows)

    summary = {
        "status": "complete" if pairs else "empty",
        "completed_problem_count": len(pairs),
        "suite_summary": suite_rows,
    }
    write_json(run_dir / "summary.json", summary)

    lines = [
        "# 消融实验报告",
        "",
        f"- 完成题目数：{len(pairs)}",
        "",
        "## 主结果",
        "",
        "| Suite | Correctness | Coverage | SemanticCoverage |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in suite_rows:
        lines.append(
            f"| {row['suite']} | {row['correctness']:.3f} | {row['coverage']:.3f} | "
            f"{row['semantic_coverage']:.3f} |"
        )
    ours = next((row for row in suite_rows if row["suite"] == "ours_pipeline"), None)
    if ours:
        lines.extend(
            [
                "",
                "## 增益",
                "",
                f"- TargetedGain：{ours['targeted_gain_vs_baseline']:.3f}",
                f"- SizeControlledGain：{ours['size_controlled_gain']:.3f}",
                f"- CorrectnessDrop：{ours['correctness_drop_vs_baseline']:.3f}",
            ]
        )
    write_text(run_dir / "report.md", "\n".join(lines) + "\n")
    return summary
