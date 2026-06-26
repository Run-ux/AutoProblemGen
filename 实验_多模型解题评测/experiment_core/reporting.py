from __future__ import annotations

import csv
import io
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .utils import atomic_write_json, atomic_write_text, read_json, utc_now_iso


CATEGORIES = ("random", "adversarial", "small_challenge", "large_scale")


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    # UTF-8 BOM 便于直接使用 Excel 打开中文 CSV。
    atomic_write_text(path, "\ufeff" + buffer.getvalue())


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _rate(successes: int, total: int) -> float:
    return successes / total if total else 0.0


def _difficulty(pass_rate: float, complete_model_count: int) -> str:
    if complete_model_count < 3:
        return "insufficient_models"
    if pass_rate >= 2 / 3:
        return "easy"
    if pass_rate >= 1 / 3:
        return "medium"
    return "hard"


def _load_results(run_dir: Path) -> list[dict[str, Any]]:
    results = []
    for path in sorted((run_dir / "results").glob("*/*.json")):
        try:
            payload = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            payload["_result_path"] = str(path.resolve())
            results.append(payload)
    return results


def _problem_model_row(result: dict[str, Any]) -> dict[str, Any]:
    response = result.get("response", {})
    usage = response.get("usage", {}) if isinstance(response, dict) else {}
    categories = result.get("category_results", {})
    return {
        "model_id": result.get("model", {}).get("id", ""),
        "problem_id": result.get("problem", {}).get("problem_id", ""),
        "status": result.get("status", ""),
        "passed": result.get("passed", ""),
        "failure_kind": result.get("failure_kind", result.get("error_type", "")),
        **{
            f"{category}_passed": categories.get(category, {}).get("passed", "")
            for category in CATEGORIES
        },
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "duration_seconds": response.get("duration_seconds", "") if isinstance(response, dict) else "",
        "estimated_cost_usd": result.get("estimated_cost_usd", ""),
        "source": result.get("problem", {}).get("source", ""),
        "applied_rule": result.get("problem", {}).get("applied_rule", ""),
        "changed_axes": "|".join(result.get("problem", {}).get("changed_axes", [])),
        "algorithm_tags": "|".join(result.get("problem", {}).get("algorithm_tags", [])),
        "result_path": result.get("_result_path", ""),
    }


def _group_values(problem: dict[str, Any]) -> list[tuple[str, str]]:
    groups = [("source", str(problem.get("source", ""))), ("applied_rule", str(problem.get("applied_rule", "")))]
    groups.extend(("changed_axis", str(value)) for value in problem.get("changed_axes", []))
    groups.extend(("algorithm_tag", str(value)) for value in problem.get("algorithm_tags", []))
    return [(dimension, value) for dimension, value in groups if value]


def generate_reports(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    metadata = read_json(run_dir / "run_metadata.json")
    expected_problem_count = int(metadata["problem_count"])
    configured_models = [item["id"] for item in metadata["models"]]
    expected_fingerprints = {item["id"]: item["fingerprint"] for item in metadata["models"]}
    results = [
        item
        for item in _load_results(run_dir)
        if item.get("model", {}).get("id") in expected_fingerprints
        and item.get("identity", {}).get("manifest_sha256") == metadata["manifest_sha256"]
        and item.get("identity", {}).get("model_config_fingerprint")
        == expected_fingerprints.get(item.get("model", {}).get("id"))
    ]
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_model[str(result.get("model", {}).get("id", ""))].append(result)
    complete_models = [
        model_id
        for model_id in configured_models
        if len(by_model[model_id]) == expected_problem_count
        and all(item.get("status") == "completed" for item in by_model[model_id])
    ]
    infrastructure_error_count = sum(item.get("status") == "infrastructure_error" for item in results)
    experiment_status = "complete" if len(complete_models) == len(configured_models) else "incomplete"

    detail_rows = [_problem_model_row(result) for result in results]
    detail_fields = [
        "model_id", "problem_id", "status", "passed", "failure_kind",
        "random_passed", "adversarial_passed", "small_challenge_passed", "large_scale_passed",
        "prompt_tokens", "completion_tokens", "total_tokens", "duration_seconds", "estimated_cost_usd",
        "source", "applied_rule", "changed_axes", "algorithm_tags", "result_path",
    ]
    _write_csv(run_dir / "problem_model_results.csv", detail_fields, detail_rows)

    model_rows = []
    for model_id in complete_models:
        items = by_model[model_id]
        overall_passes = sum(bool(item.get("passed")) for item in items)
        low, high = _wilson(overall_passes, len(items))
        category_rates = {
            category: _rate(
                sum(bool(item.get("category_results", {}).get(category, {}).get("passed")) for item in items),
                len(items),
            )
            for category in CATEGORIES
        }
        costs = [item.get("estimated_cost_usd") for item in items if item.get("estimated_cost_usd") is not None]
        prompt_tokens = sum(item.get("response", {}).get("usage", {}).get("prompt_tokens", 0) for item in items)
        completion_tokens = sum(
            item.get("response", {}).get("usage", {}).get("completion_tokens", 0) for item in items
        )
        model_rows.append(
            {
                "model_id": model_id,
                "problem_count": len(items),
                "pass_count": overall_passes,
                "overall_pass_at_1": _rate(overall_passes, len(items)),
                "wilson_95_low": low,
                "wilson_95_high": high,
                "rand_pass": category_rates["random"],
                "adv_pass": category_rates["adversarial"],
                "adv_minus_rand": category_rates["adversarial"] - category_rates["random"],
                "small_challenge_pass": category_rates["small_challenge"],
                "large_scale_pass": category_rates["large_scale"],
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "avg_output_tokens": completion_tokens / len(items),
                "avg_duration_seconds": sum(item.get("response", {}).get("duration_seconds", 0) for item in items) / len(items),
                "total_estimated_cost_usd": sum(costs) if len(costs) == len(items) else "",
                "avg_estimated_cost_usd": sum(costs) / len(items) if len(costs) == len(items) else "",
            }
        )
    model_rows.sort(key=lambda item: item["overall_pass_at_1"], reverse=True)
    model_fields = list(model_rows[0]) if model_rows else [
        "model_id", "problem_count", "pass_count", "overall_pass_at_1", "wilson_95_low", "wilson_95_high",
        "rand_pass", "adv_pass", "adv_minus_rand", "small_challenge_pass", "large_scale_pass",
        "prompt_tokens", "completion_tokens", "avg_output_tokens", "avg_duration_seconds",
        "total_estimated_cost_usd", "avg_estimated_cost_usd",
    ]
    _write_csv(run_dir / "model_summary.csv", model_fields, model_rows)

    problem_ids = sorted(
        {str(item.get("problem", {}).get("problem_id", "")) for model_id in complete_models for item in by_model[model_id]}
    )
    problem_rows = []
    for problem_id in problem_ids:
        items = [item for model_id in complete_models for item in by_model[model_id] if item.get("problem", {}).get("problem_id") == problem_id]
        passed = sum(bool(item.get("passed")) for item in items)
        pass_rate = _rate(passed, len(items))
        problem = items[0].get("problem", {}) if items else {}
        problem_rows.append(
            {
                "problem_id": problem_id,
                "title": problem.get("title", ""),
                "complete_model_count": len(items),
                "pass_count": passed,
                "model_pass_rate": pass_rate,
                "difficulty": _difficulty(pass_rate, len(complete_models)),
                "source": problem.get("source", ""),
                "applied_rule": problem.get("applied_rule", ""),
                "changed_axes": "|".join(problem.get("changed_axes", [])),
                "algorithm_tags": "|".join(problem.get("algorithm_tags", [])),
            }
        )
    problem_fields = list(problem_rows[0]) if problem_rows else [
        "problem_id", "title", "complete_model_count", "pass_count", "model_pass_rate", "difficulty",
        "source", "applied_rule", "changed_axes", "algorithm_tags",
    ]
    _write_csv(run_dir / "problem_difficulty.csv", problem_fields, problem_rows)

    group_accumulator: dict[tuple[str, str, str], list[bool]] = defaultdict(list)
    for model_id in complete_models:
        for item in by_model[model_id]:
            for dimension, value in _group_values(item.get("problem", {})):
                group_accumulator[(dimension, value, model_id)].append(bool(item.get("passed")))
                group_accumulator[(dimension, value, "__all__")].append(bool(item.get("passed")))
    group_rows = []
    for (dimension, value, model_id), passes in sorted(group_accumulator.items()):
        group_rows.append(
            {
                "dimension": dimension,
                "value": value,
                "model_id": model_id,
                "problem_model_count": len(passes),
                "pass_count": sum(passes),
                "pass_rate": _rate(sum(passes), len(passes)),
            }
        )
    _write_csv(
        run_dir / "group_summary.csv",
        ["dimension", "value", "model_id", "problem_model_count", "pass_count", "pass_rate"],
        group_rows,
    )

    failure_counts = Counter(
        str(item.get("failure_kind") or item.get("error_type") or "unknown")
        for item in results
        if item.get("status") != "completed" or not item.get("passed")
    )
    summary = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "status": experiment_status,
        "configured_models": configured_models,
        "complete_models": complete_models,
        "problem_count": expected_problem_count,
        "result_count": len(results),
        "infrastructure_error_count": infrastructure_error_count,
        "difficulty_available": len(complete_models) >= 3,
        "difficulty_thresholds": {"easy": ">= 2/3", "medium": ">= 1/3 and < 2/3", "hard": "< 1/3"},
        "failure_counts": dict(failure_counts),
        "model_summary": model_rows,
    }
    atomic_write_json(run_dir / "summary.json", summary)

    lines = [
        "# 生成题质量评测报告",
        "",
        f"- 实验状态：`{experiment_status}`",
        f"- 题目数：{expected_problem_count}",
        f"- 配置模型数：{len(configured_models)}",
        f"- 完整模型数：{len(complete_models)}",
        f"- 基础设施错误数：{infrastructure_error_count}",
        "",
        "## 模型结果",
        "",
    ]
    if experiment_status != "complete":
        lines.extend(["> 当前实验不完整，正式排名仅包含已完整覆盖全部题目的模型。", ""])
    if model_rows:
        lines.extend([
            "| 模型 | Pass@1 | RandPass | AdvPass | Adv-Rand | Small | Large | 95% CI |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ])
        for row in model_rows:
            lines.append(
                f"| {row['model_id']} | {row['overall_pass_at_1']:.3f} | {row['rand_pass']:.3f} | "
                f"{row['adv_pass']:.3f} | {row['adv_minus_rand']:.3f} | {row['small_challenge_pass']:.3f} | "
                f"{row['large_scale_pass']:.3f} | [{row['wilson_95_low']:.3f}, {row['wilson_95_high']:.3f}] |"
            )
    else:
        lines.append("暂无完整模型结果。")
    lines.extend(["", "## 难度定义", ""])
    if len(complete_models) >= 3:
        lines.append("按完整模型通过比例分档：easy >= 2/3，medium >= 1/3 且 < 2/3，hard < 1/3。")
    else:
        lines.append("完整模型少于 3 个，暂不形成正式经验难度分档。")
    lines.extend(["", "## 失败类型", ""])
    for key, value in failure_counts.most_common():
        lines.append(f"- `{key}`：{value}")
    atomic_write_text(run_dir / "report.md", "\n".join(lines) + "\n")
    return summary
