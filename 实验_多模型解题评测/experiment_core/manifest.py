from __future__ import annotations

from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .utils import atomic_write_json, read_json, sha256_file, stable_hash, utc_now_iso


MANIFEST_SCHEMA_VERSION = 1
REQUIRED_SOURCES = ("random", "adversarial", "small_challenge")


class ManifestError(RuntimeError):
    """冻结清单或其引用产物不满足实验合同。"""


def _resolve_path(raw_path: Any, *, base_dir: Path) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else (base_dir / path).resolve()


def _exclude(
    excluded: list[dict[str, Any]],
    *,
    workflow_summary: Path,
    source_problem_id: str,
    reason: str,
    details: str = "",
) -> None:
    excluded.append(
        {
            "workflow_summary": str(workflow_summary.resolve()),
            "source_problem_id": source_problem_id,
            "reason": reason,
            "details": details,
        }
    )


def _exclude_successful(
    excluded: list[dict[str, Any]],
    *,
    successful_dir: Path,
    metadata_path: Path,
    source_problem_id: str,
    reason: str,
    details: str = "",
) -> None:
    excluded.append(
        {
            "successful_dir": str(successful_dir.resolve()),
            "metadata_path": str(metadata_path.resolve()),
            "source_problem_id": source_problem_id,
            "reason": reason,
            "details": details,
        }
    )


def _path_leaf(raw_path: Any) -> str:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return ""
    value = raw_path.strip()
    candidates = [PureWindowsPath(value).name, PurePosixPath(value).name]
    return min((name for name in candidates if name), key=len, default="")


def _copied_export_path(successful_dir: Path, folder: str, raw_path: Any) -> Path | None:
    filename = _path_leaf(raw_path)
    if not filename:
        return None
    return successful_dir / folder / filename


def _validate_verification_artifact(payload: dict[str, Any]) -> tuple[Counter[str], int]:
    solved_cases = payload.get("bruteforce_verification", {}).get("solved_cases")
    if not isinstance(solved_cases, list) or not solved_cases:
        raise ManifestError("缺少 bruteforce_verification.solved_cases。")
    source_counts: Counter[str] = Counter()
    for case in solved_cases:
        if not isinstance(case, dict):
            raise ManifestError("solved_cases 中存在非对象元素。")
        source = str(case.get("source", ""))
        if source in REQUIRED_SOURCES:
            source_counts[source] += 1
        if not isinstance(case.get("input"), str) or not isinstance(case.get("output"), str):
            raise ManifestError("solved_cases 中存在缺少字符串 input/output 的用例。")
    missing = [source for source in REQUIRED_SOURCES if source_counts[source] <= 0]
    if missing:
        raise ManifestError("缺少测试类别: " + ", ".join(missing))

    large_payload = payload.get("large_scale_truth_outputs")
    if not isinstance(large_payload, dict) or large_payload.get("status") != "ok":
        raise ManifestError("large_scale_truth_outputs.status 必须为 ok。")
    large_cases = large_payload.get("cases")
    if not isinstance(large_cases, list) or not large_cases:
        raise ManifestError("缺少大规模真值用例。")
    if int(large_payload.get("failure_count", 0)) != 0:
        raise ManifestError("大规模真值生成存在失败用例。")
    for case in large_cases:
        if not isinstance(case, dict) or not isinstance(case.get("input"), str) or not isinstance(
            case.get("output"), str
        ):
            raise ManifestError("大规模真值中存在非法 input/output。")

    checker = payload.get("checker", {})
    if isinstance(checker, dict) and checker.get("needs_checker") is True:
        checker_code = checker.get("verified_checker_code") or checker.get("checker_code")
        if not isinstance(checker_code, str) or not checker_code.strip():
            raise ManifestError("题目要求 checker，但验证产物缺少已验证 checker 代码。")

    limits = payload.get("standard_solution_verification", {}).get("standard_solution_limits")
    if not isinstance(limits, dict):
        raise ManifestError("缺少标准解执行限制。")
    if float(limits.get("timeout_seconds", 0)) <= 0 or int(limits.get("memory_limit_mb", 0)) <= 0:
        raise ManifestError("标准解执行限制必须为正数。")
    return source_counts, len(large_cases)


def _load_validated_artifacts(
    generation_path: Path, verification_path: Path
) -> tuple[dict[str, Any], dict[str, Any], Counter[str], int, dict[str, Any], str]:
    generation_artifact = read_json(generation_path)
    verification_artifact = read_json(verification_path)
    if not isinstance(generation_artifact, dict) or not isinstance(verification_artifact, dict):
        raise ManifestError("artifact 顶层必须是对象。")
    source_counts, large_count = _validate_verification_artifact(verification_artifact)
    generated_problem = generation_artifact.get("generated_problem")
    if not isinstance(generated_problem, dict) or generated_problem.get("status") != "ok":
        raise ManifestError("generated_problem.status 必须为 ok。")
    generated_problem_id = str(generation_artifact.get("problem_id", "")).strip()
    if not generated_problem_id:
        raise ManifestError("生成 artifact 缺少 problem_id。")
    return generation_artifact, verification_artifact, source_counts, large_count, generated_problem, generated_problem_id


def _artifact_fields(
    *,
    generation_artifact: dict[str, Any],
    generated_problem: dict[str, Any],
    generated_problem_id: str,
    source_problem_id: str,
    source: str,
    generation_path: Path,
    verification_path: Path,
    source_counts: Counter[str],
    large_count: int,
) -> dict[str, Any]:
    changed_axes = generation_artifact.get("changed_axes_realized", [])
    if not isinstance(changed_axes, list):
        changed_axes = []
    source_ids = generation_artifact.get("source_problem_ids", [source_problem_id])
    if not isinstance(source_ids, list):
        source_ids = [source_problem_id]
    applied_rule = generation_artifact.get("applied_rule", "")
    if isinstance(applied_rule, dict):
        applied_rule = applied_rule.get("id") or applied_rule.get("name") or str(applied_rule)

    return {
        "problem_id": generated_problem_id,
        "problem_kind": "generated",
        "pair_id": source_problem_id,
        "source_problem_ids": [str(item) for item in source_ids],
        "source": source,
        "title": str(generated_problem.get("title", "")),
        "applied_rule": str(applied_rule),
        "changed_axes": [str(item) for item in changed_axes],
        "algorithm_tags": [],
        "generation_artifact_path": str(generation_path.resolve()),
        "generation_artifact_sha256": sha256_file(generation_path),
        "verification_artifact_path": str(verification_path.resolve()),
        "verification_artifact_sha256": sha256_file(verification_path),
        "test_case_counts": {
            **{source_name: source_counts[source_name] for source_name in REQUIRED_SOURCES},
            "large_scale": large_count,
        },
        "artifact_mtime_ns": max(generation_path.stat().st_mtime_ns, verification_path.stat().st_mtime_ns),
    }


def _candidate_from_problem(
    problem: dict[str, Any], summary_path: Path, excluded: list[dict[str, Any]]
) -> dict[str, Any] | None:
    source_problem_id = str(problem.get("problem_id", ""))
    if problem.get("status") != "verified":
        _exclude(
            excluded,
            workflow_summary=summary_path,
            source_problem_id=source_problem_id,
            reason="workflow_not_verified",
            details=str(problem.get("status", "")),
        )
        return None

    generation = problem.get("generation")
    if not isinstance(generation, dict):
        _exclude(
            excluded,
            workflow_summary=summary_path,
            source_problem_id=source_problem_id,
            reason="missing_generation_record",
        )
        return None
    generation_path = _resolve_path(generation.get("artifact_path"), base_dir=summary_path.parent)
    verification_path = _resolve_path(generation.get("verification_result_path"), base_dir=summary_path.parent)
    input_path = _resolve_path(problem.get("input_path"), base_dir=summary_path.parent)
    missing_paths = [
        name
        for name, path in (
            ("generation_artifact", generation_path),
            ("verification_artifact", verification_path),
        )
        if path is None or not path.is_file()
    ]
    if missing_paths:
        _exclude(
            excluded,
            workflow_summary=summary_path,
            source_problem_id=source_problem_id,
            reason="missing_artifact_file",
            details=", ".join(missing_paths),
        )
        return None

    try:
        generation_artifact, _, source_counts, large_count, generated_problem, generated_problem_id = (
            _load_validated_artifacts(generation_path, verification_path)
        )
    except (OSError, ValueError, TypeError, ManifestError) as exc:
        _exclude(
            excluded,
            workflow_summary=summary_path,
            source_problem_id=source_problem_id,
            reason="invalid_artifact_contract",
            details=str(exc),
        )
        return None

    source = ""
    if input_path is not None and input_path.is_file():
        try:
            original = read_json(input_path)
            if isinstance(original, dict):
                source = str(original.get("source", ""))
        except (OSError, ValueError):
            source = ""

    candidate = _artifact_fields(
        generation_artifact=generation_artifact,
        generated_problem=generated_problem,
        generated_problem_id=generated_problem_id,
        source_problem_id=source_problem_id,
        source=source,
        generation_path=generation_path,
        verification_path=verification_path,
        source_counts=source_counts,
        large_count=large_count,
    )
    candidate.update(
        {
            "workflow_summary_path": str(summary_path.resolve()),
            "source_input_path": str(input_path.resolve()) if input_path is not None else "",
        }
    )
    return candidate


def _read_export_source(successful_dir: Path) -> tuple[str, Path | None]:
    for folder in ("original_input", "source"):
        for path in sorted((successful_dir / folder).glob("*.json")):
            try:
                payload = read_json(path)
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict):
                return str(payload.get("source", "")), path
    return "", None


def _candidate_from_successful_dir(
    successful_dir: Path, excluded: list[dict[str, Any]]
) -> dict[str, Any] | None:
    metadata_path = successful_dir / "metadata" / "problem_record.json"
    source_problem_id = successful_dir.name
    if not metadata_path.is_file():
        _exclude_successful(
            excluded,
            successful_dir=successful_dir,
            metadata_path=metadata_path,
            source_problem_id=source_problem_id,
            reason="missing_metadata",
        )
        return None

    try:
        metadata = read_json(metadata_path)
    except (OSError, ValueError) as exc:
        _exclude_successful(
            excluded,
            successful_dir=successful_dir,
            metadata_path=metadata_path,
            source_problem_id=source_problem_id,
            reason="invalid_metadata",
            details=str(exc),
        )
        return None
    if not isinstance(metadata, dict):
        _exclude_successful(
            excluded,
            successful_dir=successful_dir,
            metadata_path=metadata_path,
            source_problem_id=source_problem_id,
            reason="invalid_metadata",
            details="metadata 顶层必须是对象。",
        )
        return None

    problem = metadata.get("problem")
    if not isinstance(problem, dict):
        _exclude_successful(
            excluded,
            successful_dir=successful_dir,
            metadata_path=metadata_path,
            source_problem_id=source_problem_id,
            reason="invalid_metadata",
            details="缺少 problem 对象。",
        )
        return None
    source_problem_id = str(problem.get("problem_id") or source_problem_id)
    if problem.get("status") != "verified":
        _exclude_successful(
            excluded,
            successful_dir=successful_dir,
            metadata_path=metadata_path,
            source_problem_id=source_problem_id,
            reason="workflow_not_verified",
            details=str(problem.get("status", "")),
        )
        return None

    generation = problem.get("generation")
    if not isinstance(generation, dict):
        _exclude_successful(
            excluded,
            successful_dir=successful_dir,
            metadata_path=metadata_path,
            source_problem_id=source_problem_id,
            reason="missing_generation_record",
        )
        return None

    generation_path = _copied_export_path(successful_dir, "artifacts", generation.get("artifact_path"))
    verification_path = _copied_export_path(
        successful_dir, "verification", generation.get("verification_result_path")
    )
    missing_paths = [
        name
        for name, path in (
            ("generation_artifact", generation_path),
            ("verification_artifact", verification_path),
        )
        if path is None or not path.is_file()
    ]
    if missing_paths:
        _exclude_successful(
            excluded,
            successful_dir=successful_dir,
            metadata_path=metadata_path,
            source_problem_id=source_problem_id,
            reason="missing_artifact_file",
            details=", ".join(missing_paths),
        )
        return None

    try:
        generation_artifact, _, source_counts, large_count, generated_problem, generated_problem_id = (
            _load_validated_artifacts(generation_path, verification_path)
        )
    except (OSError, ValueError, TypeError, ManifestError) as exc:
        _exclude_successful(
            excluded,
            successful_dir=successful_dir,
            metadata_path=metadata_path,
            source_problem_id=source_problem_id,
            reason="invalid_artifact_contract",
            details=str(exc),
        )
        return None

    source, source_path = _read_export_source(successful_dir)
    candidate = _artifact_fields(
        generation_artifact=generation_artifact,
        generated_problem=generated_problem,
        generated_problem_id=generated_problem_id,
        source_problem_id=source_problem_id,
        source=source,
        generation_path=generation_path,
        verification_path=verification_path,
        source_counts=source_counts,
        large_count=large_count,
    )
    candidate.update(
        {
            "artifact_problem_id": generated_problem_id,
            "workflow_summary_path": str(metadata.get("source_summary_path", "")),
            "source_input_path": str(source_path.resolve()) if source_path is not None else "",
            "successful_dir": str(successful_dir.resolve()),
            "metadata_path": str(metadata_path.resolve()),
        }
    )
    return candidate


def _is_successful_output_root(workflow_output_root: Path) -> bool:
    try:
        return any(
            (child / "metadata" / "problem_record.json").is_file()
            for child in workflow_output_root.iterdir()
            if child.is_dir()
        )
    except OSError:
        return False


def _finalize_successful_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifact_id_counts = Counter(
        str(candidate.get("artifact_problem_id") or candidate["problem_id"]) for candidate in candidates
    )
    used_ids: set[str] = set()
    problems = []
    for candidate in sorted(candidates, key=lambda item: (item["pair_id"], item["generation_artifact_path"])):
        candidate = dict(candidate)
        artifact_problem_id = str(candidate.get("artifact_problem_id") or candidate["problem_id"])
        if artifact_id_counts[artifact_problem_id] > 1:
            candidate["problem_id"] = f"{artifact_problem_id}__{candidate['pair_id']}"
        if candidate["problem_id"] in used_ids:
            # 极端情况下同一源题也出现重复导出，用稳定序号保证 manifest ID 不冲突。
            base_problem_id = str(candidate["problem_id"])
            duplicate_index = 2
            while candidate["problem_id"] in used_ids:
                candidate["problem_id"] = f"{base_problem_id}__dup{duplicate_index}"
                duplicate_index += 1
        used_ids.add(str(candidate["problem_id"]))
        candidate.pop("artifact_mtime_ns", None)
        problems.append(candidate)
    return sorted(problems, key=lambda item: item["problem_id"])


def build_manifest(workflow_output_root: Path, output_path: Path) -> dict[str, Any]:
    workflow_output_root = workflow_output_root.resolve()
    excluded: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    if _is_successful_output_root(workflow_output_root):
        for successful_dir in sorted(path for path in workflow_output_root.iterdir() if path.is_dir()):
            candidate = _candidate_from_successful_dir(successful_dir, excluded)
            if candidate is not None:
                candidates.append(candidate)
        problems = _finalize_successful_candidates(candidates)
    else:
        summary_paths = sorted(workflow_output_root.rglob("workflow_summary.json"))
        for summary_path in summary_paths:
            try:
                summary = read_json(summary_path)
            except (OSError, ValueError) as exc:
                _exclude(
                    excluded,
                    workflow_summary=summary_path,
                    source_problem_id="",
                    reason="invalid_workflow_summary",
                    details=str(exc),
                )
                continue
            problems_payload = summary.get("problems") if isinstance(summary, dict) else None
            if not isinstance(problems_payload, list):
                _exclude(
                    excluded,
                    workflow_summary=summary_path,
                    source_problem_id="",
                    reason="invalid_workflow_summary",
                    details="缺少 problems 数组。",
                )
                continue
            for problem in problems_payload:
                if not isinstance(problem, dict):
                    continue
                candidate = _candidate_from_problem(problem, summary_path, excluded)
                if candidate is not None:
                    candidates.append(candidate)

        # 同一道生成题可能因断点续跑出现在多个 run 中。只冻结最新的有效产物，并明确记录其余版本。
        selected: dict[str, dict[str, Any]] = {}
        for candidate in sorted(
            candidates,
            key=lambda item: (int(item["artifact_mtime_ns"]), item["verification_artifact_path"]),
        ):
            previous = selected.get(candidate["problem_id"])
            if previous is not None:
                excluded.append(
                    {
                        "workflow_summary": previous["workflow_summary_path"],
                        "source_problem_id": previous["pair_id"],
                        "reason": "superseded_duplicate",
                        "details": f"同 problem_id 已选择更新产物: {candidate['verification_artifact_path']}",
                    }
                )
            selected[candidate["problem_id"]] = candidate

        problems = []
        for candidate in sorted(selected.values(), key=lambda item: item["problem_id"]):
            candidate = dict(candidate)
            candidate.pop("artifact_mtime_ns", None)
            problems.append(candidate)

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "workflow_output_root": str(workflow_output_root),
        "problem_count": len(problems),
        "problems": problems,
    }
    manifest["content_fingerprint"] = stable_hash(
        {"schema_version": MANIFEST_SCHEMA_VERSION, "problems": problems}
    )
    atomic_write_json(output_path, manifest)
    exclusion_path = output_path.with_name(f"{output_path.stem}_excluded.json")
    atomic_write_json(
        exclusion_path,
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "created_at": manifest["created_at"],
            "excluded_count": len(excluded),
            "excluded": excluded,
        },
    )
    return {"manifest": manifest, "exclusion_path": str(exclusion_path), "excluded_count": len(excluded)}


def load_and_validate_manifest(path: Path) -> tuple[dict[str, Any], str]:
    path = path.resolve()
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestError("不支持的 manifest schema_version。")
    problems = payload.get("problems")
    if not isinstance(problems, list) or not problems:
        raise ManifestError("manifest 不包含可评测题目。")
    ids: set[str] = set()
    for problem in problems:
        if not isinstance(problem, dict):
            raise ManifestError("manifest.problems 中存在非对象元素。")
        problem_id = str(problem.get("problem_id", ""))
        if not problem_id or problem_id in ids:
            raise ManifestError(f"manifest problem_id 缺失或重复: {problem_id}")
        ids.add(problem_id)
        for prefix in ("generation_artifact", "verification_artifact"):
            artifact_path = Path(str(problem.get(f"{prefix}_path", "")))
            expected = str(problem.get(f"{prefix}_sha256", ""))
            if not artifact_path.is_file():
                raise ManifestError(f"冻结产物不存在: {artifact_path}")
            actual = sha256_file(artifact_path)
            if actual != expected:
                raise ManifestError(f"冻结产物 hash 已变化: {artifact_path}")
    return payload, sha256_file(path)
