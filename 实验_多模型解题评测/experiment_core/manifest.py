from __future__ import annotations

from collections import Counter
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .utils import atomic_write_json, read_json, stable_hash, utc_now_iso


MANIFEST_SCHEMA_VERSION = 2
SUPPORTED_MANIFEST_SCHEMA_VERSIONS = {1, MANIFEST_SCHEMA_VERSION}
REQUIRED_SOURCES = ("random", "adversarial", "small_challenge")
STREAMING_VERIFICATION_THRESHOLD_BYTES = 64 * 1024 * 1024


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


class _JsonStreamScanner:
    """面向超大 JSON 的轻量扫描器，只解析 manifest 需要的字段。"""

    def __init__(self, path: Path, *, chunk_size: int = 1024 * 1024) -> None:
        self._handle = path.open("r", encoding="utf-8")
        self._chunk_size = chunk_size
        self._buffer = ""
        self._pos = 0
        self._eof = False

    def close(self) -> None:
        self._handle.close()

    def _fill(self, min_chars: int = 1) -> bool:
        while not self._eof and len(self._buffer) - self._pos < min_chars:
            if self._pos:
                self._buffer = self._buffer[self._pos :]
                self._pos = 0
            chunk = self._handle.read(self._chunk_size)
            if chunk:
                self._buffer += chunk
            else:
                self._eof = True
        return len(self._buffer) - self._pos >= min_chars

    def _peek(self) -> str:
        if not self._fill():
            raise ValueError("JSON 意外结束。")
        return self._buffer[self._pos]

    def _read_char(self) -> str:
        char = self._peek()
        self._pos += 1
        return char

    def skip_ws(self) -> None:
        while True:
            if not self._fill():
                return
            while self._pos < len(self._buffer) and self._buffer[self._pos] in " \t\r\n":
                self._pos += 1
            if self._pos < len(self._buffer):
                return

    def expect(self, expected: str) -> None:
        self.skip_ws()
        actual = self._read_char()
        if actual != expected:
            raise ValueError(f"JSON 结构非法，期望 {expected!r}，实际 {actual!r}。")

    def consume_if(self, char: str) -> bool:
        self.skip_ws()
        if self._peek() == char:
            self._pos += 1
            return True
        return False

    def next_is_string(self) -> bool:
        self.skip_ws()
        return self._peek() == '"'

    def next_is_object(self) -> bool:
        self.skip_ws()
        return self._peek() == "{"

    def read_string(self, *, max_capture: int | None = None) -> str | None:
        self.skip_ws()
        if self._read_char() != '"':
            raise ValueError("JSON 字符串缺少起始引号。")
        captured: list[str] = []
        captured_len = 0
        too_long = False

        def capture(segment: str) -> None:
            nonlocal captured_len, too_long
            if max_capture == 0 or too_long:
                return
            if max_capture is not None and captured_len + len(segment) > max_capture:
                captured.append(segment[: max_capture - captured_len])
                captured_len = max_capture
                too_long = True
                return
            captured.append(segment)
            captured_len += len(segment)

        while True:
            if not self._fill():
                raise ValueError("JSON 字符串未闭合。")
            quote_at = self._buffer.find('"', self._pos)
            slash_at = self._buffer.find("\\", self._pos)
            candidates = [index for index in (quote_at, slash_at) if index >= 0]
            if not candidates:
                capture(self._buffer[self._pos :])
                self._pos = len(self._buffer)
                continue

            next_at = min(candidates)
            capture(self._buffer[self._pos : next_at])
            self._pos = next_at
            char = self._buffer[self._pos]
            if char == '"':
                self._pos += 1
                if max_capture == 0 or too_long:
                    return None
                return json.loads(f'"{"".join(captured)}"')

            self._pos += 1
            if not self._fill():
                raise ValueError("JSON 转义序列未闭合。")
            capture("\\" + self._buffer[self._pos])
            self._pos += 1

    def read_number_text(self) -> str:
        self.skip_ws()
        chars: list[str] = []
        while self._fill() and self._buffer[self._pos] in "-+0123456789.eE":
            chars.append(self._buffer[self._pos])
            self._pos += 1
        if not chars:
            raise ValueError("JSON 数字缺失。")
        return "".join(chars)

    def read_bool_or_skip(self) -> bool | None:
        self.skip_ws()
        char = self._peek()
        if char == "t":
            self._read_literal("true")
            return True
        if char == "f":
            self._read_literal("false")
            return False
        self.skip_value()
        return None

    def read_number_like(self) -> str | None:
        self.skip_ws()
        char = self._peek()
        if char == '"':
            return self.read_string(max_capture=128)
        if char in "-0123456789":
            return self.read_number_text()
        self.skip_value()
        return None

    def _read_literal(self, literal: str) -> None:
        for expected in literal:
            actual = self._read_char()
            if actual != expected:
                raise ValueError(f"JSON 字面量非法，期望 {literal!r}。")

    def skip_value(self) -> None:
        self.skip_ws()
        char = self._peek()
        if char == "{":
            self._skip_object()
        elif char == "[":
            self._skip_array()
        elif char == '"':
            self.read_string(max_capture=0)
        elif char in "-0123456789":
            self.read_number_text()
        elif char == "t":
            self._read_literal("true")
        elif char == "f":
            self._read_literal("false")
        elif char == "n":
            self._read_literal("null")
        else:
            raise ValueError(f"JSON 值起始字符非法: {char!r}。")

    def _skip_object(self) -> None:
        self.expect("{")
        if self.consume_if("}"):
            return
        while True:
            self.read_string(max_capture=0)
            self.expect(":")
            self.skip_value()
            if self.consume_if("}"):
                return
            self.expect(",")

    def _skip_array(self) -> None:
        self.expect("[")
        if self.consume_if("]"):
            return
        while True:
            self.skip_value()
            if self.consume_if("]"):
                return
            self.expect(",")


def _parse_case_object(scanner: _JsonStreamScanner) -> tuple[str, bool, bool]:
    source = ""
    has_input = False
    has_output = False
    scanner.expect("{")
    if scanner.consume_if("}"):
        return source, has_input, has_output
    while True:
        key = scanner.read_string()
        scanner.expect(":")
        if key == "source":
            if scanner.next_is_string():
                source = scanner.read_string(max_capture=256) or ""
            else:
                scanner.skip_value()
        elif key == "input":
            if scanner.next_is_string():
                scanner.read_string(max_capture=0)
                has_input = True
            else:
                scanner.skip_value()
        elif key == "output":
            if scanner.next_is_string():
                scanner.read_string(max_capture=0)
                has_output = True
            else:
                scanner.skip_value()
        else:
            scanner.skip_value()
        if scanner.consume_if("}"):
            return source, has_input, has_output
        scanner.expect(",")


def _parse_solved_cases(scanner: _JsonStreamScanner) -> Counter[str]:
    source_counts: Counter[str] = Counter()
    total = 0
    scanner.expect("[")
    if scanner.consume_if("]"):
        raise ManifestError("缺少 bruteforce_verification.solved_cases。")
    while True:
        if not scanner.next_is_object():
            scanner.skip_value()
            raise ManifestError("solved_cases 中存在非对象元素。")
        source, has_input, has_output = _parse_case_object(scanner)
        if not has_input or not has_output:
            raise ManifestError("solved_cases 中存在缺少字符串 input/output 的用例。")
        if source in REQUIRED_SOURCES:
            source_counts[source] += 1
        total += 1
        if scanner.consume_if("]"):
            break
        scanner.expect(",")
    if total <= 0:
        raise ManifestError("缺少 bruteforce_verification.solved_cases。")
    return source_counts


def _parse_large_cases(scanner: _JsonStreamScanner) -> int:
    total = 0
    scanner.expect("[")
    if scanner.consume_if("]"):
        return total
    while True:
        if not scanner.next_is_object():
            scanner.skip_value()
            raise ManifestError("大规模真值中存在非法 input/output。")
        _, has_input, has_output = _parse_case_object(scanner)
        if not has_input or not has_output:
            raise ManifestError("大规模真值中存在非法 input/output。")
        total += 1
        if scanner.consume_if("]"):
            return total
        scanner.expect(",")


def _parse_bruteforce_summary(scanner: _JsonStreamScanner) -> Counter[str]:
    solved_counts: Counter[str] | None = None
    scanner.expect("{")
    if scanner.consume_if("}"):
        raise ManifestError("缺少 bruteforce_verification.solved_cases。")
    while True:
        key = scanner.read_string()
        scanner.expect(":")
        if key == "solved_cases":
            solved_counts = _parse_solved_cases(scanner)
        else:
            scanner.skip_value()
        if scanner.consume_if("}"):
            break
        scanner.expect(",")
    if solved_counts is None:
        raise ManifestError("缺少 bruteforce_verification.solved_cases。")
    return solved_counts


def _parse_large_summary(scanner: _JsonStreamScanner) -> int:
    status = ""
    failure_count = 0
    large_count: int | None = None
    scanner.expect("{")
    if scanner.consume_if("}"):
        raise ManifestError("large_scale_truth_outputs.status 必须为 ok。")
    while True:
        key = scanner.read_string()
        scanner.expect(":")
        if key == "status" and scanner.next_is_string():
            status = scanner.read_string(max_capture=128) or ""
        elif key == "failure_count":
            raw_failure_count = scanner.read_number_like()
            try:
                failure_count = int(raw_failure_count or 0)
            except ValueError as exc:
                raise ManifestError("大规模真值生成存在失败用例。") from exc
        elif key == "cases":
            large_count = _parse_large_cases(scanner)
        else:
            scanner.skip_value()
        if scanner.consume_if("}"):
            break
        scanner.expect(",")
    if status != "ok":
        raise ManifestError("large_scale_truth_outputs.status 必须为 ok。")
    if large_count is None or large_count <= 0:
        raise ManifestError("缺少大规模真值用例。")
    if failure_count != 0:
        raise ManifestError("大规模真值生成存在失败用例。")
    return large_count


def _parse_checker_summary(scanner: _JsonStreamScanner) -> None:
    needs_checker = False
    has_checker_code = False
    scanner.expect("{")
    if scanner.consume_if("}"):
        return
    while True:
        key = scanner.read_string()
        scanner.expect(":")
        if key == "needs_checker":
            needs_checker = scanner.read_bool_or_skip() is True
        elif key in {"verified_checker_code", "checker_code"} and scanner.next_is_string():
            checker_code = scanner.read_string(max_capture=4096) or ""
            has_checker_code = has_checker_code or bool(checker_code.strip())
        else:
            scanner.skip_value()
        if scanner.consume_if("}"):
            break
        scanner.expect(",")
    if needs_checker and not has_checker_code:
        raise ManifestError("题目要求 checker，但验证产物缺少已验证 checker 代码。")


def _parse_standard_solution_summary(scanner: _JsonStreamScanner) -> None:
    limits_seen = False
    timeout_seconds = 0.0
    memory_limit_mb = 0
    scanner.expect("{")
    if scanner.consume_if("}"):
        raise ManifestError("缺少标准解执行限制。")
    while True:
        key = scanner.read_string()
        scanner.expect(":")
        if key == "standard_solution_limits":
            limits_seen = True
            timeout_seconds, memory_limit_mb = _parse_standard_solution_limits(scanner)
        else:
            scanner.skip_value()
        if scanner.consume_if("}"):
            break
        scanner.expect(",")
    if not limits_seen or timeout_seconds <= 0 or memory_limit_mb <= 0:
        raise ManifestError("标准解执行限制必须为正数。")


def _parse_standard_solution_limits(scanner: _JsonStreamScanner) -> tuple[float, int]:
    timeout_seconds = 0.0
    memory_limit_mb = 0
    scanner.expect("{")
    if scanner.consume_if("}"):
        return timeout_seconds, memory_limit_mb
    while True:
        key = scanner.read_string()
        scanner.expect(":")
        if key == "timeout_seconds":
            raw_timeout = scanner.read_number_like()
            try:
                timeout_seconds = float(raw_timeout or 0)
            except ValueError:
                timeout_seconds = 0.0
        elif key == "memory_limit_mb":
            raw_memory = scanner.read_number_like()
            try:
                memory_limit_mb = int(raw_memory or 0)
            except ValueError:
                memory_limit_mb = 0
        else:
            scanner.skip_value()
        if scanner.consume_if("}"):
            return timeout_seconds, memory_limit_mb
        scanner.expect(",")


def _validate_verification_artifact_streaming(path: Path) -> tuple[Counter[str], int]:
    scanner = _JsonStreamScanner(path)
    try:
        source_counts: Counter[str] | None = None
        large_count: int | None = None
        checker_seen = False
        limits_seen = False

        scanner.expect("{")
        if scanner.consume_if("}"):
            raise ManifestError("artifact 顶层必须是对象。")
        while True:
            key = scanner.read_string()
            scanner.expect(":")
            if key == "bruteforce_verification":
                source_counts = _parse_bruteforce_summary(scanner)
            elif key == "large_scale_truth_outputs":
                large_count = _parse_large_summary(scanner)
            elif key == "checker":
                checker_seen = True
                _parse_checker_summary(scanner)
            elif key == "standard_solution_verification":
                limits_seen = True
                _parse_standard_solution_summary(scanner)
            else:
                scanner.skip_value()
            if scanner.consume_if("}"):
                break
            scanner.expect(",")

        if source_counts is None:
            raise ManifestError("缺少 bruteforce_verification.solved_cases。")
        missing = [source for source in REQUIRED_SOURCES if source_counts[source] <= 0]
        if missing:
            raise ManifestError("缺少测试类别: " + ", ".join(missing))
        if large_count is None:
            raise ManifestError("large_scale_truth_outputs.status 必须为 ok。")
        if not limits_seen:
            raise ManifestError("缺少标准解执行限制。")
        if not checker_seen:
            # checker 字段缺失时沿用旧逻辑：只有显式 needs_checker=true 才要求代码。
            pass
        return source_counts, large_count
    finally:
        scanner.close()


def _load_verification_summary(path: Path) -> tuple[dict[str, Any], Counter[str], int]:
    if path.stat().st_size <= STREAMING_VERIFICATION_THRESHOLD_BYTES:
        verification_artifact = read_json(path)
        if not isinstance(verification_artifact, dict):
            raise ManifestError("artifact 顶层必须是对象。")
        source_counts, large_count = _validate_verification_artifact(verification_artifact)
        return verification_artifact, source_counts, large_count

    source_counts, large_count = _validate_verification_artifact_streaming(path)
    return {}, source_counts, large_count


def _load_validated_artifacts(
    generation_path: Path, verification_path: Path
) -> tuple[dict[str, Any], dict[str, Any], Counter[str], int, dict[str, Any], str]:
    generation_artifact, generated_problem, generated_problem_id = _load_generation_artifact(generation_path)
    verification_artifact, source_counts, large_count = _load_verification_summary(verification_path)
    return generation_artifact, verification_artifact, source_counts, large_count, generated_problem, generated_problem_id


def _load_generation_artifact(generation_path: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    generation_artifact = read_json(generation_path)
    if not isinstance(generation_artifact, dict):
        raise ManifestError("artifact 顶层必须是对象。")
    generated_problem = generation_artifact.get("generated_problem")
    if not isinstance(generated_problem, dict) or generated_problem.get("status") != "ok":
        raise ManifestError("generated_problem.status 必须为 ok。")
    generated_problem_id = str(generation_artifact.get("problem_id", "")).strip()
    if not generated_problem_id:
        raise ManifestError("生成 artifact 缺少 problem_id。")
    return generation_artifact, generated_problem, generated_problem_id


def _artifact_fields(
    *,
    generation_artifact: dict[str, Any],
    generated_problem: dict[str, Any],
    generated_problem_id: str,
    source_problem_id: str,
    source: str,
    generation_path: Path,
    verification_path: Path,
    source_counts: Counter[str] | None = None,
    large_count: int | None = None,
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

    fields: dict[str, Any] = {
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
        "verification_artifact_path": str(verification_path.resolve()),
        "artifact_mtime_ns": max(generation_path.stat().st_mtime_ns, verification_path.stat().st_mtime_ns),
    }
    if source_counts is not None and large_count is not None:
        fields["test_case_counts"] = {
            **{source_name: source_counts[source_name] for source_name in REQUIRED_SOURCES},
            "large_scale": large_count,
        }
    return fields


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


def _lightweight_candidate_from_successful_dir(
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
        generation_artifact, generated_problem, generated_problem_id = _load_generation_artifact(generation_path)
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
    )
    candidate.update(
        {
            "artifact_problem_id": generated_problem_id,
            "workflow_summary_path": str(metadata.get("source_summary_path", "")),
            "source_input_path": str(source_path.resolve()) if source_path is not None else "",
            "successful_dir": str(successful_dir.resolve()),
            "metadata_path": str(metadata_path.resolve()),
            "generation_artifact_size": generation_path.stat().st_size,
            "generation_artifact_mtime_ns": generation_path.stat().st_mtime_ns,
            "verification_artifact_size": verification_path.stat().st_size,
            "verification_artifact_mtime_ns": verification_path.stat().st_mtime_ns,
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


def load_successful_output_problem_set(workflow_output_root: Path) -> tuple[dict[str, Any], str]:
    workflow_output_root = workflow_output_root.resolve()
    if not _is_successful_output_root(workflow_output_root):
        raise ManifestError("workflow_output_root 不是 successful_output 导出目录。")

    excluded: list[dict[str, Any]] = []
    candidates = []
    for successful_dir in sorted(path for path in workflow_output_root.iterdir() if path.is_dir()):
        candidate = _lightweight_candidate_from_successful_dir(successful_dir, excluded)
        if candidate is not None:
            candidates.append(candidate)
    problems = _finalize_successful_candidates(candidates)
    if not problems:
        raise ManifestError("successful_output 不包含可评测题目。")

    problem_set = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "problem_source_type": "successful_output",
        "workflow_output_root": str(workflow_output_root),
        "problem_count": len(problems),
        "excluded_count": len(excluded),
        "problems": problems,
    }
    problem_set["content_fingerprint"] = stable_hash(
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "problem_source_type": "successful_output",
            "workflow_output_root": str(workflow_output_root),
            "problems": problems,
        }
    )
    return problem_set, problem_set["content_fingerprint"]


def load_and_validate_manifest(path: Path) -> tuple[dict[str, Any], str]:
    path = path.resolve()
    payload = read_json(path)
    schema_version = payload.get("schema_version") if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or schema_version not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
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
            if not artifact_path.is_file():
                raise ManifestError(f"冻结产物不存在: {artifact_path}")
    return payload, stable_hash({"schema_version": schema_version, "problems": problems})
