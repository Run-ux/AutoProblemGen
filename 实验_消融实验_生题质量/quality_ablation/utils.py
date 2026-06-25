from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = PROJECT_ROOT / "总流程"
GENERATION_DIR = PROJECT_ROOT / "生成题面"
QUALITY_EVAL_DIR = PROJECT_ROOT / "题目质量评价"

for import_dir in (WORKFLOW_DIR, GENERATION_DIR, QUALITY_EVAL_DIR):
    text = str(import_dir)
    if text not in sys.path:
        sys.path.insert(0, text)


TUPLE_FIELDS = ("input_structure", "core_constraints", "objective", "invariant")
ALL_CONDITIONS = ("full", "no_tuple", "no_rules", "no_quality_loop")
GENERATED_CONDITIONS = ("no_tuple", "no_rules", "no_quality_loop")
DEFAULT_SUCCESSFUL_ROOT = PROJECT_ROOT / "总流程" / "successful_output"
DEFAULT_LLM_ENV = EXPERIMENT_ROOT / ".env"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def write_csv(path: str | Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\ufeff" + buffer.getvalue(), encoding="utf-8")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(text)


def safe_name(value: Any) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(value).strip())
    return cleaned or "unnamed"


def parse_conditions(raw_values: list[str] | None, *, default: tuple[str, ...]) -> list[str]:
    if not raw_values:
        return list(default)
    parsed: list[str] = []
    for raw in raw_values:
        for item in str(raw).split(","):
            condition = item.strip()
            if not condition:
                continue
            if condition not in ALL_CONDITIONS:
                raise ValueError(f"未知实验组：{condition}")
            if condition not in parsed:
                parsed.append(condition)
    return parsed


def limited_rows(rows: list[Any], limit: int | None) -> list[Any]:
    if limit is None:
        return rows
    if limit < 0:
        raise ValueError("--limit 不能为负数。")
    return rows[:limit]


def validate_shard(shard_count: int, shard_index: int) -> None:
    if shard_count < 1:
        raise ValueError("--shard-count 必须大于等于 1。")
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError("--shard-index 必须满足 0 <= shard_index < --shard-count。")


def sharded_rows(rows: list[Any], *, shard_count: int = 1, shard_index: int = 0) -> list[Any]:
    validate_shard(shard_count=shard_count, shard_index=shard_index)
    if shard_count == 1:
        return rows
    return [row for index, row in enumerate(rows) if index % shard_count == shard_index]


def shard_file_suffix(*, shard_count: int = 1, shard_index: int = 0) -> str:
    validate_shard(shard_count=shard_count, shard_index=shard_index)
    if shard_count == 1:
        return ""
    return f"_shard_{shard_index}_of_{shard_count}"


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def format_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "NA"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)
