from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import (
    DEFAULT_SUCCESSFUL_ROOT,
    TUPLE_FIELDS,
    limited_rows,
    read_json,
    sha256_file,
    stable_hash,
    utc_now_iso,
    write_json,
)


def build_manifest(
    *,
    successful_root: Path = DEFAULT_SUCCESSFUL_ROOT,
    output_path: Path,
    limit: int | None = None,
) -> dict[str, Any]:
    root = successful_root.resolve()
    candidates = _candidate_problem_dirs(root)
    problems: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for problem_dir in candidates:
        eligible, reason, item = _build_problem_entry(problem_dir)
        if eligible:
            problems.append(item)
        else:
            skipped.append({"problem_dir": str(problem_dir), "reason": reason})

    problems = limited_rows(problems, limit)
    manifest = {
        "schema_version": 1,
        "built_at": utc_now_iso(),
        "manifest_path": str(output_path.resolve()),
        "successful_root": str(root),
        "problem_count": len(problems),
        "eligible_count": len(problems),
        "skipped_count": len(skipped),
        "problems": problems,
        "skipped": skipped,
    }
    write_json(output_path, manifest)
    return manifest


def load_manifest(path: str | Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"manifest 顶层必须是对象：{path}")
    problems = payload.get("problems")
    if not isinstance(problems, list):
        raise ValueError(f"manifest 缺少 problems 数组：{path}")
    return payload


def _candidate_problem_dirs(root: Path) -> list[Path]:
    manifest_path = root / "_manifest.json"
    dirs: list[Path] = []
    seen: set[Path] = set()

    def add_dir(candidate: Path) -> None:
        if not candidate.is_dir():
            return
        resolved = candidate.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        dirs.append(candidate)

    if manifest_path.exists():
        payload = read_json(manifest_path)
        for item in payload.get("problems", []):
            if not isinstance(item, dict):
                continue
            problem_id = str(item.get("problem_id", "")).strip()
            raw_target = str(item.get("target_dir", "")).strip()
            target = Path(raw_target) if raw_target else root / problem_id
            if not target.exists() and problem_id:
                target = root / problem_id
            if target.exists():
                add_dir(target)
        # 上游 _manifest 可能滞后于目录内容；保留其顺序，再补充根目录中的新增题。
        for path in sorted(root.iterdir()):
            add_dir(path)
        return dirs
    return sorted(path for path in root.iterdir() if path.is_dir())


def _build_problem_entry(problem_dir: Path) -> tuple[bool, str, dict[str, Any]]:
    problem_id = problem_dir.name
    source_path = problem_dir / "source" / f"{problem_id}.json"
    metadata_path = problem_dir / "metadata" / "problem_record.json"
    if not source_path.is_file():
        return False, "missing_source_json", {}
    if not metadata_path.is_file():
        return False, "missing_problem_record", {}

    try:
        source_payload = read_json(source_path)
        metadata = read_json(metadata_path)
    except Exception as exc:  # noqa: BLE001 - manifest 构建阶段只记录不可读原因。
        return False, f"invalid_json:{type(exc).__name__}", {}

    if not _has_generation_source_contract(source_payload):
        return False, "source_missing_original_problem_or_tuple_fields", {}

    problem_record = metadata.get("problem", {}) if isinstance(metadata, dict) else {}
    if problem_record.get("status") != "verified":
        return False, "problem_not_verified", {}

    generation = problem_record.get("generation", {})
    if not isinstance(generation, dict):
        return False, "generation_record_missing", {}
    artifact_name = Path(str(generation.get("artifact_path", ""))).name
    markdown_name = Path(str(generation.get("markdown_path", ""))).name
    if not artifact_name or not markdown_name:
        return False, "final_artifact_or_markdown_missing_in_metadata", {}

    artifact_path = problem_dir / "artifacts" / artifact_name
    markdown_path = problem_dir / "output" / markdown_name
    if not artifact_path.is_file():
        return False, "final_artifact_file_missing", {}
    if not markdown_path.is_file():
        return False, "final_markdown_file_missing", {}

    quality_report_path = _local_optional_path(
        problem_dir / "reports",
        str(generation.get("quality_report_json_path", "")),
    )
    iteration_summary_path = _local_optional_path(
        problem_dir / "artifacts",
        str(generation.get("iteration_summary_path", "")),
    )

    item = {
        "problem_id": problem_id,
        "successful_problem_dir": str(problem_dir.resolve()),
        "source_path": str(source_path.resolve()),
        "metadata_path": str(metadata_path.resolve()),
        "seed_hash": stable_hash(source_payload),
        "source_file_sha256": sha256_file(source_path),
        "original_title": str(source_payload.get("original_problem", {}).get("title", "")),
        "source": str(source_payload.get("source", "")),
        "full": {
            "full_reused": True,
            "full_source_dir": str(problem_dir.resolve()),
            "artifact_path": str(artifact_path.resolve()),
            "markdown_path": str(markdown_path.resolve()),
            "quality_report_json_path": str(quality_report_path.resolve()) if quality_report_path else "",
            "iteration_summary_path": str(iteration_summary_path.resolve()) if iteration_summary_path else "",
            "final_round_index": generation.get("final_round_index"),
            "generated_status": str(generation.get("generated_status", "")),
        },
    }
    return True, "", item


def _has_generation_source_contract(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if not isinstance(payload.get("original_problem"), dict) or not payload["original_problem"]:
        return False
    return all(field in payload and isinstance(payload.get(field), dict) for field in TUPLE_FIELDS)


def _local_optional_path(base_dir: Path, exported_path: str) -> Path | None:
    name = Path(exported_path).name
    if not name:
        return None
    candidate = base_dir / name
    return candidate if candidate.is_file() else None
