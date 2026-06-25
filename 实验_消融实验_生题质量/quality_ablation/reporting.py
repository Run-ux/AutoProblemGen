from __future__ import annotations

import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .judging import JUDGE_METRICS
from .manifest import load_manifest
from .utils import (
    ALL_CONDITIONS,
    average,
    format_number,
    median,
    read_json,
    read_jsonl,
    safe_name,
    write_csv,
    write_text,
)


METRICS = (*JUDGE_METRICS, "overall_score")
ABLATION_CONDITIONS = ("no_tuple", "no_rules", "no_quality_loop")


def build_report(*, manifest_path: Path, run_dir: Path, bootstrap_samples: int = 2000) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    scores = _latest_scores(run_dir)
    problem_ids = [str(problem["problem_id"]) for problem in manifest["problems"]]

    condition_stats = _condition_stats(scores=scores, problem_ids=problem_ids)
    generation_stats = _generation_stats(manifest=manifest, run_dir=run_dir)
    judge_stats = _judge_stats(scores=scores)
    comparisons = _paired_comparisons(scores=scores, bootstrap_samples=bootstrap_samples)

    summary_rows = _summary_rows(
        condition_stats=condition_stats,
        comparisons=comparisons,
        generation_stats=generation_stats,
        judge_stats=judge_stats,
    )
    summary_path = run_dir / "summary.csv"
    write_csv(
        summary_path,
        [
            "row_type",
            "condition",
            "comparison",
            "metric",
            "n",
            "mean",
            "median",
            "ci_low",
            "ci_high",
            "completed_count",
            "declared_failure_count",
            "failed_count",
            "missing_count",
            "judge_failed_count",
            "judge_missing_count",
        ],
        summary_rows,
    )

    report_path = run_dir / "report.md"
    write_text(
        report_path,
        _render_markdown_report(
            manifest=manifest,
            run_dir=run_dir,
            condition_stats=condition_stats,
            comparisons=comparisons,
            generation_stats=generation_stats,
            judge_stats=judge_stats,
            summary_path=summary_path,
        ),
    )

    return {
        "summary_path": str(summary_path),
        "report_path": str(report_path),
        "condition_stats": condition_stats,
        "comparisons": comparisons,
        "generation_stats": generation_stats,
        "judge_stats": judge_stats,
    }


def _latest_scores(run_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    scores: dict[tuple[str, str], dict[str, Any]] = {}
    for scores_path in _score_paths(run_dir):
        for row in read_jsonl(scores_path):
            problem_id = str(row.get("problem_id", ""))
            condition = str(row.get("condition", ""))
            if problem_id and condition:
                scores[(problem_id, condition)] = row
    return scores


def _score_paths(run_dir: Path) -> list[Path]:
    shard_paths = sorted(run_dir.glob("scores_shard_*_of_*.jsonl"))
    if shard_paths:
        return shard_paths
    return [run_dir / "scores.jsonl"]


def _condition_stats(*, scores: dict[tuple[str, str], dict[str, Any]], problem_ids: list[str]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for condition in ALL_CONDITIONS:
        metric_stats: dict[str, Any] = {}
        for metric in METRICS:
            values = [
                float(score[metric])
                for problem_id in problem_ids
                if (score := scores.get((problem_id, condition))) is not None
                and isinstance(score.get(metric), (int, float))
            ]
            metric_stats[metric] = {
                "n": len(values),
                "mean": average(values),
                "median": median(values),
            }
        stats[condition] = metric_stats
    return stats


def _paired_comparisons(
    *,
    scores: dict[tuple[str, str], dict[str, Any]],
    bootstrap_samples: int,
) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    problem_ids = sorted({problem_id for problem_id, _ in scores})
    for condition in ABLATION_CONDITIONS:
        comparison_name = f"full-{condition}"
        metric_stats: dict[str, Any] = {}
        for metric in METRICS:
            deltas: list[float] = []
            for problem_id in problem_ids:
                full_score = scores.get((problem_id, "full"))
                ablation_score = scores.get((problem_id, condition))
                if not full_score or not ablation_score:
                    continue
                if not isinstance(full_score.get(metric), (int, float)):
                    continue
                if not isinstance(ablation_score.get(metric), (int, float)):
                    continue
                deltas.append(float(full_score[metric]) - float(ablation_score[metric]))
            ci_low, ci_high = _bootstrap_ci(deltas, samples=bootstrap_samples)
            metric_stats[metric] = {
                "n": len(deltas),
                "mean": average(deltas),
                "median": median(deltas),
                "ci_low": ci_low,
                "ci_high": ci_high,
            }
        comparisons[comparison_name] = metric_stats
    return comparisons


def _generation_stats(*, manifest: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    problem_ids = [str(problem["problem_id"]) for problem in manifest["problems"]]
    stats: dict[str, Any] = {}
    for condition in ALL_CONDITIONS:
        counter: Counter[str] = Counter()
        for problem_id in problem_ids:
            if condition == "full":
                counter["completed"] += 1
                continue
            result_path = run_dir / "generations" / condition / safe_name(problem_id) / "result.json"
            if not result_path.is_file():
                counter["missing"] += 1
                continue
            result = read_json(result_path)
            status = str(result.get("status") or "unknown")
            if status == "completed":
                counter["completed"] += 1
            elif status == "declared_failure":
                counter["declared_failure"] += 1
            else:
                counter["failed"] += 1
        total = len(problem_ids)
        stats[condition] = {
            "total": total,
            "completed_count": counter["completed"],
            "declared_failure_count": counter["declared_failure"],
            "failed_count": counter["failed"],
            "missing_count": counter["missing"],
            "failure_rate": _rate(counter["declared_failure"] + counter["failed"] + counter["missing"], total),
        }
    return stats


def _judge_stats(scores: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for (_, condition), score in scores.items():
        grouped[condition][str(score.get("judge_status") or "unknown")] += 1
    stats: dict[str, Any] = {}
    for condition in ALL_CONDITIONS:
        counter = grouped[condition]
        total = sum(counter.values())
        stats[condition] = {
            "total": total,
            "completed_count": counter["completed"] + counter["declared_failure_zero"],
            "judge_failed_count": counter["judge_failed"],
            "judge_missing_count": counter["missing"],
            "missing_count": counter["missing"],
            "failure_rate": _rate(counter["judge_failed"] + counter["missing"], total),
        }
    return stats


def _summary_rows(
    *,
    condition_stats: dict[str, Any],
    comparisons: dict[str, Any],
    generation_stats: dict[str, Any],
    judge_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for condition in ALL_CONDITIONS:
        for metric in METRICS:
            metric_stats = condition_stats[condition][metric]
            gen = generation_stats[condition]
            judge = judge_stats[condition]
            rows.append(
                {
                    "row_type": "condition",
                    "condition": condition,
                    "comparison": "",
                    "metric": metric,
                    "n": metric_stats["n"],
                    "mean": metric_stats["mean"],
                    "median": metric_stats["median"],
                    "ci_low": "",
                    "ci_high": "",
                    "completed_count": gen["completed_count"],
                    "declared_failure_count": gen["declared_failure_count"],
                    "failed_count": gen["failed_count"],
                    "missing_count": gen["missing_count"],
                    "judge_failed_count": judge["judge_failed_count"],
                    "judge_missing_count": judge["judge_missing_count"],
                }
            )

    for comparison, metric_payload in comparisons.items():
        for metric in METRICS:
            metric_stats = metric_payload[metric]
            rows.append(
                {
                    "row_type": "paired_delta",
                    "condition": "",
                    "comparison": comparison,
                    "metric": metric,
                    "n": metric_stats["n"],
                    "mean": metric_stats["mean"],
                    "median": metric_stats["median"],
                    "ci_low": metric_stats["ci_low"],
                    "ci_high": metric_stats["ci_high"],
                    "completed_count": "",
                    "declared_failure_count": "",
                    "failed_count": "",
                    "missing_count": "",
                    "judge_failed_count": "",
                    "judge_missing_count": "",
                }
            )
    return rows


def _render_markdown_report(
    *,
    manifest: dict[str, Any],
    run_dir: Path,
    condition_stats: dict[str, Any],
    comparisons: dict[str, Any],
    generation_stats: dict[str, Any],
    judge_stats: dict[str, Any],
    summary_path: Path,
) -> str:
    lines: list[str] = [
        "# 生题质量消融实验报告",
        "",
        f"- run_dir: `{run_dir}`",
        f"- manifest: `{manifest.get('manifest_path', '') or '见命令参数'}`",
        f"- eligible 题数: {manifest.get('eligible_count', len(manifest.get('problems', [])))}",
        f"- summary.csv: `{summary_path}`",
        "",
        "## 实验说明",
        "",
        "- `full` 复用 `successful_output` 中已验证成功的最终题面，不重新生成。",
        "- `no_tuple` 禁用外部四元组输入，只给原题文本、元信息和规则摘要。",
        "- `no_rules` 保留四元组和原题文本，但禁用 `planning_rules.json` 和规则专属逻辑。",
        "- `no_quality_loop` 保留四元组和规则规划，只生成首轮题面，关闭质量评价后的回流修订。",
        "- LLM judge 为单次盲评；报告结论应同时考虑 judge 方差风险。",
        "",
        "## 分组均值",
        "",
        "| condition | metric | n | mean | median |",
        "|---|---:|---:|---:|---:|",
    ]
    for condition in ALL_CONDITIONS:
        for metric in METRICS:
            payload = condition_stats[condition][metric]
            lines.append(
                f"| {condition} | {metric} | {payload['n']} | "
                f"{format_number(payload['mean'])} | {format_number(payload['median'])} |"
            )

    lines.extend(
        [
            "",
            "## 配对差值",
            "",
            "`full - ablation` 为正表示 full 分数更高。",
            "",
            "| comparison | metric | n | mean delta | median delta | bootstrap 95% CI |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for comparison, metric_payload in comparisons.items():
        for metric in METRICS:
            payload = metric_payload[metric]
            ci_text = f"[{format_number(payload['ci_low'])}, {format_number(payload['ci_high'])}]"
            lines.append(
                f"| {comparison} | {metric} | {payload['n']} | "
                f"{format_number(payload['mean'])} | {format_number(payload['median'])} | {ci_text} |"
            )

    lines.extend(
        [
            "",
            "## 失败统计",
            "",
            "| condition | generation completed | declared failure | infra failed | missing | judge failed | judge missing |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for condition in ALL_CONDITIONS:
        gen = generation_stats[condition]
        judge = judge_stats[condition]
        lines.append(
            f"| {condition} | {gen['completed_count']} | {gen['declared_failure_count']} | "
            f"{gen['failed_count']} | {gen['missing_count']} | "
            f"{judge['judge_failed_count']} | {judge['judge_missing_count']} |"
        )

    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 本实验只评价题面质量，不把测试用例、标准解法或验证结果输入 judge。",
            "- 声明性失败按 0 分进入主指标；API、超时、文件缺失等基础设施失败记为 missing。",
            "- 种子集合限定为 `successful_output` 中已成功生成并验证的题，不代表全部候选种子的无偏样本。",
            "",
        ]
    )
    return "\n".join(lines)


def _bootstrap_ci(values: list[float], *, samples: int, seed: int = 20260624) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    if len(values) == 1 or samples <= 0:
        value = average(values)
        return value, value

    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        resampled = [values[rng.randrange(len(values))] for _ in values]
        estimate = average(resampled)
        if estimate is not None:
            estimates.append(estimate)
    estimates.sort()
    low_index = int(0.025 * (len(estimates) - 1))
    high_index = int(0.975 * (len(estimates) - 1))
    return estimates[low_index], estimates[high_index]


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator
