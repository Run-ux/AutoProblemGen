from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Callable

try:  # 兼容包内导入与当前目录直接运行两种方式。
    from .execution_config import ExecutionConfig
    from .generation_pipeline import generate_all_artifacts
    from .llm_client import ChatLLMClient, OpenAIChatLLMClient
    from .llm_config import LLMConfig
    from .llm_contract import call_prompt_with_contract_retry
    from .llm_json import (
        validate_checker_repair_response,
        validate_code_repair_response,
        validate_counterexample_response,
        validate_small_challenge_response,
        validate_test_generator_response,
    )
    from .local_execution import (
        EXECUTION_MEMORY_LIMIT,
        EXECUTION_OK,
        EXECUTION_TIMEOUT,
        ExecutionResult,
        run_checker,
        run_generate_test_input,
        run_solution,
        run_validate_test_input,
    )
    from .prompts.tool_generation import prompt_small_challenge_test_input, prompt_wrong_solution_targeted_test_input
    from .prompts.verification import (
        prompt_bruteforce_debug,
        prompt_checker_counterexample,
        prompt_checker_false_accept_debug,
        prompt_checker_false_reject_debug,
        prompt_standard_solution_debug,
        prompt_test_input_debug,
    )
except ImportError:  # pragma: no cover - 当前测试以顶层模块方式导入。
    from execution_config import ExecutionConfig
    from generation_pipeline import generate_all_artifacts
    from llm_client import ChatLLMClient, OpenAIChatLLMClient
    from llm_config import LLMConfig
    from llm_contract import call_prompt_with_contract_retry
    from llm_json import (
        validate_checker_repair_response,
        validate_code_repair_response,
        validate_counterexample_response,
        validate_small_challenge_response,
        validate_test_generator_response,
    )
    from local_execution import (
        EXECUTION_MEMORY_LIMIT,
        EXECUTION_OK,
        EXECUTION_TIMEOUT,
        ExecutionResult,
        run_checker,
        run_generate_test_input,
        run_solution,
        run_validate_test_input,
    )
    from prompts.tool_generation import prompt_small_challenge_test_input, prompt_wrong_solution_targeted_test_input
    from prompts.verification import (
        prompt_bruteforce_debug,
        prompt_checker_counterexample,
        prompt_checker_false_accept_debug,
        prompt_checker_false_reject_debug,
        prompt_standard_solution_debug,
        prompt_test_input_debug,
    )


logger = logging.getLogger(__name__)

Validator = Callable[[dict[str, Any]], dict[str, Any]]

WRONG_POOL_STOP_KILL_RATIO = 0.8
TEST_INPUT_REPAIR_LIMIT = 2
TIME_LIMIT_LABEL_RE = re.compile(r"(时间限制|time\s*limit)", re.IGNORECASE)
MEMORY_LIMIT_LABEL_RE = re.compile(r"(空间限制|内存限制|memory\s*limit)", re.IGNORECASE)
TIME_LIMIT_VALUE_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|毫秒|milliseconds?|secs?|seconds?|s|秒)",
    re.IGNORECASE,
)
MEMORY_LIMIT_VALUE_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>kb|kib|mb|mib|gb|gib)",
    re.IGNORECASE,
)

DEFAULT_LLM_CASE_MAX_CHARS = 40_000
DEFAULT_LLM_CASE_INPUT_MAX_CHARS = 24_000
DEFAULT_LLM_CASE_OUTPUT_MAX_CHARS = 16_000
DEFAULT_LLM_CASE_TOTAL_CHARS = 160_000
DEFAULT_LLM_CASE_MAX_COUNT = 10
DEFAULT_MAX_LLM_PROMPT_CHARS = 600_000
DEFAULT_LLM_TRACE_MAX_TEXT_CHARS = 30_000


class VerificationError(RuntimeError):
    """表示生成后验证流水线无法安全继续。"""


@dataclass(frozen=True)
class LLMContextLimits:
    """验证阶段进入 LLM 上下文的文本预算。"""

    llm_case_max_chars: int = DEFAULT_LLM_CASE_MAX_CHARS
    llm_case_input_max_chars: int = DEFAULT_LLM_CASE_INPUT_MAX_CHARS
    llm_case_output_max_chars: int = DEFAULT_LLM_CASE_OUTPUT_MAX_CHARS
    llm_case_total_chars: int = DEFAULT_LLM_CASE_TOTAL_CHARS
    llm_case_max_count: int = DEFAULT_LLM_CASE_MAX_COUNT
    max_llm_prompt_chars: int = DEFAULT_MAX_LLM_PROMPT_CHARS
    llm_trace_max_text_chars: int = DEFAULT_LLM_TRACE_MAX_TEXT_CHARS

    @classmethod
    def from_object(cls, value: Any | None) -> "LLMContextLimits":
        if value is None:
            return cls()
        return cls(
            llm_case_max_chars=int(getattr(value, "llm_case_max_chars", DEFAULT_LLM_CASE_MAX_CHARS)),
            llm_case_input_max_chars=int(
                getattr(value, "llm_case_input_max_chars", DEFAULT_LLM_CASE_INPUT_MAX_CHARS)
            ),
            llm_case_output_max_chars=int(
                getattr(value, "llm_case_output_max_chars", DEFAULT_LLM_CASE_OUTPUT_MAX_CHARS)
            ),
            llm_case_total_chars=int(getattr(value, "llm_case_total_chars", DEFAULT_LLM_CASE_TOTAL_CHARS)),
            llm_case_max_count=int(getattr(value, "llm_case_max_count", DEFAULT_LLM_CASE_MAX_COUNT)),
            max_llm_prompt_chars=int(getattr(value, "max_llm_prompt_chars", DEFAULT_MAX_LLM_PROMPT_CHARS)),
            llm_trace_max_text_chars=int(
                getattr(value, "llm_trace_max_text_chars", DEFAULT_LLM_TRACE_MAX_TEXT_CHARS)
            ),
        )


def _emit_progress(message: str) -> None:
    print(message, flush=True)


def _emit_repair_progress(repair_name: str, repair_round: int, message: str) -> None:
    _emit_progress(f"[verification repair] {repair_name}：第 {repair_round} 轮{message}")


def _build_client(config: LLMConfig | None, client: ChatLLMClient | None) -> tuple[LLMConfig | None, ChatLLMClient]:
    if client is not None:
        return config, client
    if config is None:
        raise RuntimeError("LLMConfig 必须由总流程注入，子模块不再读取本地 .env。")
    resolved_config = config
    return resolved_config, OpenAIChatLLMClient(resolved_config)


def _call_prompt(
    client: ChatLLMClient,
    *,
    task_name: str,
    system_prompt: str,
    user_prompt: str,
    validator: Validator,
) -> dict[str, Any]:
    return call_prompt_with_contract_retry(
        client,
        task_name=task_name,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        validator=validator,
    )


def _truncate_middle(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    marker = "\n...<truncated>...\n"
    if limit <= len(marker):
        return value[:limit]
    keep_each_side = (limit - len(marker)) // 2
    return value[:keep_each_side] + marker + value[-keep_each_side:]


def _result_summary(result: ExecutionResult) -> dict[str, Any]:
    payload = result.to_dict()
    if payload.get("stdout") and len(payload["stdout"]) > 2000:
        payload["stdout"] = _truncate_middle(payload["stdout"], 2000)
    if payload.get("stderr") and len(payload["stderr"]) > 2000:
        payload["stderr"] = _truncate_middle(payload["stderr"], 2000)
    if payload.get("traceback") and len(payload["traceback"]) > 4000:
        payload["traceback"] = _truncate_middle(payload["traceback"], 4000)
    if payload.get("user_stdout") and len(payload["user_stdout"]) > 2000:
        payload["user_stdout"] = _truncate_middle(payload["user_stdout"], 2000)
    if payload.get("user_stderr") and len(payload["user_stderr"]) > 2000:
        payload["user_stderr"] = _truncate_middle(payload["user_stderr"], 2000)
    return payload


def _case_text_metadata(
    *,
    input_string: str,
    output_string: str = "",
    context_limits: LLMContextLimits,
) -> dict[str, Any]:
    input_chars = len(input_string)
    output_chars = len(output_string)
    total_io_chars = input_chars + output_chars
    reasons: list[str] = []
    if total_io_chars > context_limits.llm_case_max_chars:
        reasons.append("case_io_too_large")
    if input_chars > context_limits.llm_case_input_max_chars:
        reasons.append("case_input_too_large")
    if output_chars > context_limits.llm_case_output_max_chars:
        reasons.append("case_output_too_large")
    llm_eligible = not reasons
    return {
        "llm_eligible": llm_eligible,
        "stress_only": not llm_eligible,
        "input_chars": input_chars,
        "output_chars": output_chars,
        "total_io_chars": total_io_chars,
        "llm_exclusion_reason": ",".join(reasons),
    }


def _input_case_metadata(input_string: str, context_limits: LLMContextLimits) -> dict[str, Any]:
    return _case_text_metadata(input_string=input_string, context_limits=context_limits)


def _solved_case_payload(
    *,
    case: dict[str, Any],
    output: str,
    context_limits: LLMContextLimits,
) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "source": case["source"],
        "input": case["input"],
        "output": output,
        **_case_text_metadata(
            input_string=case["input"],
            output_string=output,
            context_limits=context_limits,
        ),
    }


def _select_llm_cases(
    solved_cases: list[dict[str, Any]],
    context_limits: LLMContextLimits,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    used_chars = 0
    for case in solved_cases:
        case_chars = int(case.get("total_io_chars", len(case.get("input", "")) + len(case.get("output", ""))))
        if not case.get("llm_eligible", True):
            skipped.append(_llm_case_skip_record(case, reason=str(case.get("llm_exclusion_reason") or "stress_only")))
            continue
        if len(selected) >= context_limits.llm_case_max_count:
            skipped.append(_llm_case_skip_record(case, reason="case_count_budget_exceeded"))
            continue
        if used_chars + case_chars > context_limits.llm_case_total_chars:
            skipped.append(_llm_case_skip_record(case, reason="case_total_budget_exceeded"))
            continue
        selected.append(case)
        used_chars += case_chars
    return selected, skipped


def _llm_case_skip_record(case: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id", ""),
        "source": case.get("source", ""),
        "reason": reason,
        "input_chars": len(str(case.get("input", ""))),
        "output_chars": len(str(case.get("output", ""))),
        "total_io_chars": len(str(case.get("input", ""))) + len(str(case.get("output", ""))),
    }


def _is_case_input_too_large(case: dict[str, Any], context_limits: LLMContextLimits) -> bool:
    return len(str(case.get("input", ""))) > context_limits.llm_case_input_max_chars


def _format_execution_report(result: ExecutionResult, *, expectation: str) -> str:
    return json.dumps(
        {
            "expectation": expectation,
            "execution_result": _result_summary(result),
        },
        ensure_ascii=False,
        indent=2,
    )


def _fail_execution(context: str, result: ExecutionResult) -> None:
    raise VerificationError(
        f"{context} 执行失败："
        + json.dumps(_result_summary(result), ensure_ascii=False, indent=2)
    )


def _ensure_string_result(context: str, result: ExecutionResult) -> str:
    if result.status != EXECUTION_OK:
        _fail_execution(context, result)
    if not isinstance(result.return_value, str) or not result.return_value.strip():
        raise VerificationError(f"{context} 必须返回非空字符串。实际返回：{result.return_value!r}")
    return result.return_value


def _ensure_true_result(context: str, result: ExecutionResult) -> None:
    if result.status != EXECUTION_OK:
        _fail_execution(context, result)
    if result.return_value is not True:
        raise VerificationError(f"{context} 校验未通过。实际返回：{result.return_value!r}")


def _constraint_texts(artifact: dict[str, Any]) -> list[str]:
    problem = artifact.get("generated_problem") if isinstance(artifact, dict) else None
    if not isinstance(problem, dict):
        raise VerificationError("artifact.generated_problem 必须是字典，无法解析标准解执行限制。")

    constraints = problem.get("constraints")
    if isinstance(constraints, str):
        return [item.strip() for item in constraints.splitlines() if item.strip()]
    if isinstance(constraints, list):
        return [str(item) for item in constraints]
    if isinstance(constraints, dict):
        return [f"{key}: {value}" for key, value in constraints.items()]
    raise VerificationError("generated_problem.constraints 必须是字符串、列表或字典，无法解析标准解执行限制。")


def _parse_limit_value_after_label(
    text: str,
    *,
    label_re: re.Pattern[str],
    value_re: re.Pattern[str],
    limit_name: str,
) -> re.Match[str] | None:
    label_match = label_re.search(text)
    if label_match is None:
        return None
    value_match = value_re.search(text[label_match.end() :])
    if value_match is None:
        raise VerificationError(f"constraints 中的{limit_name}缺少明确数值和单位：{text}")
    return value_match


def _time_limit_seconds(match: re.Match[str]) -> float:
    value = float(match.group("value"))
    unit = match.group("unit").lower()
    if value <= 0:
        raise VerificationError("标准解时间限制必须大于 0。")
    if unit in ("ms", "毫秒", "millisecond", "milliseconds"):
        return value / 1000
    return value


def _memory_limit_mb(match: re.Match[str]) -> int:
    value = float(match.group("value"))
    unit = match.group("unit").lower()
    if value <= 0:
        raise VerificationError("标准解空间限制必须大于 0。")
    if unit in ("kb", "kib"):
        return max(1, math.ceil(value / 1024))
    if unit in ("gb", "gib"):
        return math.ceil(value * 1024)
    return math.ceil(value)


def _parse_standard_solution_limits(artifact: dict[str, Any]) -> dict[str, Any]:
    """从题面 constraints 中解析标准解运行限制，避免用测试配置替代题面限制。"""

    time_limit: float | None = None
    memory_limit: int | None = None
    raw_time_limit = ""
    raw_memory_limit = ""

    for text in _constraint_texts(artifact):
        if time_limit is None:
            time_match = _parse_limit_value_after_label(
                text,
                label_re=TIME_LIMIT_LABEL_RE,
                value_re=TIME_LIMIT_VALUE_RE,
                limit_name="时间限制",
            )
            if time_match is not None:
                time_limit = _time_limit_seconds(time_match)
                raw_time_limit = text
        if memory_limit is None:
            memory_match = _parse_limit_value_after_label(
                text,
                label_re=MEMORY_LIMIT_LABEL_RE,
                value_re=MEMORY_LIMIT_VALUE_RE,
                limit_name="空间限制",
            )
            if memory_match is not None:
                memory_limit = _memory_limit_mb(memory_match)
                raw_memory_limit = text

    missing = []
    if time_limit is None:
        missing.append("时间限制")
    if memory_limit is None:
        missing.append("空间限制")
    if missing:
        raise VerificationError(
            "无法从 generated_problem.constraints 解析标准解"
            + "、".join(missing)
            + "；请提供带明确标签和单位的约束，例如“时间限制: 2s”“空间限制: 512MB”。"
        )

    return {
        "timeout_seconds": time_limit,
        "memory_limit_mb": memory_limit,
        "source": "generated_problem.constraints",
        "raw_time_limit": raw_time_limit,
        "raw_memory_limit": raw_memory_limit,
    }


def _validate_input(
    *,
    context: str,
    validate_code: str,
    input_string: str,
    execution_config: ExecutionConfig,
) -> None:
    result = run_validate_test_input(
        validate_code,
        input_string,
        timeout_seconds=execution_config.test_input_timeout_seconds,
        memory_limit_mb=execution_config.test_input_memory_limit_mb,
    )
    _ensure_true_result(context, result)


def _test_input_failure_record(
    *,
    source: str,
    local_index: int,
    failure_stage: str,
    error_report: str,
    failing_input: str = "",
) -> dict[str, Any]:
    return {
        "source": source,
        "source_index": local_index,
        "failure_stage": failure_stage,
        "error_report": error_report,
        "failing_input": _truncate_middle(failing_input, 4000) if failing_input else "",
    }


def _format_return_value_failure(result: ExecutionResult, *, expectation: str) -> str:
    return json.dumps(
        {
            "expectation": expectation,
            "actual_return_value": result.return_value,
            "execution_result": _result_summary(result),
        },
        ensure_ascii=False,
        indent=2,
    )


def _collect_generated_inputs_once(
    *,
    source: str,
    generator_code: str,
    validate_code: str,
    start_index: int,
    execution_config: ExecutionConfig,
    context_limits: LLMContextLimits,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    cases: list[dict[str, Any]] = []
    for local_index in range(1, 11):
        result = run_generate_test_input(
            generator_code,
            timeout_seconds=execution_config.test_input_timeout_seconds,
            memory_limit_mb=execution_config.test_input_memory_limit_mb,
        )
        if result.status != EXECUTION_OK:
            return cases, _test_input_failure_record(
                source=source,
                local_index=local_index,
                failure_stage="run_generate_test_input",
                error_report=_format_execution_report(
                    result,
                    expectation="generate_test_input() 必须正常返回非空输入字符串。",
                ),
            )
        if not isinstance(result.return_value, str) or not result.return_value.strip():
            return cases, _test_input_failure_record(
                source=source,
                local_index=local_index,
                failure_stage="return_value_type",
                error_report=_format_return_value_failure(
                    result,
                    expectation="generate_test_input() 必须返回非空字符串，不能返回列表、None 或其它类型。",
                ),
            )

        input_string = result.return_value
        validate_result = run_validate_test_input(
            validate_code,
            input_string,
            timeout_seconds=execution_config.test_input_timeout_seconds,
            memory_limit_mb=execution_config.test_input_memory_limit_mb,
        )
        if validate_result.status != EXECUTION_OK:
            return cases, _test_input_failure_record(
                source=source,
                local_index=local_index,
                failure_stage="run_validate_test_input",
                error_report=_format_execution_report(
                    validate_result,
                    expectation="validate_test_input(input_string) 必须正常返回 True/False。",
                ),
                failing_input=input_string,
            )
        if validate_result.return_value is not True:
            return cases, _test_input_failure_record(
                source=source,
                local_index=local_index,
                failure_stage="run_validate_test_input",
                error_report=_format_return_value_failure(
                    validate_result,
                    expectation="生成出的输入必须被 validate_test_input 判为 True。",
                ),
                failing_input=input_string,
            )

        case_id = f"case_{start_index + local_index - 1:03d}"
        cases.append(
            {
                "case_id": case_id,
                "source": source,
                "source_index": local_index,
                "input": input_string,
                **_input_case_metadata(input_string, context_limits),
            }
        )
    return cases, None


def _repair_test_input_payload(
    artifact: dict[str, Any],
    client: ChatLLMClient,
    *,
    source: str,
    repair_round: int,
    current_payload: dict[str, Any],
    failure: dict[str, Any],
) -> dict[str, Any]:
    task_name = f"test_input_debug:{source}:{repair_round}"
    return _call_prompt(
        client,
        task_name=task_name,
        system_prompt=prompt_test_input_debug.build_system_prompt(),
        user_prompt=prompt_test_input_debug.build_user_prompt(
            artifact,
            source=source,
            constraint_analysis=str(current_payload.get("constraint_analysis", "")),
            generate_test_input_code=str(current_payload.get("generate_test_input_code", "")),
            validate_test_input_code=str(current_payload.get("validate_test_input_code", "")),
            failure_stage=str(failure.get("failure_stage", "")),
            error_report=str(failure.get("error_report", "")),
            failing_input=str(failure.get("failing_input", "")),
        ),
        validator=lambda payload, task_name=task_name: validate_test_generator_response(payload, task_name=task_name),
    )


def _format_test_input_repair_failure(
    *,
    source: str,
    failure: dict[str, Any],
    repair_history: list[dict[str, Any]],
) -> str:
    return (
        f"{source} 测试输入生成器修复超过 {TEST_INPUT_REPAIR_LIMIT} 轮仍失败："
        + json.dumps(
            {
                "last_failure": failure,
                "repair_history": repair_history,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _collect_generated_inputs(
    *,
    artifact: dict[str, Any],
    client: ChatLLMClient,
    source: str,
    payload: dict[str, Any],
    start_index: int,
    execution_config: ExecutionConfig,
    context_limits: LLMContextLimits,
) -> dict[str, Any]:
    current_payload = dict(payload)
    repair_history: list[dict[str, Any]] = []
    while True:
        cases, failure = _collect_generated_inputs_once(
            source=source,
            generator_code=current_payload["generate_test_input_code"],
            validate_code=current_payload["validate_test_input_code"],
            start_index=start_index,
            execution_config=execution_config,
            context_limits=context_limits,
        )
        if failure is None:
            if repair_history:
                _emit_progress(
                    f"[verification repair] {source} 测试输入修复循环结束；"
                    f"累计修复 {len(repair_history)} 轮，重新收集 10 条输入通过。"
                )
            return {
                "payload": current_payload,
                "cases": cases,
                "repair_history": repair_history,
            }
        if len(repair_history) >= TEST_INPUT_REPAIR_LIMIT:
            raise VerificationError(
                _format_test_input_repair_failure(
                    source=source,
                    failure=failure,
                    repair_history=repair_history,
                )
            )

        repair_round = len(repair_history) + 1
        _emit_repair_progress(f"{source} 测试输入修复", repair_round, "开始。")
        repair = _repair_test_input_payload(
            artifact,
            client,
            source=source,
            repair_round=repair_round,
            current_payload=current_payload,
            failure=failure,
        )
        repair_history.append(
            {
                "source": source,
                "repair_round": repair_round,
                "failure": failure,
                "repair": repair,
            }
        )
        current_payload = repair
        _emit_repair_progress(f"{source} 测试输入修复", repair_round, "完成，重新收集该来源 10 条输入。")


def _collect_small_challenge_inputs(
    *,
    artifact: dict[str, Any],
    client: ChatLLMClient,
    initial_payload: dict[str, Any],
    validate_code: str,
    start_index: int,
    execution_config: ExecutionConfig,
    context_limits: LLMContextLimits,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for local_index in range(1, 11):
        if local_index == 1:
            payload = initial_payload
        else:
            task_name = f"small_challenge_test_input:verified:{local_index}"
            payload = _call_prompt(
                client,
                task_name=task_name,
                system_prompt=prompt_small_challenge_test_input.build_system_prompt(),
                user_prompt=prompt_small_challenge_test_input.build_user_prompt(artifact),
                validator=lambda item, task_name=task_name: validate_small_challenge_response(
                    item,
                    task_name=task_name,
                ),
            )
        input_string = payload["test_input"]
        _validate_input(
            context=f"small_challenge 第 {local_index} 条输入",
            validate_code=validate_code,
            input_string=input_string,
            execution_config=execution_config,
        )
        case_id = f"case_{start_index + local_index - 1:03d}"
        cases.append(
            {
                "case_id": case_id,
                "source": "small_challenge",
                "source_index": local_index,
                "input": input_string,
                **_input_case_metadata(input_string, context_limits),
            }
        )
    return cases


def collect_verified_test_inputs(
    artifact: dict[str, Any],
    generated_artifacts: dict[str, Any],
    client: ChatLLMClient,
    execution_config: ExecutionConfig,
    context_limits: LLMContextLimits,
) -> dict[str, Any]:
    """收集 30 个已通过本地 validate 函数的合法输入。"""

    test_inputs = generated_artifacts["test_inputs"]
    random_payload = test_inputs["random"]
    adversarial_payload = test_inputs["adversarial"]
    small_payload = test_inputs["small_challenge"]

    cases: list[dict[str, Any]] = []
    repair_history: list[dict[str, Any]] = []
    random_collection = _collect_generated_inputs(
        artifact=artifact,
        client=client,
        source="random",
        payload=random_payload,
        start_index=1,
        execution_config=execution_config,
        context_limits=context_limits,
    )
    test_inputs["random"] = random_collection["payload"]
    random_payload = test_inputs["random"]
    cases.extend(random_collection["cases"])
    repair_history.extend(random_collection["repair_history"])

    adversarial_collection = _collect_generated_inputs(
        artifact=artifact,
        client=client,
        source="adversarial",
        payload=adversarial_payload,
        start_index=11,
        execution_config=execution_config,
        context_limits=context_limits,
    )
    test_inputs["adversarial"] = adversarial_collection["payload"]
    cases.extend(adversarial_collection["cases"])
    repair_history.extend(adversarial_collection["repair_history"])

    cases.extend(
        _collect_small_challenge_inputs(
            artifact=artifact,
            client=client,
            initial_payload=small_payload,
            validate_code=random_payload["validate_test_input_code"],
            start_index=21,
            execution_config=execution_config,
            context_limits=context_limits,
        )
    )
    return {
        "status": "ok",
        "cases": cases,
        "count": len(cases),
        "source_counts": {
            "random": 10,
            "adversarial": 10,
            "small_challenge": 10,
        },
        "small_challenge_llm_calls_including_initial": 10,
        "test_input_repair_history": repair_history,
        "test_input_repair_iteration_count": len(repair_history),
    }


def _repair_bruteforce(
    artifact: dict[str, Any],
    client: ChatLLMClient,
    *,
    current_code: str,
    failing_input: str,
    error_report: str,
) -> dict[str, Any]:
    return _call_prompt(
        client,
        task_name="bruteforce_debug",
        system_prompt=prompt_bruteforce_debug.build_system_prompt(),
        user_prompt=prompt_bruteforce_debug.build_user_prompt(
            artifact,
            bruteforce_code=current_code,
            failing_input=failing_input,
            error_report=error_report,
        ),
        validator=lambda payload: validate_code_repair_response(payload, task_name="bruteforce_debug"),
    )


def _shrink_large_bruteforce_failure(
    *,
    current_code: str,
    original_input: str,
    validate_code: str,
    original_result: ExecutionResult,
    execution_config: ExecutionConfig,
) -> dict[str, Any]:
    """尝试把多测试组大输入缩小为仍可复现同类错误的小输入。"""

    parsed = _parse_constant_line_test_cases(original_input)
    if parsed is None:
        return {
            "status": "not_reproduced",
            "reason": "unsupported_input_structure",
            "attempt_count": 0,
        }
    header, cases = parsed
    if len(cases) <= 1:
        return {
            "status": "not_reproduced",
            "reason": "single_case_input",
            "attempt_count": 0,
        }

    attempts: list[dict[str, Any]] = []
    found_size: int | None = None
    size = 1
    while size <= len(cases):
        candidate = _build_constant_line_test_input(header, cases[:size])
        attempt = _try_shrink_candidate(
            candidate,
            current_code=current_code,
            validate_code=validate_code,
            original_result=original_result,
            execution_config=execution_config,
        )
        attempt["case_count"] = size
        attempts.append(attempt)
        if attempt["reproduced"]:
            found_size = size
            break
        size *= 2

    if found_size is None:
        return {
            "status": "not_reproduced",
            "reason": "prefix_search_not_reproduced",
            "attempt_count": len(attempts),
            "attempts": attempts,
        }

    low = 1
    high = found_size
    best_input = _build_constant_line_test_input(header, cases[:found_size])
    while low < high:
        mid = (low + high) // 2
        candidate = _build_constant_line_test_input(header, cases[:mid])
        attempt = _try_shrink_candidate(
            candidate,
            current_code=current_code,
            validate_code=validate_code,
            original_result=original_result,
            execution_config=execution_config,
        )
        attempt["case_count"] = mid
        attempts.append(attempt)
        if attempt["reproduced"]:
            high = mid
            best_input = candidate
        else:
            low = mid + 1

    return {
        "status": "reproduced",
        "reason": "constant_line_test_case_prefix",
        "input": best_input,
        "input_chars": len(best_input),
        "case_count": high,
        "attempt_count": len(attempts),
        "attempts": attempts,
    }


def _parse_constant_line_test_cases(input_string: str) -> tuple[int, list[list[str]]] | None:
    lines = input_string.splitlines()
    if len(lines) < 3:
        return None
    try:
        test_count = int(lines[0].strip())
    except ValueError:
        return None
    if test_count <= 1:
        return None
    body = lines[1:]
    if len(body) % test_count != 0:
        return None
    lines_per_case = len(body) // test_count
    if lines_per_case <= 0:
        return None
    cases = [
        body[index : index + lines_per_case]
        for index in range(0, len(body), lines_per_case)
    ]
    return test_count, cases


def _build_constant_line_test_input(_original_test_count: int, cases: list[list[str]]) -> str:
    lines = [str(len(cases))]
    for case_lines in cases:
        lines.extend(case_lines)
    return "\n".join(lines)


def _try_shrink_candidate(
    candidate: str,
    *,
    current_code: str,
    validate_code: str,
    original_result: ExecutionResult,
    execution_config: ExecutionConfig,
) -> dict[str, Any]:
    validate_result = run_validate_test_input(
        validate_code,
        candidate,
        timeout_seconds=execution_config.test_input_timeout_seconds,
        memory_limit_mb=execution_config.test_input_memory_limit_mb,
    )
    if validate_result.status != EXECUTION_OK or validate_result.return_value is not True:
        return {
            "valid": False,
            "reproduced": False,
            "input_chars": len(candidate),
            "validation_result": _result_summary(validate_result),
        }

    result = run_solution(
        current_code,
        candidate,
        timeout_seconds=execution_config.bruteforce_timeout_seconds,
        memory_limit_mb=execution_config.bruteforce_memory_limit_mb,
    )
    return {
        "valid": True,
        "reproduced": _is_same_failure(original_result, result),
        "input_chars": len(candidate),
        "execution_result": _result_summary(result),
    }


def _is_same_failure(original: ExecutionResult, candidate: ExecutionResult) -> bool:
    return (
        candidate.status == original.status
        and candidate.phase == original.phase
        and candidate.error_type == original.error_type
    )


def verify_bruteforce_solution(
    artifact: dict[str, Any],
    bruteforce_payload: dict[str, Any],
    input_cases: list[dict[str, Any]],
    client: ChatLLMClient,
    execution_config: ExecutionConfig,
    context_limits: LLMContextLimits,
    validate_code: str,
) -> dict[str, Any]:
    if bruteforce_payload.get("status") != "ok":
        raise VerificationError("暴力解法未生成成功，无法执行验证：" + str(bruteforce_payload.get("block_reason", "")))

    current_code = bruteforce_payload["code"]
    repair_history: list[dict[str, Any]] = []
    iteration = 0
    while True:
        iteration += 1
        solved_cases: list[dict[str, Any]] = []
        large_scale_inputs: list[dict[str, Any]] = []
        large_scale_runtime_failures: list[dict[str, Any]] = []
        should_restart = False

        for case in input_cases:
            result = run_solution(
                current_code,
                case["input"],
                timeout_seconds=execution_config.bruteforce_timeout_seconds,
                memory_limit_mb=execution_config.bruteforce_memory_limit_mb,
            )
            if result.status == EXECUTION_OK and isinstance(result.return_value, str):
                solved_cases.append(
                    _solved_case_payload(
                        case=case,
                        output=result.return_value,
                        context_limits=context_limits,
                    )
                )
                continue
            if result.status in (EXECUTION_TIMEOUT, EXECUTION_MEMORY_LIMIT):
                large_scale_inputs.append(
                    {
                        "case_id": case["case_id"],
                        "source": case["source"],
                        "input": case["input"],
                        "classification": "large_scale_input",
                        "execution_result": _result_summary(result),
                    }
                )
                continue

            shrink_result: dict[str, Any] | None = None
            if result.status != EXECUTION_OK and _is_case_input_too_large(case, context_limits):
                shrink_result = _shrink_large_bruteforce_failure(
                    current_code=current_code,
                    original_input=case["input"],
                    validate_code=validate_code,
                    original_result=result,
                    execution_config=execution_config,
                )
                if shrink_result["status"] != "reproduced":
                    large_scale_runtime_failures.append(
                        {
                            "case_id": case["case_id"],
                            "source": case["source"],
                            "input": case["input"],
                            "classification": "large_scale_runtime_failure",
                            "input_chars": len(case["input"]),
                            "execution_result": _result_summary(result),
                            "shrink_result": shrink_result,
                        }
                    )
                    continue

            repair_input = case["input"]
            if result.status == EXECUTION_OK:
                error_report = json.dumps(
                    {
                        "expectation": "solve(input_str) 必须返回字符串。",
                        "actual_return_value": result.return_value,
                        "execution_result": _result_summary(result),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                if shrink_result is not None and shrink_result["status"] == "reproduced":
                    repair_input = shrink_result["input"]
                    error_report = json.dumps(
                        {
                            "expectation": "暴力解法应正常返回输出字符串。",
                            "original_large_input": {
                                "case_id": case["case_id"],
                                "input_chars": len(case["input"]),
                                "execution_result": _result_summary(result),
                            },
                            "shrink_result": {
                                key: value
                                for key, value in shrink_result.items()
                                if key != "input"
                            },
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                else:
                    error_report = _format_execution_report(result, expectation="暴力解法应正常返回输出字符串。")
            repair_round = len(repair_history) + 1
            _emit_repair_progress("暴力解法修复", repair_round, "开始。")
            repair = _repair_bruteforce(
                artifact,
                client,
                current_code=current_code,
                failing_input=repair_input,
                error_report=error_report,
            )
            repair_history.append(
                {
                    "iteration": iteration,
                    "failed_case_id": case["case_id"],
                    "failed_input": repair_input,
                    "original_failed_input_chars": len(case["input"]),
                    "shrink_result": (
                        {key: value for key, value in shrink_result.items() if key != "input"}
                        if shrink_result
                        else None
                    ),
                    "error_report": error_report,
                    "repair": repair,
                }
            )
            current_code = repair["code"]
            should_restart = True
            _emit_repair_progress("暴力解法修复", repair_round, "完成，重新验证全部输入。")
            logger.info("暴力解法已修复，准备重新验证全部输入: iteration=%s", iteration)
            break

        if not should_restart:
            if repair_history:
                _emit_progress(
                    f"[verification repair] 暴力解法修复循环结束；累计修复 {len(repair_history)} 轮，验证通过。"
                )
            return {
                "status": "ok",
                "final_code": current_code,
                "solved_cases": solved_cases,
                "solved_case_count": len(solved_cases),
                "large_scale_inputs": large_scale_inputs,
                "large_scale_input_count": len(large_scale_inputs),
                "large_scale_runtime_failures": large_scale_runtime_failures,
                "large_scale_runtime_failure_count": len(large_scale_runtime_failures),
                "repair_history": repair_history,
                "repair_iteration_count": len(repair_history),
            }


def _repair_checker_false_reject(
    artifact: dict[str, Any],
    client: ChatLLMClient,
    *,
    current_code: str,
    failing_input: str,
    failing_output: str,
    error_report: str,
) -> dict[str, Any]:
    return _call_prompt(
        client,
        task_name="checker_false_reject_debug",
        system_prompt=prompt_checker_false_reject_debug.build_system_prompt(),
        user_prompt=prompt_checker_false_reject_debug.build_user_prompt(
            artifact,
            checker_code=current_code,
            failing_input=failing_input,
            failing_output=failing_output,
            error_report=error_report,
        ),
        validator=lambda payload: validate_checker_repair_response(
            payload,
            task_name="checker_false_reject_debug",
        ),
    )


def _repair_checker_false_accept(
    artifact: dict[str, Any],
    client: ChatLLMClient,
    *,
    current_code: str,
    failing_input: str,
    wrong_output: str,
    error_report: str,
) -> dict[str, Any]:
    return _call_prompt(
        client,
        task_name="checker_false_accept_debug",
        system_prompt=prompt_checker_false_accept_debug.build_system_prompt(),
        user_prompt=prompt_checker_false_accept_debug.build_user_prompt(
            artifact,
            checker_code=current_code,
            failing_input=failing_input,
            wrong_output=wrong_output,
            error_report=error_report,
        ),
        validator=lambda payload: validate_checker_repair_response(
            payload,
            task_name="checker_false_accept_debug",
        ),
    )


def _verify_checker_property_1(
    artifact: dict[str, Any],
    client: ChatLLMClient,
    *,
    checker_code: str,
    solved_cases: list[dict[str, Any]],
    execution_config: ExecutionConfig,
    repair_history: list[dict[str, Any]],
) -> str:
    initial_repair_count = len(repair_history)
    while True:
        restarted = False
        for case in solved_cases:
            result = run_checker(
                checker_code,
                case["input"],
                case["output"],
                timeout_seconds=execution_config.checker_timeout_seconds,
                memory_limit_mb=execution_config.checker_memory_limit_mb,
            )
            if result.status == EXECUTION_OK and result.return_value is True:
                continue
            error_report = _format_execution_report(result, expectation="合法输出必须被 checker 判为 AC/True。")
            if not case.get("llm_eligible", True):
                repair_history.append(
                    {
                        "property": "no_false_reject",
                        "classification": "large_case_false_reject_not_repaired",
                        "failed_case_id": case["case_id"],
                        "input_chars": len(case["input"]),
                        "output_chars": len(case["output"]),
                        "error_report": error_report,
                    }
                )
                continue
            repair_round = len(repair_history) + 1
            _emit_repair_progress("checker 误拒修复", repair_round, "开始。")
            repair = _repair_checker_false_reject(
                artifact,
                client,
                current_code=checker_code,
                failing_input=case["input"],
                failing_output=case["output"],
                error_report=error_report,
            )
            repair_history.append(
                {
                    "property": "no_false_reject",
                    "failed_case_id": case["case_id"],
                    "failed_input": case["input"],
                    "failed_output": case["output"],
                    "error_report": error_report,
                    "repair": repair,
                }
            )
            checker_code = repair["checker_code"]
            restarted = True
            _emit_repair_progress("checker 误拒修复", repair_round, "完成，重新验证性质1。")
            logger.info("checker 误拒修复完成，重新验证性质1。")
            break
        if not restarted:
            repaired_count = len(repair_history) - initial_repair_count
            if repaired_count:
                _emit_progress(
                    f"[verification repair] checker 误拒修复循环结束；累计修复 {repaired_count} 轮，性质1通过。"
                )
            return checker_code


def _checker_property_1_summary(solved_cases: list[dict[str, Any]], repair_history: list[dict[str, Any]]) -> dict[str, Any]:
    large_unrepaired = [
        item
        for item in repair_history
        if item.get("classification") == "large_case_false_reject_not_repaired"
    ]
    if large_unrepaired:
        return {
            "status": "partial_large_case_failures",
            "checked_count": len(solved_cases),
            "large_unrepaired_count": len(large_unrepaired),
            "large_unrepaired_cases": [
                {
                    "case_id": item.get("failed_case_id", ""),
                    "input_chars": item.get("input_chars", 0),
                    "output_chars": item.get("output_chars", 0),
                }
                for item in large_unrepaired
            ],
        }
    return {"status": "ok", "checked_count": len(solved_cases)}


def _generate_counterexamples(
    artifact: dict[str, Any],
    client: ChatLLMClient,
    solved_cases: list[dict[str, Any]],
    context_limits: LLMContextLimits,
) -> dict[str, Any]:
    selected_cases, skipped_cases = _select_llm_cases(solved_cases, context_limits)
    if not selected_cases:
        return {
            "counterexamples": [],
            "skipped": [],
            "llm_case_selection": {
                "status": "skipped",
                "reason": "没有满足 LLM 上下文预算的可读真值用例。",
                "selected_count": 0,
                "skipped_count": len(skipped_cases),
                "skipped_cases": skipped_cases,
            },
        }
    prompt_cases = [
        {
            "case_id": case["case_id"],
            "input": case["input"],
            "correct_output": case["output"],
        }
        for case in selected_cases
    ]
    result = _call_prompt(
        client,
        task_name="checker_counterexample_generation",
        system_prompt=prompt_checker_counterexample.build_system_prompt(),
        user_prompt=prompt_checker_counterexample.build_user_prompt(artifact, solved_cases=prompt_cases),
        validator=lambda payload: validate_counterexample_response(
            payload,
            task_name="checker_counterexample_generation",
        ),
    )
    result["llm_case_selection"] = {
        "status": "ok",
        "selected_count": len(selected_cases),
        "skipped_count": len(skipped_cases),
        "selected_case_ids": [case["case_id"] for case in selected_cases],
        "skipped_cases": skipped_cases,
        "total_selected_io_chars": sum(int(case.get("total_io_chars", 0)) for case in selected_cases),
    }
    return result


def verify_checker(
    artifact: dict[str, Any],
    checker_payload: dict[str, Any],
    solved_cases: list[dict[str, Any]],
    client: ChatLLMClient,
    execution_config: ExecutionConfig,
    context_limits: LLMContextLimits,
) -> dict[str, Any]:
    if not checker_payload.get("needs_checker"):
        return {
            "status": "skipped",
            "reason": checker_payload.get("reason", "该题不需要特殊 checker。"),
        }
    if not solved_cases:
        return {
            "status": "skipped",
            "reason": "没有可由暴力解法产出真值的测试用例，无法验证 checker。",
        }

    checker_code = checker_payload["checker_code"]
    repair_history: list[dict[str, Any]] = []
    checker_code = _verify_checker_property_1(
        artifact,
        client,
        checker_code=checker_code,
        solved_cases=solved_cases,
        execution_config=execution_config,
        repair_history=repair_history,
    )

    counterexamples = _generate_counterexamples(artifact, client, solved_cases, context_limits)
    invalid_cases = counterexamples["counterexamples"]
    if not invalid_cases:
        return {
            "status": "counterexamples_empty",
            "final_checker_code": checker_code,
            "property_1": _checker_property_1_summary(solved_cases, repair_history),
            "property_2": {"status": "not_checked", "checked_count": 0},
            "counterexamples": counterexamples,
            "repair_history": repair_history,
        }

    checked_counterexamples: list[dict[str, Any]] = []
    index = 0
    while index < len(invalid_cases):
        item = invalid_cases[index]
        result = run_checker(
            checker_code,
            item["input"],
            item["wrong_output"],
            timeout_seconds=execution_config.checker_timeout_seconds,
            memory_limit_mb=execution_config.checker_memory_limit_mb,
        )
        if result.status == EXECUTION_OK and result.return_value is False:
            checked_counterexamples.append(
                {
                    "source_case_id": item["source_case_id"],
                    "primary_strategy": item["primary_strategy"],
                    "verdict": "WA",
                    "execution_result": _result_summary(result),
                }
            )
            index += 1
            continue

        expectation = "非法输出必须被 checker 稳定判为 WA/False。"
        error_report = _format_execution_report(result, expectation=expectation)
        repair_round = len(repair_history) + 1
        _emit_repair_progress("checker 误收修复", repair_round, "开始。")
        repair = _repair_checker_false_accept(
            artifact,
            client,
            current_code=checker_code,
            failing_input=item["input"],
            wrong_output=item["wrong_output"],
            error_report=error_report,
        )
        repair_history.append(
            {
                "property": "no_false_accept",
                "source_case_id": item["source_case_id"],
                "wrong_output": item["wrong_output"],
                "primary_strategy": item["primary_strategy"],
                "error_report": error_report,
                "repair": repair,
            }
        )
        checker_code = repair["checker_code"]
        _emit_repair_progress("checker 误收修复", repair_round, "完成，重新验证性质1和性质2。")
        checker_code = _verify_checker_property_1(
            artifact,
            client,
            checker_code=checker_code,
            solved_cases=solved_cases,
            execution_config=execution_config,
            repair_history=repair_history,
        )
        checked_counterexamples = []
        index = 0
        logger.info("checker 误收修复完成，重新验证性质1和性质2。")

    return {
        "status": "ok",
        "final_checker_code": checker_code,
        "property_1": _checker_property_1_summary(solved_cases, repair_history),
        "property_2": {"status": "ok", "checked_count": len(invalid_cases)},
        "counterexamples": counterexamples,
        "checked_counterexamples": checked_counterexamples,
        "repair_history": repair_history,
        "repair_iteration_count": len(repair_history),
    }


def _repair_standard_solution(
    artifact: dict[str, Any],
    client: ChatLLMClient,
    *,
    initial_code: str,
    current_code: str,
    failing_input: str,
    expected_output: str,
    actual_output: str,
    error_report: str,
) -> dict[str, Any]:
    return _call_prompt(
        client,
        task_name="standard_solution_debug",
        system_prompt=prompt_standard_solution_debug.build_system_prompt(),
        user_prompt=prompt_standard_solution_debug.build_user_prompt(
            artifact,
            initial_code=initial_code,
            current_code=current_code,
            failing_input=failing_input,
            expected_output=expected_output,
            actual_output=actual_output,
            error_report=error_report,
        ),
        validator=lambda payload: validate_code_repair_response(payload, task_name="standard_solution_debug"),
    )


def _checker_code_for_standard_verification(
    checker_payload: dict[str, Any],
    checker_verification: dict[str, Any],
) -> str | None:
    if not checker_payload.get("needs_checker"):
        return None
    checker_code = checker_verification.get("final_checker_code")
    if not isinstance(checker_code, str) or not checker_code.strip():
        raise VerificationError("题目需要 checker，但 checker 未完成验证，无法验证标准解输出。")
    return checker_code


def _standard_output_failure_report(
    *,
    solution_result: ExecutionResult,
    expected_output: str,
    actual_output: str,
    checker_result: ExecutionResult | None,
) -> str:
    if checker_result is not None:
        return json.dumps(
            {
                "expectation": "标准解输出必须被 checker 判为 AC/True。",
                "expected_output_reference": expected_output,
                "actual_output": actual_output,
                "standard_solution_execution_result": _result_summary(solution_result),
                "checker_execution_result": _result_summary(checker_result),
            },
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps(
        {
            "expectation": "标准解输出必须与小规模真值输出完全一致。",
            "expected_output": expected_output,
            "actual_output": actual_output,
            "standard_solution_execution_result": _result_summary(solution_result),
        },
        ensure_ascii=False,
        indent=2,
    )


def verify_standard_solution(
    artifact: dict[str, Any],
    standard_payload: dict[str, Any],
    solved_cases: list[dict[str, Any]],
    checker_payload: dict[str, Any],
    checker_verification: dict[str, Any],
    client: ChatLLMClient,
    execution_config: ExecutionConfig,
) -> dict[str, Any]:
    if standard_payload.get("status") != "ok":
        raise VerificationError("标准解未生成成功，无法执行验证：" + str(standard_payload.get("block_reason", "")))
    if not solved_cases:
        raise VerificationError("没有可用于验证标准解的小规模真值用例。")

    standard_limits = _parse_standard_solution_limits(artifact)
    checker_code = _checker_code_for_standard_verification(checker_payload, checker_verification)
    initial_code = standard_payload["code"]
    current_code = initial_code
    repair_history: list[dict[str, Any]] = []
    iteration = 0

    while True:
        iteration += 1
        checked_cases: list[dict[str, Any]] = []
        should_restart = False

        for case in solved_cases:
            result = run_solution(
                current_code,
                case["input"],
                timeout_seconds=standard_limits["timeout_seconds"],
                memory_limit_mb=standard_limits["memory_limit_mb"],
            )
            expected_output = case["output"]
            actual_output = result.return_value if result.status == EXECUTION_OK and isinstance(result.return_value, str) else ""

            if result.status == EXECUTION_OK and isinstance(result.return_value, str):
                if checker_code is None:
                    if actual_output == expected_output:
                        checked_cases.append({"case_id": case["case_id"], "verdict": "accepted"})
                        continue
                    error_report = _standard_output_failure_report(
                        solution_result=result,
                        expected_output=expected_output,
                        actual_output=actual_output,
                        checker_result=None,
                    )
                else:
                    checker_result = run_checker(
                        checker_code,
                        case["input"],
                        actual_output,
                        timeout_seconds=execution_config.checker_timeout_seconds,
                        memory_limit_mb=execution_config.checker_memory_limit_mb,
                    )
                    if checker_result.status == EXECUTION_OK and checker_result.return_value is True:
                        checked_cases.append({"case_id": case["case_id"], "verdict": "accepted_by_checker"})
                        continue
                    error_report = _standard_output_failure_report(
                        solution_result=result,
                        expected_output=expected_output,
                        actual_output=actual_output,
                        checker_result=checker_result,
                    )
            elif result.status == EXECUTION_OK:
                error_report = json.dumps(
                    {
                        "expectation": "solve(input_str) 必须返回字符串。",
                        "expected_output": expected_output,
                        "actual_return_value": result.return_value,
                        "standard_solution_execution_result": _result_summary(result),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                error_report = _format_execution_report(result, expectation="标准解应在题面限制内正常返回输出字符串。")

            repair_round = len(repair_history) + 1
            _emit_repair_progress("标准解修复", repair_round, "开始。")
            repair = _repair_standard_solution(
                artifact,
                client,
                initial_code=initial_code,
                current_code=current_code,
                failing_input=case["input"],
                expected_output=expected_output,
                actual_output=actual_output,
                error_report=error_report,
            )
            repair_history.append(
                {
                    "iteration": iteration,
                    "failed_case_id": case["case_id"],
                    "failed_input": case["input"],
                    "expected_output": expected_output,
                    "actual_output": actual_output,
                    "error_report": error_report,
                    "repair": repair,
                }
            )
            current_code = repair["code"]
            should_restart = True
            _emit_repair_progress("标准解修复", repair_round, "完成，重新验证全部小规模真值输入。")
            logger.info("标准解已修复，准备重新验证全部小规模真值输入: iteration=%s", iteration)
            break

        if not should_restart:
            if repair_history:
                _emit_progress(
                    f"[verification repair] 标准解修复循环结束；累计修复 {len(repair_history)} 轮，验证通过。"
                )
            return {
                "status": "ok",
                "final_code": current_code,
                "checked_cases": checked_cases,
                "checked_count": len(checked_cases),
                "standard_solution_limits": standard_limits,
                "checker_used": checker_code is not None,
                "repair_history": repair_history,
                "repair_iteration_count": len(repair_history),
            }


def generate_large_scale_truth_outputs(
    standard_code: str,
    large_scale_inputs: list[dict[str, Any]],
    standard_limits: dict[str, Any],
) -> dict[str, Any]:
    if not large_scale_inputs:
        return {
            "status": "skipped",
            "reason": "没有大规模测试输入。",
            "cases": [],
            "count": 0,
            "attempted_count": 0,
            "failed_cases": [],
            "failure_count": 0,
            "standard_solution_limits": standard_limits,
        }

    cases: list[dict[str, Any]] = []
    failed_cases: list[dict[str, Any]] = []
    for index, case in enumerate(large_scale_inputs, start=1):
        case_id = str(case.get("case_id", ""))
        classification = str(case.get("classification", "large_scale_input"))
        result = run_solution(
            standard_code,
            case["input"],
            timeout_seconds=standard_limits["timeout_seconds"],
            memory_limit_mb=standard_limits["memory_limit_mb"],
        )
        if result.status in {EXECUTION_TIMEOUT, EXECUTION_MEMORY_LIMIT}:
            failed_cases.append(
                {
                    "case_id": case_id,
                    "source": case["source"],
                    "classification": classification,
                    "input": case["input"],
                    "failure_reason": result.status,
                    "execution_result": _result_summary(result),
                }
            )
            continue
        if result.status != EXECUTION_OK or not isinstance(result.return_value, str):
            raise VerificationError(
                f"标准解生成第 {index} 条大规模真值输出失败："
                f"case_id={case_id}；classification={classification}；"
                + json.dumps(_result_summary(result), ensure_ascii=False, indent=2)
            )
        cases.append(
            {
                "case_id": case_id,
                "source": case["source"],
                "classification": classification,
                "input": case["input"],
                "output": result.return_value,
                "execution_result": _result_summary(result),
            }
        )

    return {
        "status": "partial_large_scale_failures" if failed_cases else "ok",
        "cases": cases,
        "count": len(cases),
        "attempted_count": len(large_scale_inputs),
        "failed_cases": failed_cases,
        "failure_count": len(failed_cases),
        "standard_solution_limits": standard_limits,
    }


def _large_scale_truth_input_cases(bruteforce_verification: dict[str, Any]) -> list[dict[str, Any]]:
    """合并所有需要由标准解生成真值的大规模输入。"""

    return [
        *bruteforce_verification.get("large_scale_inputs", []),
        *bruteforce_verification.get("large_scale_runtime_failures", []),
    ]


def _flatten_wrong_solution_candidates(wrong_solutions: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for category, payload in wrong_solutions.get("fixed_categories", {}).items():
        code = payload.get("code") if isinstance(payload, dict) else None
        if not isinstance(code, str) or not code.strip():
            continue
        candidates.append(
            {
                "candidate_id": f"wrong_{len(candidates) + 1:03d}",
                "source": "fixed_category",
                "category": category,
                "strategy": {
                    "title": category,
                    "wrong_idea": f"固定类别错误解：{category}",
                    "plausible_reason": "由固定错误类别生成。",
                    "failure_reason": "需要通过测试执行确认。",
                    "trigger_case": "由定向测试输入生成阶段补充。",
                },
                "code": code,
            }
        )

    for item in wrong_solutions.get("strategy_based", []):
        if not isinstance(item, dict):
            continue
        solution = item.get("solution")
        strategy = item.get("strategy")
        code = solution.get("code") if isinstance(solution, dict) else None
        if not isinstance(strategy, dict) or not isinstance(code, str) or not code.strip():
            continue
        candidates.append(
            {
                "candidate_id": f"wrong_{len(candidates) + 1:03d}",
                "source": "strategy_based",
                "category": "",
                "strategy": strategy,
                "code": code,
            }
        )
    return candidates


def _candidate_prompt_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate["candidate_id"],
        "source": candidate["source"],
        "category": candidate.get("category", ""),
        "strategy": candidate["strategy"],
        "code": candidate["code"],
    }


def _verified_input_prompt_summary(solved_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for case in solved_cases:
        summary.append(
            {
                "case_id": case["case_id"],
                "source": case["source"],
                "input": _truncate_middle(case["input"], 1200),
            }
        )
    return summary


def _generate_wrong_solution_targeted_input(
    artifact: dict[str, Any],
    client: ChatLLMClient,
    *,
    round_index: int,
    candidate: dict[str, Any],
    solved_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    task_name = f"wrong_solution_targeted_input:{round_index}:{candidate['candidate_id']}"
    return _call_prompt(
        client,
        task_name=task_name,
        system_prompt=prompt_wrong_solution_targeted_test_input.build_system_prompt(),
        user_prompt=prompt_wrong_solution_targeted_test_input.build_user_prompt(
            artifact,
            wrong_solution_candidate=_candidate_prompt_payload(candidate),
            verified_input_cases=_verified_input_prompt_summary(solved_cases),
        ),
        validator=lambda payload, task_name=task_name: validate_small_challenge_response(
            payload,
            task_name=task_name,
        ),
    )


def _append_targeted_input_if_solved(
    *,
    verified_test_inputs: dict[str, Any],
    solved_cases: list[dict[str, Any]],
    input_string: str,
    validate_code: str,
    bruteforce_code: str,
    execution_config: ExecutionConfig,
    context_limits: LLMContextLimits,
) -> dict[str, Any]:
    for case in verified_test_inputs["cases"]:
        if case["input"] == input_string:
            return {"status": "skipped", "reason": "duplicate_input", "input": input_string}

    validate_result = run_validate_test_input(
        validate_code,
        input_string,
        timeout_seconds=execution_config.test_input_timeout_seconds,
        memory_limit_mb=execution_config.test_input_memory_limit_mb,
    )
    if validate_result.status != EXECUTION_OK or validate_result.return_value is not True:
        return {
            "status": "skipped",
            "reason": "invalid_input",
            "input": input_string,
            "validation_result": _result_summary(validate_result),
        }

    solve_result = run_solution(
        bruteforce_code,
        input_string,
        timeout_seconds=execution_config.bruteforce_timeout_seconds,
        memory_limit_mb=execution_config.bruteforce_memory_limit_mb,
    )
    if solve_result.status != EXECUTION_OK or not isinstance(solve_result.return_value, str):
        return {
            "status": "skipped",
            "reason": "bruteforce_unsolved",
            "input": input_string,
            "execution_result": _result_summary(solve_result),
        }

    source_counts = verified_test_inputs.setdefault("source_counts", {})
    source_index = int(source_counts.get("wrong_pool_targeted", 0)) + 1
    case_id = f"case_{len(verified_test_inputs['cases']) + 1:03d}"
    input_case = {
        "case_id": case_id,
        "source": "wrong_pool_targeted",
        "source_index": source_index,
        "input": input_string,
        **_input_case_metadata(input_string, context_limits),
    }
    solved_case = _solved_case_payload(
        case=input_case,
        output=solve_result.return_value,
        context_limits=context_limits,
    )
    verified_test_inputs["cases"].append(input_case)
    verified_test_inputs["count"] = len(verified_test_inputs["cases"])
    source_counts["wrong_pool_targeted"] = source_index
    solved_cases.append(solved_case)
    return {
        "status": "added",
        "case_id": case_id,
        "source_index": source_index,
        "input": input_string,
        "output": solve_result.return_value,
    }


def _evaluate_wrong_solution_candidate(
    candidate: dict[str, Any],
    solved_cases: list[dict[str, Any]],
    *,
    checker_code: str | None,
    execution_config: ExecutionConfig,
    context_limits: LLMContextLimits,
) -> dict[str, Any]:
    checked_count = 0
    for case in solved_cases:
        solution_result = run_solution(
            candidate["code"],
            case["input"],
            timeout_seconds=execution_config.bruteforce_timeout_seconds,
            memory_limit_mb=execution_config.bruteforce_memory_limit_mb,
        )
        if solution_result.status != EXECUTION_OK or not isinstance(solution_result.return_value, str):
            return {
                "candidate": _candidate_prompt_payload(candidate),
                "status": "invalid",
                "failed_case_id": case["case_id"],
                "execution_result": _result_summary(solution_result),
                "checked_count": checked_count,
            }

        checked_count += 1
        wrong_output = solution_result.return_value
        if checker_code is None:
            if wrong_output != case["output"]:
                return {
                    "candidate": _candidate_prompt_payload(candidate),
                    "status": "killed",
                    "verdict": "output_mismatch",
                    "failed_case_id": case["case_id"],
                    "input": case["input"],
                    "correct_output": case["output"],
                    "wrong_output": wrong_output,
                    "checked_count": checked_count,
                }
            continue

        checker_result = run_checker(
            checker_code,
            case["input"],
            wrong_output,
            timeout_seconds=execution_config.checker_timeout_seconds,
            memory_limit_mb=execution_config.checker_memory_limit_mb,
        )
        if checker_result.status == EXECUTION_OK and checker_result.return_value is False:
            return {
                "candidate": _candidate_prompt_payload(candidate),
                "status": "killed",
                "verdict": "checker_rejected",
                "failed_case_id": case["case_id"],
                "input": case["input"],
                "correct_output": case["output"],
                "wrong_output": wrong_output,
                "checker_execution_result": _result_summary(checker_result),
                "checked_count": checked_count,
            }

    return {
        "candidate": _candidate_prompt_payload(candidate),
        "status": "survived",
        "checked_count": checked_count,
    }


def _evaluate_wrong_solution_pool(
    candidates: list[dict[str, Any]],
    solved_cases: list[dict[str, Any]],
    *,
    checker_code: str | None,
    execution_config: ExecutionConfig,
    context_limits: LLMContextLimits,
) -> list[dict[str, Any]]:
    return [
        _evaluate_wrong_solution_candidate(
            candidate,
            solved_cases,
            checker_code=checker_code,
            execution_config=execution_config,
            context_limits=context_limits,
        )
        for candidate in candidates
    ]


def _wrong_pool_status_counts(evaluation_records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "killed_count": sum(1 for record in evaluation_records if record["status"] == "killed"),
        "survived_count": sum(1 for record in evaluation_records if record["status"] == "survived"),
        "invalid_count": sum(1 for record in evaluation_records if record["status"] == "invalid"),
    }


def _killed_original_survivor_ids(
    evaluation_records: list[dict[str, Any]],
    original_survivor_ids: set[str],
) -> set[str]:
    return {
        record["candidate"]["candidate_id"]
        for record in evaluation_records
        if record["status"] == "killed" and record["candidate"]["candidate_id"] in original_survivor_ids
    }


def _kill_ratio(killed_ids: set[str], original_survivor_ids: set[str]) -> float:
    if not original_survivor_ids:
        return 1.0
    return len(killed_ids) / len(original_survivor_ids)


def verify_wrong_solution_pool(
    artifact: dict[str, Any],
    generated_artifacts: dict[str, Any],
    verified_test_inputs: dict[str, Any],
    bruteforce_verification: dict[str, Any],
    checker_verification: dict[str, Any],
    client: ChatLLMClient,
    execution_config: ExecutionConfig,
    context_limits: LLMContextLimits,
) -> dict[str, Any]:
    """执行单题临时错误解池增强验证，并返回更新后的真值用例和 checker。"""

    candidates = _flatten_wrong_solution_candidates(generated_artifacts["wrong_solutions"])
    current_verified_inputs = {
        **verified_test_inputs,
        "cases": list(verified_test_inputs["cases"]),
        "source_counts": dict(verified_test_inputs.get("source_counts", {})),
    }
    solved_cases = list(bruteforce_verification["solved_cases"])
    checker_code = checker_verification.get("final_checker_code")
    if not generated_artifacts["checker"].get("needs_checker"):
        checker_code = None

    if not candidates:
        return {
            "verification": {
                "status": "skipped",
                "reason": "没有可执行的错误解候选。",
                "rounds": [],
                "candidate_count": 0,
                "killed_count": 0,
                "survived_count": 0,
                "invalid_count": 0,
                "targeted_input_count": 0,
                "original_survivor_count": 0,
                "cumulative_killed_original_survivor_count": 0,
                "kill_ratio": 1.0,
            },
            "verified_test_inputs": current_verified_inputs,
            "solved_cases": solved_cases,
        }
    if not solved_cases:
        return {
            "verification": {
                "status": "skipped",
                "reason": "没有可由暴力解法产出真值的测试用例，无法评估错误解池。",
                "rounds": [],
                "candidate_count": len(candidates),
                "killed_count": 0,
                "survived_count": len(candidates),
                "invalid_count": 0,
                "targeted_input_count": 0,
                "original_survivor_count": 0,
                "cumulative_killed_original_survivor_count": 0,
                "kill_ratio": 1.0,
            },
            "verified_test_inputs": current_verified_inputs,
            "solved_cases": solved_cases,
        }

    validate_code = generated_artifacts["test_inputs"]["random"]["validate_test_input_code"]
    bruteforce_code = bruteforce_verification["final_code"]
    round_records: list[dict[str, Any]] = []
    targeted_inputs: list[dict[str, Any]] = []
    final_evaluation = _evaluate_wrong_solution_pool(
        candidates=candidates,
        solved_cases=solved_cases,
        checker_code=checker_code,
        execution_config=execution_config,
        context_limits=context_limits,
    )
    original_survivor_ids = {
        record["candidate"]["candidate_id"]
        for record in final_evaluation
        if record["status"] == "survived"
    }
    if not original_survivor_ids:
        initial_counts = _wrong_pool_status_counts(final_evaluation)
        return {
            "verification": {
                "status": "ok",
                "rounds": [
                    {
                        "round": 0,
                        **initial_counts,
                        "selected_candidate_ids": [],
                        "targeted_inputs": [],
                        "original_survivor_count": 0,
                        "cumulative_killed_original_survivor_count": 0,
                        "kill_ratio": 1.0,
                        "stop_reason": "no_survivor",
                    }
                ],
                "candidate_count": len(candidates),
                **initial_counts,
                "targeted_input_count": 0,
                "original_survivor_count": 0,
                "cumulative_killed_original_survivor_count": 0,
                "kill_ratio": 1.0,
                "targeted_inputs": targeted_inputs,
                "final_evaluation": final_evaluation,
            },
            "verified_test_inputs": current_verified_inputs,
            "solved_cases": solved_cases,
        }

    round_index = 0
    while True:
        round_index += 1
        current_counts = _wrong_pool_status_counts(final_evaluation)
        killed_original_ids = _killed_original_survivor_ids(final_evaluation, original_survivor_ids)
        current_kill_ratio = _kill_ratio(killed_original_ids, original_survivor_ids)
        selected = [
            record
            for record in final_evaluation
            if record["status"] == "survived"
            and record["candidate"]["candidate_id"] in original_survivor_ids
        ]
        round_record = {
            "round": round_index,
            **current_counts,
            "selected_candidate_ids": [record["candidate"]["candidate_id"] for record in selected],
            "targeted_inputs": [],
            "original_survivor_count": len(original_survivor_ids),
            "cumulative_killed_original_survivor_count": len(killed_original_ids),
            "kill_ratio": current_kill_ratio,
        }
        if current_kill_ratio >= WRONG_POOL_STOP_KILL_RATIO:
            round_record["stop_reason"] = "kill_ratio_reached"
            round_records.append(round_record)
            break
        if not selected:
            round_record["stop_reason"] = "no_valid_targeted_input"
            round_records.append(round_record)
            break

        added_count = 0
        for record in selected:
            candidate_id = record["candidate"]["candidate_id"]
            candidate = next(item for item in candidates if item["candidate_id"] == candidate_id)
            payload = _generate_wrong_solution_targeted_input(
                artifact,
                client,
                round_index=round_index,
                candidate=candidate,
                solved_cases=solved_cases,
            )
            append_result = _append_targeted_input_if_solved(
                verified_test_inputs=current_verified_inputs,
                solved_cases=solved_cases,
                input_string=payload["test_input"],
                validate_code=validate_code,
                bruteforce_code=bruteforce_code,
                execution_config=execution_config,
                context_limits=context_limits,
            )
            append_result = {
                "candidate_id": candidate_id,
                "payload": payload,
                **append_result,
            }
            targeted_inputs.append(append_result)
            round_record["targeted_inputs"].append(append_result)
            if append_result["status"] == "added":
                added_count += 1

        if added_count == 0:
            round_record["stop_reason"] = "no_valid_targeted_input"
            round_records.append(round_record)
            break

        final_evaluation = _evaluate_wrong_solution_pool(
            candidates=candidates,
            solved_cases=solved_cases,
            checker_code=checker_code,
            execution_config=execution_config,
            context_limits=context_limits,
        )
        round_records.append(round_record)

    final_counts = _wrong_pool_status_counts(final_evaluation)
    killed_original_ids = _killed_original_survivor_ids(final_evaluation, original_survivor_ids)
    final_kill_ratio = _kill_ratio(killed_original_ids, original_survivor_ids)
    added_targeted_count = sum(1 for item in targeted_inputs if item["status"] == "added")

    return {
        "verification": {
            "status": "ok",
            "rounds": round_records,
            "candidate_count": len(candidates),
            **final_counts,
            "targeted_input_count": added_targeted_count,
            "original_survivor_count": len(original_survivor_ids),
            "cumulative_killed_original_survivor_count": len(killed_original_ids),
            "kill_ratio": final_kill_ratio,
            "targeted_inputs": targeted_inputs,
            "final_evaluation": final_evaluation,
        },
        "verified_test_inputs": current_verified_inputs,
        "solved_cases": solved_cases,
    }


def generate_verified_artifacts(
    artifact: dict[str, Any],
    config: LLMConfig | None = None,
    *,
    client: ChatLLMClient | None = None,
    execution_config: ExecutionConfig | None = None,
    context_limits: Any | None = None,
) -> dict[str, Any]:
    """生成全部产物，并执行测试输入、暴力解法和 checker 验证闭环。"""

    resolved_config, active_client = _build_client(config, client)
    if execution_config is None:
        raise RuntimeError("ExecutionConfig 必须由总流程注入，子模块不再读取本地 .env。")
    active_execution_config = execution_config
    active_context_limits = LLMContextLimits.from_object(context_limits)
    _emit_progress("[verification 2/7] Prompt 与 LLM 生成开始。")
    generated_artifacts = generate_all_artifacts(artifact, resolved_config, client=active_client)
    _emit_progress("[verification 2/7] Prompt 与 LLM 生成完成。")

    _emit_progress("[verification 4/7] 本地验证闭环开始：收集合法输入。")
    verified_test_inputs = collect_verified_test_inputs(
        artifact,
        generated_artifacts,
        active_client,
        active_execution_config,
        active_context_limits,
    )
    _emit_progress(
        f"[verification 4/7] 合法输入收集完成；count={verified_test_inputs['count']}。"
    )
    _emit_progress("[verification 4/7] 暴力解法验证开始。")
    bruteforce_verification = verify_bruteforce_solution(
        artifact,
        generated_artifacts["bruteforce_solution"],
        verified_test_inputs["cases"],
        active_client,
        active_execution_config,
        active_context_limits,
        generated_artifacts["test_inputs"]["random"]["validate_test_input_code"],
    )
    _emit_progress(
        "[verification 4/7] 暴力解法验证完成；"
        f"solved={bruteforce_verification['solved_case_count']}；"
        f"large_scale={bruteforce_verification['large_scale_input_count']}；"
        f"large_runtime_failure={bruteforce_verification['large_scale_runtime_failure_count']}。"
    )
    _emit_progress("[verification 5/7] checker 验证开始。")
    checker_verification = verify_checker(
        artifact,
        generated_artifacts["checker"],
        bruteforce_verification["solved_cases"],
        active_client,
        active_execution_config,
        active_context_limits,
    )
    _emit_progress(f"[verification 5/7] checker 验证完成；status={checker_verification['status']}。")
    _emit_progress("[verification 6/7] 错误解池增强开始。")
    wrong_solution_pool_result = verify_wrong_solution_pool(
        artifact,
        generated_artifacts,
        verified_test_inputs,
        bruteforce_verification,
        checker_verification,
        active_client,
        active_execution_config,
        active_context_limits,
    )
    _emit_progress(
        "[verification 6/7] 错误解池增强完成；"
        f"kill_ratio={wrong_solution_pool_result['verification']['kill_ratio']:.2f}；"
        f"killed={wrong_solution_pool_result['verification']['killed_count']}。"
    )
    verified_test_inputs = wrong_solution_pool_result["verified_test_inputs"]
    bruteforce_verification = {
        **bruteforce_verification,
        "solved_cases": wrong_solution_pool_result["solved_cases"],
        "solved_case_count": len(wrong_solution_pool_result["solved_cases"]),
    }
    _emit_progress("[verification 4/7] 标准解本地验证开始。")
    standard_solution_verification = verify_standard_solution(
        artifact,
        generated_artifacts["standard_solution"],
        bruteforce_verification["solved_cases"],
        generated_artifacts["checker"],
        checker_verification,
        active_client,
        active_execution_config,
    )
    _emit_progress(
        "[verification 4/7] 标准解本地验证完成；"
        f"checked={standard_solution_verification['checked_count']}。"
    )
    _emit_progress("[verification 4/7] 大规模真值输出生成开始。")
    large_scale_truth_input_cases = _large_scale_truth_input_cases(bruteforce_verification)
    large_scale_truth_outputs = generate_large_scale_truth_outputs(
        standard_solution_verification["final_code"],
        large_scale_truth_input_cases,
        standard_solution_verification["standard_solution_limits"],
    )
    _emit_progress(
        "[verification 4/7] 大规模真值输出生成完成；"
        f"success={large_scale_truth_outputs['count']} "
        f"failed={large_scale_truth_outputs['failure_count']} "
        f"attempted={large_scale_truth_outputs['attempted_count']}。"
    )

    result = dict(generated_artifacts)
    final_checker_code = checker_verification.get("final_checker_code")
    if generated_artifacts["checker"].get("needs_checker") and final_checker_code:
        checker_result = {
            **generated_artifacts["checker"],
            "initial_checker_code": generated_artifacts["checker"]["checker_code"],
            "checker_code": final_checker_code,
            "verified_checker_code": final_checker_code,
        }
    else:
        checker_result = generated_artifacts["checker"]

    result.update(
        {
            "standard_solution": {
                **generated_artifacts["standard_solution"],
                "initial_code": generated_artifacts["standard_solution"]["code"],
                "code": standard_solution_verification["final_code"],
                "verified_code": standard_solution_verification["final_code"],
            },
            "bruteforce_solution": {
                **generated_artifacts["bruteforce_solution"],
                "initial_code": generated_artifacts["bruteforce_solution"]["code"],
                "code": bruteforce_verification["final_code"],
                "verified_code": bruteforce_verification["final_code"],
            },
            "checker": checker_result,
            "verified_test_inputs": verified_test_inputs,
            "bruteforce_verification": bruteforce_verification,
            "checker_verification": checker_verification,
            "standard_solution_verification": standard_solution_verification,
            "large_scale_truth_outputs": large_scale_truth_outputs,
            "wrong_solution_pool_verification": wrong_solution_pool_result["verification"],
            "execution_metadata": {
                "execution_config": {
                    "test_input_timeout_seconds": active_execution_config.test_input_timeout_seconds,
                    "test_input_memory_limit_mb": active_execution_config.test_input_memory_limit_mb,
                    "bruteforce_timeout_seconds": active_execution_config.bruteforce_timeout_seconds,
                    "bruteforce_memory_limit_mb": active_execution_config.bruteforce_memory_limit_mb,
                    "checker_timeout_seconds": active_execution_config.checker_timeout_seconds,
                    "checker_memory_limit_mb": active_execution_config.checker_memory_limit_mb,
                },
                "context_limits": {
                    "llm_case_max_chars": active_context_limits.llm_case_max_chars,
                    "llm_case_input_max_chars": active_context_limits.llm_case_input_max_chars,
                    "llm_case_output_max_chars": active_context_limits.llm_case_output_max_chars,
                    "llm_case_total_chars": active_context_limits.llm_case_total_chars,
                    "llm_case_max_count": active_context_limits.llm_case_max_count,
                    "max_llm_prompt_chars": active_context_limits.max_llm_prompt_chars,
                    "llm_trace_max_text_chars": active_context_limits.llm_trace_max_text_chars,
                },
                "verified_test_input_count": verified_test_inputs["count"],
                "solved_case_count": bruteforce_verification["solved_case_count"],
                "large_scale_input_count": bruteforce_verification["large_scale_input_count"],
                "large_scale_runtime_failure_count": bruteforce_verification[
                    "large_scale_runtime_failure_count"
                ],
                "standard_solution_timeout_seconds": standard_solution_verification["standard_solution_limits"][
                    "timeout_seconds"
                ],
                "standard_solution_memory_limit_mb": standard_solution_verification["standard_solution_limits"][
                    "memory_limit_mb"
                ],
                "standard_solution_repair_iteration_count": standard_solution_verification[
                    "repair_iteration_count"
                ],
                "standard_solution_checked_count": standard_solution_verification["checked_count"],
                "large_scale_truth_output_count": large_scale_truth_outputs["count"],
                "large_scale_truth_failure_count": large_scale_truth_outputs["failure_count"],
                "large_scale_truth_attempted_count": large_scale_truth_outputs["attempted_count"],
                "wrong_solution_pool_targeted_input_count": wrong_solution_pool_result["verification"][
                    "targeted_input_count"
                ],
                "wrong_solution_pool_killed_count": wrong_solution_pool_result["verification"]["killed_count"],
                "wrong_solution_pool_survived_count": wrong_solution_pool_result["verification"]["survived_count"],
                "test_input_repair_iteration_count": verified_test_inputs.get(
                    "test_input_repair_iteration_count",
                    0,
                ),
            },
        }
    )
    return result
