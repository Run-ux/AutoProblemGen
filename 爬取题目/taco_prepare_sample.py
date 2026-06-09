from __future__ import annotations

import argparse
import ast
import hashlib
import json
import random
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


DATASET_REPO = "BAAI/TACO"
PARQUET_FILES = [
    ("ALL/test-00000-of-00001.parquet", 245_784_461),
    ("ALL/train-00000-of-00009.parquet", 286_917_870),
    ("ALL/train-00001-of-00009.parquet", 327_223_660),
    ("ALL/train-00002-of-00009.parquet", 177_530_416),
    ("ALL/train-00003-of-00009.parquet", 179_463_335),
    ("ALL/train-00004-of-00009.parquet", 205_709_320),
    ("ALL/train-00005-of-00009.parquet", 271_713_449),
    ("ALL/train-00006-of-00009.parquet", 213_807_578),
    ("ALL/train-00007-of-00009.parquet", 260_118_596),
    ("ALL/train-00008-of-00009.parquet", 251_576_257),
]
METADATA_COLUMNS = [
    "difficulty",
    "raw_tags",
    "tags",
    "skill_types",
    "name",
    "source",
    "url",
]
FULL_COLUMNS = [
    "question",
    "solutions",
    "starter_code",
    "input_output",
    "difficulty",
    "raw_tags",
    "name",
    "source",
    "tags",
    "skill_types",
    "url",
    "Expected Auxiliary Space",
    "time_limit",
    "date",
    "picture_num",
    "memory_limit",
    "Expected Time Complexity",
]
COVERAGE_FIELDS = ("difficulty", "raw_tags", "tags", "skill_types")
EMPTY_LABEL = "<EMPTY>"
KNOWN_DIFFICULTIES = {"EASY", "MEDIUM", "MEDIUM_HARD", "HARD", "VERY_HARD"}
DEFAULT_COVERAGE_FIELDS = ("difficulty", "tags", "skill_types")
ALLOWED_COVERAGE_FIELDS = {"difficulty", "raw_tags", "tags", "skill_types"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下载 TACO 数据集并抽取覆盖约束样本。")
    parser.add_argument(
        "--output-root",
        default=str(Path(__file__).resolve().parent / "output" / "taco"),
        help="TACO 本地输出根目录。",
    )
    parser.add_argument("--sample-size", type=int, default=400, help="抽样题目数量。")
    parser.add_argument("--seed", type=int, default=20260522, help="随机种子。")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="跳过下载，直接使用已存在的 parquet 文件。",
    )
    parser.add_argument(
        "--unicode-filter",
        action="store_true",
        help="按 UniCode 论文的数据池方法筛选：已知难度、清晰 I/O、去重、15 个最高频算法标签。",
    )
    parser.add_argument(
        "--exclude-difficulties",
        default="",
        help="逗号分隔的难度黑名单，例如 EASY。",
    )
    parser.add_argument(
        "--exclude-sample-dir",
        default="",
        help="递归读取已有样本 JSON，并按 problem_id 从候选池中排除。",
    )
    parser.add_argument(
        "--coverage-fields",
        default=",".join(DEFAULT_COVERAGE_FIELDS),
        help="逗号分隔的覆盖字段，可选 difficulty,raw_tags,tags,skill_types。",
    )
    parser.add_argument(
        "--sample-dir-name",
        default="sample_400_autoproblemgen",
        help="输出题目目录名，路径相对于 output-root。",
    )
    parser.add_argument(
        "--aggregate-name",
        default="taco_sample_400.json",
        help="聚合样本 JSON 文件名，路径相对于 output-root。",
    )
    parser.add_argument(
        "--manifest-name",
        default="manifest.json",
        help="manifest JSON 文件名，路径相对于 output-root。",
    )
    parser.add_argument(
        "--coverage-name",
        default="coverage_report.json",
        help="覆盖报告 JSON 文件名，路径相对于 output-root。",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=0,
        help="每个分片目录包含的题目数；0 表示不分片。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root).resolve()
    raw_dir = output_root / "raw_parquet"
    sample_dir = resolve_output_child(output_root, args.sample_dir_name, "样本输出目录")
    aggregate_path = resolve_output_child(output_root, args.aggregate_name, "聚合样本 JSON")
    manifest_path = resolve_output_child(output_root, args.manifest_name, "manifest JSON")
    coverage_path = resolve_output_child(output_root, args.coverage_name, "覆盖报告 JSON")
    coverage_fields = parse_coverage_fields(args.coverage_fields)
    if args.chunk_size < 0:
        raise ValueError("--chunk-size 不能为负数。")

    output_root.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    ensure_output_targets_available(sample_dir, [aggregate_path, manifest_path, coverage_path])
    sample_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_download:
        download_dataset(raw_dir)
    parquet_paths = [raw_dir / Path(path).name for path, _ in PARQUET_FILES]
    ensure_parquet_files(parquet_paths)

    print("[taco] 读取元数据并计算覆盖集合。", flush=True)
    metadata_rows = load_metadata_rows(parquet_paths)
    full_rows_for_filter: list[tuple[str, dict[str, Any]]] | None = None
    exclude_report: dict[str, Any] = {}
    if args.unicode_filter:
        print("[taco] 按 UniCode 论文方法筛选候选池。", flush=True)
        full_rows_for_filter = load_all_records(parquet_paths)
        metadata_by_key = {row["key"]: row for row in metadata_rows}
        excluded_difficulties = parse_csv_set(args.exclude_difficulties)
        eligible_keys, filter_report = build_unicode_filtered_pool(
            full_rows_for_filter,
            metadata_by_key,
            excluded_difficulties=excluded_difficulties,
        )
        target_tags = set(filter_report["target_tags"])
        metadata_rows = [
            {**row, "tags": [tag for tag in row["tags"] if tag in target_tags]}
            for row in metadata_rows
            if row["key"] in eligible_keys
        ]
        if len(metadata_rows) < args.sample_size:
            raise RuntimeError(
                f"UniCode 筛选后候选池不足：pool={len(metadata_rows)} sample_size={args.sample_size}"
            )
    else:
        filter_report = {}

    if args.exclude_sample_dir:
        exclude_sample_dir = Path(args.exclude_sample_dir).resolve()
        excluded_problem_ids, exclude_report = load_excluded_problem_ids(exclude_sample_dir)
        if full_rows_for_filter is None:
            print("[taco] 读取完整字段以匹配待排除 problem_id。", flush=True)
            full_rows_for_filter = load_all_records(parquet_paths)
        excluded_keys, match_report = match_excluded_problem_keys(
            full_rows_for_filter,
            excluded_problem_ids,
        )
        before_exclude = len(metadata_rows)
        metadata_rows = [row for row in metadata_rows if row["key"] not in excluded_keys]
        exclude_report.update(match_report)
        exclude_report["candidate_rows_before_exclude"] = before_exclude
        exclude_report["candidate_rows_after_exclude"] = len(metadata_rows)
        print(
            f"[taco] 已排除已有样本：ids={len(excluded_problem_ids)} rows={len(excluded_keys)}。",
            flush=True,
        )

    if len(metadata_rows) < args.sample_size:
        raise RuntimeError(
            f"候选池不足：pool={len(metadata_rows)} sample_size={args.sample_size}"
        )

    selected_keys, coverage_report = select_sample_keys(
        metadata_rows,
        sample_size=args.sample_size,
        seed=args.seed,
        coverage_fields=coverage_fields,
        stratify_field="difficulty",
    )

    print("[taco] 读取选中题目的完整字段。", flush=True)
    if full_rows_for_filter is None:
        selected_records = load_selected_records(parquet_paths, selected_keys)
    else:
        selected_records = [(key, row) for key, row in full_rows_for_filter if key in selected_keys]
    prepared_records = [
        prepare_autoproblemgen_record(record, key)
        for key, record in selected_records
    ]

    write_problem_directory(sample_dir, prepared_records, chunk_size=args.chunk_size)
    write_json_atomic(aggregate_path, prepared_records)

    manifest = {
        "dataset": DATASET_REPO,
        "sample_size": len(prepared_records),
        "seed": args.seed,
        "raw_parquet_dir": str(raw_dir),
        "aggregate_json": str(aggregate_path),
        "autoproblemgen_input_dir": str(sample_dir),
        "coverage_report": str(coverage_path),
        "chunk_size": args.chunk_size,
        "coverage_fields": coverage_report.get("coverage_fields", []),
        "unicode_filter": bool(args.unicode_filter),
        "exclude_sample_dir": str(Path(args.exclude_sample_dir).resolve())
        if args.exclude_sample_dir
        else "",
        "excluded_sample_report": exclude_report,
    }
    if filter_report:
        manifest["unicode_filter_report"] = filter_report
    write_json_atomic(manifest_path, manifest)
    write_json_atomic(coverage_path, coverage_report)

    print(f"[taco] 已写入聚合样本：{aggregate_path}", flush=True)
    print(f"[taco] 已写入总流程输入目录：{sample_dir}", flush=True)
    print(f"[taco] 已写入覆盖报告：{coverage_path}", flush=True)
    return 0


def download_dataset(raw_dir: Path) -> None:
    for repo_path, expected_size in PARQUET_FILES:
        filename = Path(repo_path).name
        target = raw_dir / filename
        if target.exists() and target.stat().st_size == expected_size:
            print(f"[taco] 已存在，跳过：{filename}", flush=True)
            continue
        if target.exists() and target.stat().st_size != expected_size:
            raise RuntimeError(
                f"本地文件大小不匹配，请手动检查后再处理：{target} "
                f"expected={expected_size} actual={target.stat().st_size}"
            )

        url = f"https://huggingface.co/datasets/{DATASET_REPO}/resolve/main/{repo_path}"
        tmp_path = target.with_suffix(target.suffix + ".tmp")
        downloaded = tmp_path.stat().st_size if tmp_path.exists() else 0
        headers = {}
        mode = "ab" if downloaded else "wb"
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"

        request = urllib.request.Request(url, headers=headers)
        print(f"[taco] 下载 {repo_path} -> {target}", flush=True)
        with urllib.request.urlopen(request, timeout=120) as response, tmp_path.open(mode + "") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

        actual_size = tmp_path.stat().st_size
        if actual_size != expected_size:
            raise RuntimeError(
                f"下载文件大小不完整：{tmp_path} expected={expected_size} actual={actual_size}"
            )
        tmp_path.replace(target)


def ensure_parquet_files(paths: list[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("缺少 TACO parquet 文件：\n" + "\n".join(missing))


def resolve_output_child(output_root: Path, name: str, label: str) -> Path:
    if not name.strip():
        raise ValueError(f"{label}不能为空。")
    child = Path(name)
    if child.is_absolute():
        raise ValueError(f"{label}必须是相对于 output-root 的路径：{name}")
    resolved = (output_root / child).resolve()
    if resolved != output_root and output_root not in resolved.parents:
        raise ValueError(f"{label}不能指向 output-root 之外：{name}")
    return resolved


def ensure_output_targets_available(sample_dir: Path, output_files: list[Path]) -> None:
    if sample_dir.exists() and not sample_dir.is_dir():
        raise FileExistsError(f"样本输出路径已存在且不是目录：{sample_dir}")
    if sample_dir.exists() and any(sample_dir.iterdir()):
        raise FileExistsError(f"样本输出目录已存在且非空，请更换输出目录：{sample_dir}")

    existing_files = [str(path) for path in output_files if path.exists()]
    if existing_files:
        raise FileExistsError(
            "输出文件已存在，为避免覆盖请更换文件名：\n" + "\n".join(existing_files)
        )


def parse_coverage_fields(value: str) -> tuple[str, ...]:
    fields = tuple(item.strip() for item in value.split(",") if item.strip())
    if not fields:
        raise ValueError("--coverage-fields 至少需要包含一个字段。")
    unknown = sorted(set(fields) - ALLOWED_COVERAGE_FIELDS)
    if unknown:
        raise ValueError(
            "--coverage-fields 包含未知字段："
            + ",".join(unknown)
            + f"；可选字段：{','.join(sorted(ALLOWED_COVERAGE_FIELDS))}"
        )
    if len(set(fields)) != len(fields):
        raise ValueError("--coverage-fields 存在重复字段。")
    return fields


def load_excluded_problem_ids(sample_dir: Path) -> tuple[set[str], dict[str, Any]]:
    if not sample_dir.exists():
        raise FileNotFoundError(f"待排除样本目录不存在：{sample_dir}")
    if not sample_dir.is_dir():
        raise NotADirectoryError(f"待排除样本路径不是目录：{sample_dir}")

    problem_ids: set[str] = set()
    duplicate_count = 0
    json_files = sorted(sample_dir.rglob("*.json"))
    if not json_files:
        raise RuntimeError(f"待排除样本目录下没有 JSON 文件：{sample_dir}")

    for path in json_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"样本 JSON 解析失败：{path}") from exc
        problem_id = normalize_scalar(payload.get("problem_id")) if isinstance(payload, dict) else ""
        if not problem_id:
            raise ValueError(f"样本 JSON 缺少 problem_id：{path}")
        if problem_id in problem_ids:
            duplicate_count += 1
        problem_ids.add(problem_id)

    return problem_ids, {
        "sample_dir": str(sample_dir),
        "json_file_count": len(json_files),
        "unique_problem_id_count": len(problem_ids),
        "duplicate_problem_id_count": duplicate_count,
    }


def match_excluded_problem_keys(
    full_rows: list[tuple[str, dict[str, Any]]],
    excluded_problem_ids: set[str],
) -> tuple[set[str], dict[str, Any]]:
    excluded_keys: set[str] = set()
    matched_problem_ids: set[str] = set()

    for key, record in full_rows:
        problem_id = make_problem_id(record, key)
        if problem_id in excluded_problem_ids:
            excluded_keys.add(key)
            matched_problem_ids.add(problem_id)

    unmatched_ids = sorted(excluded_problem_ids - matched_problem_ids)
    if unmatched_ids:
        preview = "\n".join(unmatched_ids[:20])
        raise RuntimeError(
            "部分待排除 problem_id 无法映射回 raw parquet，已停止以避免漏排：\n"
            + preview
        )

    return excluded_keys, {
        "matched_problem_id_count": len(matched_problem_ids),
        "matched_raw_row_count": len(excluded_keys),
    }


def load_metadata_rows(parquet_paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    global_index = 0
    for parquet_path in parquet_paths:
        table = pq.read_table(parquet_path, columns=METADATA_COLUMNS)
        data = table.to_pylist()
        for local_index, row in enumerate(data):
            parsed = {
                "key": f"{parquet_path.name}:{local_index}",
                "file": parquet_path.name,
                "local_index": local_index,
                "global_index": global_index,
                "difficulty": normalize_scalar(row.get("difficulty")),
                "raw_tags": parse_list_field(row.get("raw_tags")),
                "tags": parse_list_field(row.get("tags")),
                "skill_types": parse_list_field(row.get("skill_types")),
                "source": normalize_scalar(row.get("source")),
                "url": normalize_scalar(row.get("url")),
                "name": normalize_scalar(row.get("name")),
            }
            rows.append(parsed)
            global_index += 1
    return rows


def select_sample_keys(
    rows: list[dict[str, Any]],
    *,
    sample_size: int,
    seed: int,
    coverage_fields: tuple[str, ...] = COVERAGE_FIELDS,
    stratify_field: str | None = None,
) -> tuple[set[str], dict[str, Any]]:
    if sample_size <= 0:
        raise ValueError("sample_size 必须为正整数。")
    if sample_size > len(rows):
        raise ValueError(f"sample_size={sample_size} 超过数据总量 {len(rows)}。")

    rng = random.Random(seed)
    selected: dict[str, dict[str, Any]] = {}
    label_to_keys = build_label_index(rows, coverage_fields=coverage_fields)
    universe = set(label_to_keys)
    uncovered = set(universe)
    stratum_targets = proportional_targets(rows, sample_size) if stratify_field == "difficulty" else {}
    selected_by_stratum: Counter[str] = Counter()

    while uncovered and len(selected) < sample_size:
        candidates = [
            row
            for row in rows
            if row["key"] not in selected and coverage_labels(row, coverage_fields) & uncovered
        ]
        if stratum_targets:
            candidates = [
                row
                for row in candidates
                if selected_by_stratum[row[stratify_field]] < stratum_targets[row[stratify_field]]
            ]
        if not candidates:
            break
        best = max(
            candidates,
            key=lambda row: (
                len(coverage_labels(row) & uncovered),
                rarity_score(row, label_to_keys, coverage_fields),
                -row["global_index"],
            ),
        )
        selected[best["key"]] = best
        if stratify_field is not None:
            selected_by_stratum[best[stratify_field]] += 1
        uncovered -= coverage_labels(best, coverage_fields)

    if uncovered:
        uncovered_by_field = group_coverage_labels(uncovered)
        raise RuntimeError(
            "无法在样本容量内覆盖全部标签，未覆盖标签："
            + json.dumps(uncovered_by_field, ensure_ascii=False)
        )

    target_by_difficulty = stratum_targets or proportional_targets(rows, sample_size)
    by_difficulty: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_difficulty[row["difficulty"]].append(row)
    for bucket in by_difficulty.values():
        rng.shuffle(bucket)

    selected_difficulty = Counter(row["difficulty"] for row in selected.values())
    while len(selected) < sample_size:
        deficits = [
            (target_by_difficulty[difficulty] - selected_difficulty[difficulty], difficulty)
            for difficulty in sorted(target_by_difficulty)
            if target_by_difficulty[difficulty] > selected_difficulty[difficulty]
        ]
        if not deficits:
            break
        deficits.sort(reverse=True)
        picked = None
        for _, difficulty in deficits:
            while by_difficulty[difficulty] and by_difficulty[difficulty][-1]["key"] in selected:
                by_difficulty[difficulty].pop()
            if by_difficulty[difficulty]:
                picked = by_difficulty[difficulty].pop()
                break
        if picked is None:
            remaining = [
                row
                for row in rows
                if row["key"] not in selected
                and selected_difficulty[row["difficulty"]] < target_by_difficulty[row["difficulty"]]
            ]
            picked = rng.choice(remaining)
        selected[picked["key"]] = picked
        selected_difficulty[picked["difficulty"]] += 1

    coverage_report = build_coverage_report(rows, list(selected.values()), universe, coverage_fields)
    return set(selected), coverage_report


def build_label_index(
    rows: list[dict[str, Any]],
    *,
    coverage_fields: tuple[str, ...] = COVERAGE_FIELDS,
) -> dict[str, set[str]]:
    label_to_keys: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for label in coverage_labels(row, coverage_fields):
            label_to_keys[label].add(row["key"])
    return label_to_keys


def coverage_labels(
    row: dict[str, Any],
    coverage_fields: tuple[str, ...] = COVERAGE_FIELDS,
) -> set[str]:
    labels: set[str] = set()
    if "difficulty" in coverage_fields:
        labels.add(f"difficulty::{row['difficulty']}")
    for field in ("raw_tags", "tags", "skill_types"):
        if field not in coverage_fields:
            continue
        values = row[field] or [EMPTY_LABEL]
        labels.update(f"{field}::{value}" for value in values)
    return labels


def rarity_score(
    row: dict[str, Any],
    label_to_keys: dict[str, set[str]],
    coverage_fields: tuple[str, ...],
) -> float:
    score = 0.0
    for label in coverage_labels(row, coverage_fields):
        score += 1.0 / max(1, len(label_to_keys[label]))
    return score


def proportional_targets(rows: list[dict[str, Any]], sample_size: int) -> dict[str, int]:
    counts = Counter(row["difficulty"] for row in rows)
    raw_targets = {
        difficulty: counts[difficulty] * sample_size / len(rows)
        for difficulty in counts
    }
    targets = {difficulty: int(value) for difficulty, value in raw_targets.items()}
    for difficulty in counts:
        targets[difficulty] = max(1, targets[difficulty])
    while sum(targets.values()) < sample_size:
        difficulty = max(
            counts,
            key=lambda item: (raw_targets[item] - targets[item], counts[item]),
        )
        targets[difficulty] += 1
    while sum(targets.values()) > sample_size:
        difficulty = max(targets, key=lambda item: (targets[item], -counts[item]))
        if targets[difficulty] <= 1:
            break
        targets[difficulty] -= 1
    return targets


def build_coverage_report(
    rows: list[dict[str, Any]],
    selected_rows: list[dict[str, Any]],
    universe: set[str],
    coverage_fields: tuple[str, ...],
) -> dict[str, Any]:
    selected_labels: set[str] = set()
    for row in selected_rows:
        selected_labels |= coverage_labels(row, coverage_fields)
    missing = universe - selected_labels
    return {
        "total_rows": len(rows),
        "sample_rows": len(selected_rows),
        "coverage_fields": list(coverage_fields),
        "coverage_complete": not missing,
        "label_counts_full": count_labels(rows, coverage_fields),
        "label_counts_sample": count_labels(selected_rows, coverage_fields),
        "missing_labels": group_coverage_labels(missing),
        "difficulty_distribution_full": dict(Counter(row["difficulty"] for row in rows)),
        "difficulty_distribution_sample": dict(Counter(row["difficulty"] for row in selected_rows)),
        "raw_tags_distribution_full": value_distribution(rows, "raw_tags"),
        "raw_tags_distribution_sample": value_distribution(selected_rows, "raw_tags"),
        "tags_distribution_full": value_distribution(rows, "tags"),
        "tags_distribution_sample": value_distribution(selected_rows, "tags"),
        "skill_types_distribution_full": value_distribution(rows, "skill_types"),
        "skill_types_distribution_sample": value_distribution(selected_rows, "skill_types"),
    }


def count_labels(rows: list[dict[str, Any]], coverage_fields: tuple[str, ...]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter.update(coverage_labels(row, coverage_fields))
    return dict(sorted(counter.items()))


def value_distribution(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        values = row[field] if isinstance(row.get(field), list) else []
        counter.update(values or [EMPTY_LABEL])
    return dict(counter.most_common())


def group_coverage_labels(labels: set[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for label in sorted(labels):
        field, value = label.split("::", 1)
        grouped[field].append(value)
    return dict(grouped)


def load_selected_records(
    parquet_paths: list[Path],
    selected_keys: set[str],
) -> list[tuple[str, dict[str, Any]]]:
    selected_by_file: dict[str, set[int]] = defaultdict(set)
    for key in selected_keys:
        file_name, local_index_text = key.rsplit(":", 1)
        selected_by_file[file_name].add(int(local_index_text))

    records: list[tuple[str, dict[str, Any]]] = []
    for parquet_path in parquet_paths:
        wanted = selected_by_file.get(parquet_path.name)
        if not wanted:
            continue
        table = pq.read_table(parquet_path, columns=FULL_COLUMNS)
        data = table.to_pylist()
        for local_index in sorted(wanted):
            key = f"{parquet_path.name}:{local_index}"
            records.append((key, data[local_index]))
    return records


def load_all_records(parquet_paths: list[Path]) -> list[tuple[str, dict[str, Any]]]:
    records: list[tuple[str, dict[str, Any]]] = []
    for parquet_path in parquet_paths:
        table = pq.read_table(parquet_path, columns=FULL_COLUMNS)
        for local_index, row in enumerate(table.to_pylist()):
            records.append((f"{parquet_path.name}:{local_index}", row))
    return records


def build_unicode_filtered_pool(
    full_rows: list[tuple[str, dict[str, Any]]],
    metadata_by_key: dict[str, dict[str, Any]],
    *,
    excluded_difficulties: set[str],
) -> tuple[set[str], dict[str, Any]]:
    # UniCode 论文的数据池筛选思想：保留竞赛难度题、去掉重复题和 I/O 规格不清的题，
    # 再围绕筛后池的高频算法标签构建目标覆盖。
    eligible: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    reject_counts: Counter[str] = Counter()
    seen_url: set[str] = set()
    seen_question_hash: set[str] = set()

    for key, record in full_rows:
        meta = metadata_by_key[key]
        if meta["difficulty"] not in KNOWN_DIFFICULTIES:
            reject_counts["unknown_difficulty"] += 1
            continue
        if meta["difficulty"] in excluded_difficulties:
            reject_counts["excluded_difficulty"] += 1
            continue
        if not normalize_scalar(record.get("question")):
            reject_counts["empty_question"] += 1
            continue
        solutions = parse_json_field(record.get("solutions"), default=[])
        if not isinstance(solutions, list) or not first_text(solutions):
            reject_counts["missing_solution"] += 1
            continue
        input_output = parse_json_field(record.get("input_output"), default={})
        if not has_clear_input_output(input_output):
            reject_counts["unclear_input_output"] += 1
            continue
        if not meta["tags"]:
            reject_counts["missing_tags"] += 1
            continue

        url = meta["url"]
        if url and url in seen_url:
            reject_counts["duplicate_url"] += 1
            continue
        question_hash = normalized_question_hash(record.get("question"))
        if question_hash in seen_question_hash:
            reject_counts["duplicate_question"] += 1
            continue
        if url:
            seen_url.add(url)
        seen_question_hash.add(question_hash)
        eligible.append((key, record, meta))

    tag_counter: Counter[str] = Counter()
    for _, _, meta in eligible:
        tag_counter.update(meta["tags"])
    target_tags = [tag for tag, _ in tag_counter.most_common(15)]
    eligible_keys = {
        key
        for key, _, meta in eligible
        if set(meta["tags"]) & set(target_tags)
    }
    reject_counts["outside_top_15_tags"] = len(eligible) - len(eligible_keys)

    return eligible_keys, {
        "method": "UniCode-style filtering: known difficulty, clear input/output, deduplication, top-15 prevalent tags",
        "known_difficulties": sorted(KNOWN_DIFFICULTIES),
        "excluded_difficulties": sorted(excluded_difficulties),
        "target_tags": target_tags,
        "input_rows": len(full_rows),
        "eligible_before_top_tags": len(eligible),
        "eligible_after_top_tags": len(eligible_keys),
        "reject_counts": dict(reject_counts),
    }


def parse_csv_set(value: str) -> set[str]:
    return {item.strip().upper() for item in value.split(",") if item.strip()}


def has_clear_input_output(input_output: Any) -> bool:
    if not isinstance(input_output, dict):
        return False
    inputs = input_output.get("inputs")
    outputs = input_output.get("outputs")
    if not isinstance(inputs, list) or not isinstance(outputs, list):
        return False
    if not inputs or not outputs or len(inputs) != len(outputs):
        return False
    return all(normalize_scalar(item) for item in inputs) and all(
        normalize_scalar(item) for item in outputs
    )


def normalized_question_hash(value: Any) -> str:
    text = normalize_scalar(value).lower()
    text = re.sub(r"\s+", " ", text)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def prepare_autoproblemgen_record(record: dict[str, Any], key: str) -> dict[str, Any]:
    solutions = parse_json_field(record.get("solutions"), default=[])
    title = normalize_scalar(record.get("name")) or title_from_url(record.get("url")) or "TACO Problem"
    problem_id = make_problem_id(record, key)
    standard_solution = first_text(solutions)

    # 单题输入只保留总流程实际消费的字段；覆盖统计保存在 coverage_report.json。
    prepared = {
        "problem_id": problem_id,
        "title": title,
        "description": normalize_scalar(record.get("question")),
        "input": "",
        "output": "",
        "constraints": format_constraints(record),
        "source": normalize_scalar(record.get("source")) or "taco",
        "standard_solution_code": standard_solution,
    }
    sections = split_statement_sections(prepared["description"])
    prepared["input"] = sections["input"]
    prepared["output"] = sections["output"]
    merged_constraints = "\n\n".join(
        part for part in [sections["constraints"], prepared["constraints"]] if part
    )
    prepared["constraints"] = merged_constraints
    return prepared


def make_problem_id(record: dict[str, Any], key: str) -> str:
    source = normalize_scalar(record.get("source")) or "taco"
    url = normalize_scalar(record.get("url"))
    digest_source = f"{key}|{url}|{normalize_scalar(record.get('name'))}"
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:12]
    return f"taco_{slugify(source)}_{digest}"


def title_from_url(url: Any) -> str:
    text = normalize_scalar(url)
    if not text:
        return ""
    tail = text.rstrip("/").split("/")[-1]
    return tail.replace("-", " ").replace("_", " ").strip() or ""


def split_statement_sections(statement: str) -> dict[str, str]:
    normalized = statement.replace("\r\n", "\n").replace("\r", "\n").strip()
    sections = {"description": [], "input": [], "output": [], "constraints": []}
    current = "description"
    for line in normalized.split("\n"):
        heading = re.sub(r"\s+", " ", line.strip().rstrip(":")).lower()
        if heading in {"example", "examples", "sample", "sample input", "sample output", "note", "notes"}:
            break
        if heading in {"input", "input format"}:
            current = "input"
            continue
        if heading in {"output", "output format"}:
            current = "output"
            continue
        if heading in {"constraints", "constraint", "limits"}:
            current = "constraints"
            continue
        sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def format_constraints(record: dict[str, Any]) -> str:
    lines = []
    for key, label in [
        ("time_limit", "time limit"),
        ("memory_limit", "memory limit"),
        ("Expected Time Complexity", "expected time complexity"),
        ("Expected Auxiliary Space", "expected auxiliary space"),
    ]:
        value = normalize_scalar(record.get(key))
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def parse_list_field(value: Any) -> list[str]:
    parsed = parse_json_field(value, default=[])
    if parsed is None:
        return []
    if isinstance(parsed, list):
        return [normalize_scalar(item) for item in parsed if normalize_scalar(item)]
    if isinstance(parsed, str) and parsed.strip():
        return [parsed.strip()]
    return []


def parse_json_field(value: Any, *, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return default
    text = value.strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return default


def first_text(values: Any) -> str:
    if isinstance(values, list):
        for value in values:
            text = normalize_scalar(value)
            if text:
                return text
    return ""


def normalize_scalar(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"none", "nan", "null"}:
        return ""
    return text


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "unknown"


def write_problem_directory(
    sample_dir: Path,
    records: list[dict[str, Any]],
    *,
    chunk_size: int = 0,
) -> None:
    sample_dir.mkdir(parents=True, exist_ok=True)
    width = len(str(len(records)))
    for index, record in enumerate(records, start=1):
        item = dict(record)
        filename = f"{index:0{width}d}_{item['problem_id']}.json"
        if chunk_size:
            chunk_start = ((index - 1) // chunk_size) * chunk_size + 1
            chunk_end = min(chunk_start + chunk_size - 1, len(records))
            target_dir = sample_dir / f"part_{chunk_start:0{width}d}_{chunk_end:0{width}d}"
        else:
            target_dir = sample_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(target_dir / filename, item)


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[taco] 失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
