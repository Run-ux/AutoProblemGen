from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .utils import read_json, stable_hash, utc_now_iso, write_json


MANIFEST_SCHEMA_VERSION = 1
DEFAULT_PROBLEM_PARQUET_URL = (
    "https://huggingface.co/datasets/TestCase-Eval/problem/resolve/main/data/train-00000-of-00001.parquet"
)
DEFAULT_SUBMISSION_PARQUET_URL = (
    "https://huggingface.co/datasets/TestCase-Eval/submission_all/resolve/main/data/train-00000-of-00001.parquet"
)
PYTHON3_LANGUAGE_RE = r"Python 3|PyPy 3"


class ManifestError(RuntimeError):
    """消融实验 manifest 不满足输入合同。"""


def _rating_bucket(rating: Any) -> str:
    try:
        value = int(rating)
    except (TypeError, ValueError):
        return "unknown"
    if value <= 1200:
        return "easy"
    if value <= 1800:
        return "medium"
    return "hard"


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if hasattr(value, "tolist"):
        return [str(item) for item in value.tolist()]
    return [str(value)]


def _sample_problem_ids(problem_rows: pd.DataFrame, sample_size: int, seed: int) -> list[str]:
    # 先按难度分桶分配名额，再在桶内按主标签排序随机抽样，避免样本集中在单一 rating 段。
    rng = pd.Series(problem_rows["problem_id"]).sample(frac=1.0, random_state=seed).tolist()
    shuffled_rank = {problem_id: index for index, problem_id in enumerate(rng)}
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in problem_rows.to_dict("records"):
        tags = _as_string_list(row.get("tags"))
        buckets[_rating_bucket(row.get("rating"))].append(
            {
                "problem_id": str(row["problem_id"]),
                "primary_tag": tags[0] if tags else "",
                "shuffle_rank": shuffled_rank[str(row["problem_id"])],
            }
        )

    total = sum(len(items) for items in buckets.values())
    selected: list[str] = []
    remaining_slots = sample_size
    ordered_buckets = sorted(buckets.items(), key=lambda item: item[0])
    for index, (bucket, items) in enumerate(ordered_buckets):
        if index == len(ordered_buckets) - 1:
            quota = remaining_slots
        else:
            quota = round(sample_size * len(items) / total)
            quota = max(0, min(quota, remaining_slots))
        chosen = sorted(items, key=lambda item: (item["primary_tag"], item["shuffle_rank"]))[:quota]
        selected.extend(item["problem_id"] for item in chosen)
        remaining_slots -= len(chosen)

    if len(selected) < sample_size:
        already = set(selected)
        extras = [
            str(row["problem_id"])
            for row in sorted(problem_rows.to_dict("records"), key=lambda item: shuffled_rank[str(item["problem_id"])])
            if str(row["problem_id"]) not in already
        ]
        selected.extend(extras[: sample_size - len(selected)])
    return sorted(selected[:sample_size])


def _submission_ids(rows: pd.DataFrame, problem_id: str, submission_type: str) -> list[int]:
    selected = rows[(rows["problem_id"] == problem_id) & (rows["type"] == submission_type)]
    return [int(value) for value in selected.sort_values("id")["id"].tolist()]


def build_manifest(
    *,
    output_path: Path,
    sample_size: int = 80,
    seed: int = 20260617,
    min_right: int = 3,
    min_wrong: int = 50,
    eval_right_per_problem: int = 3,
    eval_wrong_per_problem: int = 50,
    problem_parquet_url: str = DEFAULT_PROBLEM_PARQUET_URL,
    submission_parquet_url: str = DEFAULT_SUBMISSION_PARQUET_URL,
) -> dict[str, Any]:
    problem_df = pd.read_parquet(problem_parquet_url)
    submission_df = pd.read_parquet(submission_parquet_url, columns=["id", "language", "problem_id", "type"])
    python_df = submission_df[submission_df["language"].astype(str).str.contains(PYTHON3_LANGUAGE_RE, case=False, na=False)]
    counts = python_df.groupby(["problem_id", "type"]).size().unstack(fill_value=0)
    for column in ("right_submission", "wrong_submission"):
        if column not in counts.columns:
            counts[column] = 0
    eligible_ids = set(
        counts[(counts["right_submission"] >= min_right) & (counts["wrong_submission"] >= min_wrong)].index.astype(str)
    )
    eligible_problem_df = problem_df[problem_df["problem_id"].astype(str).isin(eligible_ids)].copy()
    if len(eligible_problem_df) < sample_size:
        raise ManifestError(f"可用题目不足：eligible={len(eligible_problem_df)} sample_size={sample_size}")

    sampled_ids = _sample_problem_ids(eligible_problem_df, sample_size, seed)
    problems: list[dict[str, Any]] = []
    problem_by_id = {str(row["problem_id"]): row for row in problem_df.to_dict("records")}
    for problem_id in sampled_ids:
        row = problem_by_id[problem_id]
        right_ids = _submission_ids(python_df, problem_id, "right_submission")
        wrong_ids = _submission_ids(python_df, problem_id, "wrong_submission")
        problems.append(
            {
                "problem_id": problem_id,
                "url": str(row.get("url", "")),
                "title": str(row.get("title", "")),
                "rating": int(row.get("rating", 0)),
                "rating_bucket": _rating_bucket(row.get("rating")),
                "tags": _as_string_list(row.get("tags")),
                "right_submission_ids": right_ids[:eval_right_per_problem],
                "wrong_submission_ids": wrong_ids[:eval_wrong_per_problem],
                "right_submission_count": len(right_ids),
                "wrong_submission_count": len(wrong_ids),
                "selected_right_submission_count": min(len(right_ids), eval_right_per_problem),
                "selected_wrong_submission_count": min(len(wrong_ids), eval_wrong_per_problem),
            }
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "problem_parquet_url": problem_parquet_url,
        "submission_parquet_url": submission_parquet_url,
        "sample_size": sample_size,
        "seed": seed,
        "filters": {
            "language_regex": PYTHON3_LANGUAGE_RE,
            "min_right_submission": min_right,
            "min_wrong_submission": min_wrong,
            "eval_right_per_problem": eval_right_per_problem,
            "eval_wrong_per_problem": eval_wrong_per_problem,
        },
        "problem_count": len(problems),
        "problems": problems,
    }
    manifest["content_fingerprint"] = stable_hash({"schema_version": MANIFEST_SCHEMA_VERSION, "problems": problems})
    write_json(output_path, manifest)
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestError("不支持的消融实验 manifest schema_version。")
    problems = payload.get("problems")
    if not isinstance(problems, list) or not problems:
        raise ManifestError("manifest 不包含可评测题目。")
    return payload
