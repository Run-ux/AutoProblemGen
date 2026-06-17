from __future__ import annotations

import itertools
from typing import Any

from .config import VERIFICATION_DIR

import sys

if str(VERIFICATION_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFICATION_DIR))

from local_execution import EXECUTION_MEMORY_LIMIT, EXECUTION_OK, EXECUTION_TIMEOUT  # noqa: E402
from local_execution import run_generate_test_input, run_solution, run_validate_test_input  # noqa: E402


BASELINE_SOURCES = {"random", "adversarial", "small_challenge"}
TARGETED_SOURCE = "wrong_pool_targeted"


def _case_payload(case: dict[str, Any], *, source_override: str | None = None) -> dict[str, Any]:
    return {
        "case_id": str(case["case_id"]),
        "source": source_override or str(case.get("source", "")),
        "input": str(case["input"]),
        "output": str(case["output"]),
    }


def baseline_cases(verification: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for case in verification.get("bruteforce_verification", {}).get("solved_cases", []):
        if str(case.get("source", "")) in BASELINE_SOURCES:
            cases.append(_case_payload(case))
    for case in verification.get("large_scale_truth_outputs", {}).get("cases", []):
        if str(case.get("source", "")) in BASELINE_SOURCES:
            cases.append(_case_payload(case, source_override=f"large_scale:{case.get('source', '')}"))
    return cases


def ours_cases(verification: dict[str, Any]) -> list[dict[str, Any]]:
    cases = baseline_cases(verification)
    for case in verification.get("bruteforce_verification", {}).get("solved_cases", []):
        if str(case.get("source", "")) == TARGETED_SOURCE:
            cases.append(_case_payload(case))
    return cases


def collect_size_control_cases(
    verification: dict[str, Any],
    *,
    target_total_count: int,
    execution_config: Any,
    max_attempt_multiplier: int = 12,
) -> list[dict[str, Any]]:
    cases = baseline_cases(verification)
    needed = max(0, target_total_count - len(cases))
    if needed <= 0:
        return cases

    seen_inputs = {case["input"] for case in cases}
    generated = verification["test_inputs"]
    brute_code = verification["bruteforce_solution"]["verified_code"]
    standard_code = verification["standard_solution"]["verified_code"]
    standard_limits = verification["standard_solution_verification"]["standard_solution_limits"]
    source_cycle = itertools.cycle(["random", "adversarial"])
    attempts = 0
    max_attempts = max(needed * max_attempt_multiplier, needed + 20)
    while len(cases) < target_total_count and attempts < max_attempts:
        attempts += 1
        source = next(source_cycle)
        payload = generated[source]
        generation = run_generate_test_input(
            payload["generate_test_input_code"],
            timeout_seconds=execution_config.test_input_timeout_seconds,
            memory_limit_mb=execution_config.test_input_memory_limit_mb,
        )
        if generation.status != EXECUTION_OK or not isinstance(generation.return_value, str):
            continue
        input_string = generation.return_value
        if not input_string.strip() or input_string in seen_inputs:
            continue
        validation = run_validate_test_input(
            payload["validate_test_input_code"],
            input_string,
            timeout_seconds=execution_config.test_input_timeout_seconds,
            memory_limit_mb=execution_config.test_input_memory_limit_mb,
        )
        if validation.status != EXECUTION_OK or validation.return_value is not True:
            continue

        solve_result = run_solution(
            brute_code,
            input_string,
            timeout_seconds=execution_config.bruteforce_timeout_seconds,
            memory_limit_mb=execution_config.bruteforce_memory_limit_mb,
        )
        output_source = "bruteforce"
        if solve_result.status in {EXECUTION_TIMEOUT, EXECUTION_MEMORY_LIMIT}:
            solve_result = run_solution(
                standard_code,
                input_string,
                timeout_seconds=float(standard_limits["timeout_seconds"]),
                memory_limit_mb=int(standard_limits["memory_limit_mb"]),
            )
            output_source = "standard_solution"
        if solve_result.status != EXECUTION_OK or not isinstance(solve_result.return_value, str):
            continue
        seen_inputs.add(input_string)
        index = len(cases) + 1
        cases.append(
            {
                "case_id": f"size_control_{index:03d}",
                "source": f"size_control_{source}:{output_source}",
                "input": input_string,
                "output": solve_result.return_value,
            }
        )
    return cases


def build_suites(
    verification: dict[str, Any],
    *,
    execution_config: Any,
) -> dict[str, list[dict[str, Any]]]:
    ours = ours_cases(verification)
    return {
        "unicode_style_baseline": baseline_cases(verification),
        "ours_pipeline": ours,
        "size_control": collect_size_control_cases(
            verification,
            target_total_count=len(ours),
            execution_config=execution_config,
        ),
    }
