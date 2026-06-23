from __future__ import annotations

from typing import Any


def select_manifest_problem_range(
    problems: list[dict[str, Any]],
    *,
    limit: int | None = None,
    start_index: int | None = None,
    end_index: int | None = None,
) -> tuple[list[tuple[int, dict[str, Any]]], dict[str, int | str]]:
    """按 CLI 语义选择 manifest 题目范围，返回全局题号和题目记录。"""
    total = len(problems)
    if limit is not None and (start_index is not None or end_index is not None):
        raise ValueError("--limit 不能与 --start-index/--end-index 同时使用。")

    if limit is not None:
        if limit < 1:
            raise ValueError("--limit 必须大于等于 1。")
        selected = list(enumerate(problems[:limit], start=1))
        return selected, {
            "mode": "limit",
            "manifest_problem_count": total,
            "start_index": 1,
            "end_index": len(selected),
            "selected_problem_count": len(selected),
        }

    resolved_start = 1 if start_index is None else start_index
    resolved_end = total if end_index is None else end_index
    if resolved_start < 1:
        raise ValueError("--start-index 必须大于等于 1。")
    if resolved_start > total:
        raise ValueError(f"--start-index 超出 manifest 题目总数：start_index={resolved_start} problem_count={total}")
    if resolved_end < resolved_start:
        raise ValueError("--end-index 必须大于等于 --start-index。")
    if resolved_end > total:
        raise ValueError(f"--end-index 超出 manifest 题目总数：end_index={resolved_end} problem_count={total}")

    selected = list(enumerate(problems[resolved_start - 1 : resolved_end], start=resolved_start))
    return selected, {
        "mode": "range",
        "manifest_problem_count": total,
        "start_index": resolved_start,
        "end_index": resolved_end,
        "selected_problem_count": len(selected),
    }
