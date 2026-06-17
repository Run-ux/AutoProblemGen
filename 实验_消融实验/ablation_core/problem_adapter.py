from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def load_problem_rows(problem_parquet_url: str) -> dict[str, dict[str, Any]]:
    frame = pd.read_parquet(problem_parquet_url)
    return {str(row["problem_id"]): row for row in frame.to_dict("records")}


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if hasattr(value, "tolist"):
        return value.tolist()
    return [value]


def _samples(examples: Any) -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
    for item in as_list(examples):
        values = as_list(item)
        if len(values) >= 2:
            samples.append({"input": str(values[0]), "output": str(values[1])})
    return samples


def problem_record_for_tuple_extract(row: dict[str, Any]) -> dict[str, Any]:
    problem_id = str(row["problem_id"])
    time_ms = int(row.get("time_limit_ms") or 2000)
    memory_mb = int(row.get("memory_limit_mb") or 256)
    return {
        "problem_id": problem_id,
        "title": str(row.get("title", "")),
        "source": {"source_name": "codeforces"},
        "description": str(row.get("prompt") or _joined_statement(row)),
        "limits": {
            "time_limit": {"seconds": time_ms // 1000, "nanos": (time_ms % 1000) * 1_000_000},
            "memory_limit_bytes": memory_mb * 1024 * 1024,
        },
    }


def artifact_from_problem(row: dict[str, Any], tuple_snapshot: dict[str, Any]) -> dict[str, Any]:
    problem_id = str(row["problem_id"])
    constraints = [
        str(row.get("input", "")),
        f"time limit: {int(row.get('time_limit_ms') or 2000) / 1000:g}s",
        f"memory limit: {int(row.get('memory_limit_mb') or 256)} MB",
    ]
    return {
        "problem_id": problem_id,
        "source_problem_ids": [problem_id],
        "mode": "testcase_eval_original_problem",
        "applied_rule": "none_original_problem",
        "generated_problem": {
            "status": "ok",
            "title": str(row.get("title", "")),
            "description": str(row.get("description", "")),
            "input_format": str(row.get("input", "")),
            "output_format": str(row.get("output", "")),
            "constraints": constraints,
            "samples": _samples(row.get("examples")),
            "notes": str(row.get("note", "")),
        },
        "new_schema_snapshot": tuple_snapshot,
        "source_metadata": {
            "dataset": "TestCase-Eval/problem",
            "url": str(row.get("url", "")),
            "rating": int(row.get("rating") or 0),
            "tags": [str(item) for item in as_list(row.get("tags"))],
        },
    }


def _joined_statement(row: dict[str, Any]) -> str:
    parts = [
        f"Title: {row.get('title', '')}",
        "",
        "Description:",
        str(row.get("description", "")),
        "",
        "Input:",
        str(row.get("input", "")),
        "",
        "Output:",
        str(row.get("output", "")),
    ]
    samples = _samples(row.get("examples"))
    if samples:
        parts.extend(["", "Examples:"])
        for sample in samples:
            parts.extend(["Input:", sample["input"], "Output:", sample["output"]])
    note = str(row.get("note", ""))
    if note:
        parts.extend(["", "Note:", note])
    return "\n".join(parts)


def write_tuple_input(path: Path, row: dict[str, Any]) -> None:
    from .utils import write_json

    write_json(path, problem_record_for_tuple_extract(row))
