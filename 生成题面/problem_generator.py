from __future__ import annotations

import copy
import json
import re
from typing import Any

from models import GeneratedProblem, VariantPlan
from prompt_builder import build_generation_system_prompt, build_generation_user_prompt
from qwen_client import QwenClient
from rule_handlers import get_rule_handler
from schema_tools import dataclass_to_dict, normalize_forbidden_reuse_token


PROBLEM_CONTRACT_RETRY_LIMIT = 2


class ProblemGenerator:
    def __init__(
        self,
        client: QwenClient | None,
        temperature: float = 0.7,
        max_validation_attempts: int = 4,
        solver_verifier: Any | None = None,
    ):
        self.client = client
        self.temperature = temperature
        self.max_validation_attempts = max_validation_attempts
        self.solver_verifier = solver_verifier

    def generate(
        self,
        schema_context: dict[str, Any],
        plan: VariantPlan,
        original_problems: list[dict[str, Any]] | None = None,
        revision_context: dict[str, Any] | None = None,
    ) -> GeneratedProblem:
        if plan.planning_status != "ok":
            return GeneratedProblem(
                title="",
                description="",
                input_format="",
                output_format="",
                constraints=[],
                samples=[],
                notes="",
                status=plan.planning_status,
                error_reason=plan.planning_error_reason,
                feedback=plan.planning_feedback,
            )

        if (
            plan.predicted_schema_distance < plan.difference_plan.target_distance_band["min"]
            or len(plan.changed_axes_realized) < 2
        ):
            return GeneratedProblem(
                title="",
                description="",
                input_format="",
                output_format="",
                constraints=[],
                samples=[],
                notes="",
                status="difference_insufficient",
                error_reason=(
                    "规则规划未达到有效差异门槛。"
                    f" 预测距离={plan.predicted_schema_distance:.2f}，"
                    f"落地轴={', '.join(plan.changed_axes_realized) or '无'}。"
                ),
                feedback=plan.difference_plan.rationale,
            )

        if self.client is None:
            raise RuntimeError("未初始化 LLM 客户端，无法执行真实生成。")

        system_prompt = build_generation_system_prompt()
        user_prompt = build_generation_user_prompt(
            schema_context,
            plan,
            original_problem_references=original_problems or [],
            revision_context=revision_context,
        )
        last_errors: list[str] = []
        failure_history: list[dict[str, Any]] = []
        base_temperature = min(self.temperature, 0.3)
        new_schema = dataclass_to_dict(plan.new_schema_snapshot)
        max_attempts = max(1, min(self.max_validation_attempts, PROBLEM_CONTRACT_RETRY_LIMIT + 1))

        for attempt in range(1, max_attempts + 1):
            payload = self.client.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=max(0.1, base_temperature - 0.05 * (attempt - 1)),
                request_label=f"problem_statement_round{attempt}",
            )
            problem = self._normalize_payload(payload, plan)
            if problem.status in {"schema_insufficient", "difference_insufficient"}:
                return problem
            self._repair_problem(problem, new_schema)
            errors = self._validate_problem(problem, new_schema, plan, original_problems or [])
            if not errors:
                return problem

            last_errors = errors
            failure_history.append(
                {
                    "attempt": attempt,
                    "errors": errors,
                    "payload": payload,
                }
            )
            contract_errors, non_contract_errors = self._split_contract_errors(errors)
            if non_contract_errors or not contract_errors:
                break
            if attempt == max_attempts:
                break
            user_prompt = self._build_contract_retry_prompt(
                schema_context,
                plan,
                payload,
                contract_errors,
                attempt + 1,
                original_problems or [],
                revision_context,
                failure_history,
            )

        failure_detail = json.dumps(failure_history, ensure_ascii=False, indent=2)
        raise RuntimeError(
            "模型连续返回不合法题面，校验失败："
            + "；".join(last_errors[:5])
            + "；失败历史："
            + failure_detail
        )

    def _normalize_payload(self, payload: dict[str, Any], plan: VariantPlan) -> GeneratedProblem:
        status = self._clean_text(str(payload.get("status", "ok"))) or "ok"
        raw_samples = payload.get("samples", [])
        if not isinstance(raw_samples, list):
            raw_samples = []
        raw_constraints = payload.get("constraints", [])
        if not isinstance(raw_constraints, list):
            raw_constraints = []
        samples = []
        for item in raw_samples:
            if not isinstance(item, dict):
                continue
            samples.append(
                {
                    "input": self._clean_text(str(item.get("input", ""))),
                    "output": self._clean_text(str(item.get("output", ""))),
                    "explanation": self._clean_text(str(item.get("explanation", ""))),
                }
            )
        return GeneratedProblem(
            title=self._clean_text(str(payload.get("title", f"{plan.theme.name}任务"))),
            description=self._clean_text(str(payload.get("description", ""))),
            input_format=self._clean_text(str(payload.get("input_format", ""))),
            output_format=self._clean_text(str(payload.get("output_format", ""))),
            constraints=[
                self._clean_text(str(item))
                for item in raw_constraints
                if self._clean_text(str(item))
            ],
            samples=samples,
            notes=self._clean_text(str(payload.get("notes", ""))),
            status=status,
            error_reason=self._clean_text(str(payload.get("error_reason", ""))),
            feedback=self._clean_text(str(payload.get("feedback", ""))),
        )

    def _validate_problem(
        self,
        problem: GeneratedProblem,
        schema: dict[str, Any],
        plan: VariantPlan,
        original_problems: list[dict[str, Any]],
    ) -> list[str]:
        errors: list[str] = []

        if not problem.title:
            errors.append("title 不能为空。")
        if not problem.description:
            errors.append("description 不能为空。")
        if not problem.input_format:
            errors.append("input_format 不能为空。")
        if not problem.output_format:
            errors.append("output_format 不能为空。")

        if len(problem.constraints) < 2:
            errors.append("constraints 至少需要包含 2 条限制。")
        constraint_text = "\n".join(problem.constraints).lower()
        if "时间" not in constraint_text and "time" not in constraint_text:
            errors.append("constraints 必须包含时间限制。")
        if "空间" not in constraint_text and "memory" not in constraint_text:
            errors.append("constraints 必须包含空间限制。")

        if len(problem.samples) < 2:
            errors.append("samples 至少需要 2 组。")

        expected_sample_lines = self._infer_expected_sample_lines(schema)
        declared_line_count = self._extract_declared_line_count(
            "\n".join([problem.input_format, problem.description, problem.notes])
        )
        if expected_sample_lines is not None and declared_line_count is not None and declared_line_count != expected_sample_lines:
            errors.append(
                f"题面声明的输入项数量为 {declared_line_count}，但 new_schema 要求为 {expected_sample_lines}。"
            )

        for index, sample in enumerate(problem.samples, start=1):
            sample_input = sample.get("input", "").strip()
            sample_output = sample.get("output", "").strip()
            explanation = sample.get("explanation", "").strip()
            if not sample_input:
                errors.append(f"样例 {index} 的 input 不能为空。")
            if not sample_output:
                errors.append(f"样例 {index} 的 output 不能为空。")
            if not explanation:
                errors.append(f"样例 {index} 的 explanation 不能为空。")
            if "```" in sample_input or "```" in sample_output:
                errors.append(f"样例 {index} 不应包含 Markdown 代码块标记。")
            if self._contains_html_artifact(sample_input) or self._contains_html_artifact(sample_output):
                errors.append(f"样例 {index} 包含疑似 HTML 污染内容。")
            if expected_sample_lines is not None:
                actual_lines = len([line for line in sample_input.splitlines() if line.strip()])
                if actual_lines != expected_sample_lines:
                    errors.append(
                        f"样例 {index} 的输入行数应为 {expected_sample_lines}，实际为 {actual_lines}。"
                    )

        errors.extend(self._validate_objective(problem, plan))
        if errors:
            return errors

        errors.extend(self._validate_structural_commitments(problem, schema, plan))
        errors.extend(self._validate_rule_commitments(problem, plan))
        errors.extend(self._validate_source_reuse(problem, original_problems))
        return errors

    def _split_contract_errors(self, errors: list[str]) -> tuple[list[str], list[str]]:
        contract_errors: list[str] = []
        non_contract_errors: list[str] = []
        for error in errors:
            if self._is_contract_retryable_error(error):
                contract_errors.append(error)
            else:
                non_contract_errors.append(error)
        return contract_errors, non_contract_errors

    def _is_contract_retryable_error(self, error: str) -> bool:
        contract_markers = (
            "title 不能为空",
            "description 不能为空",
            "input_format 不能为空",
            "output_format 不能为空",
            "constraints 至少需要包含",
            "constraints 必须包含时间限制",
            "constraints 必须包含空间限制",
            "samples 至少需要",
            "题面声明的输入项数量",
            "样例",
            "当前 objective 是计数类",
            "当前 objective 是判定类",
            "当前 objective 是构造类",
            "当前 objective 要求字典序规范",
            "题面包含不应复用的原题标识或标题片段",
        )
        return any(marker in error for marker in contract_markers)

    def _repair_problem(self, problem: GeneratedProblem, schema: dict[str, Any]) -> None:
        expected_sample_lines = self._infer_expected_sample_lines(schema)
        if expected_sample_lines is None:
            return
        for sample in problem.samples:
            repaired_input = self._repair_sample_input(sample.get("input", ""), expected_sample_lines)
            if repaired_input is not None:
                sample["input"] = repaired_input

    def _infer_expected_sample_lines(self, schema: dict[str, Any]) -> int | None:
        input_structure = schema.get("input_structure", {})
        if input_structure.get("type") != "array":
            return None
        length = input_structure.get("length", {})
        min_length = length.get("min")
        max_length = length.get("max")
        if not isinstance(min_length, int) or min_length != max_length:
            return None
        if min_length <= 0 or min_length > 10:
            return None
        return min_length

    def _validate_objective(self, problem: GeneratedProblem, plan: VariantPlan) -> list[str]:
        objective_type = str(plan.objective.get("type", "")).lower()
        combined = "\n".join(
            [problem.description, problem.output_format, problem.notes, "\n".join(problem.constraints)]
        ).lower()
        errors: list[str] = []
        if objective_type == "counting":
            if not any(
                token in combined
                for token in (
                    "方案数",
                    "计数结果",
                    "合法方案数",
                    "不同方案数",
                    "个数",
                    "数量",
                    "number of ways",
                    "count result",
                    "count",
                )
            ):
                errors.append("当前 objective 是计数类，但题面没有明确说明输出的是方案数/计数结果。")
            if not any(
                token in combined
                for token in (
                    "不同方案",
                    "等价方案",
                    "重复计数",
                    "去重",
                    "视为同一种",
                    "distinct",
                    "deduplicate",
                    "unique",
                )
            ):
                errors.append("当前 objective 是计数类，但题面没有明确不同方案的定义或去重规则。")
            if not any(
                token in combined
                for token in (
                    "取模",
                    "模数",
                    "mod",
                    "998244353",
                    "1000000007",
                    "有限",
                    "有限性",
                    "上界",
                    "长度上限",
                    "输入规模",
                    "取值范围",
                    "至多",
                    "最多",
                    "bounded",
                    "finite",
                )
            ):
                errors.append("当前 objective 是计数类，但题面没有说明计数空间有限性的来源或取模规则。")
        if objective_type == "decision" and not any(token in combined for token in ("yes", "no", "是否", "存在")):
            errors.append("当前 objective 是判定类，但题面没有明确说明输出判定结果。")
        if objective_type == "construction" and not any(token in combined for token in ("构造", "方案", "witness", "输出一个")):
            errors.append("当前 objective 是构造类，但题面没有明确说明需要输出构造方案。")
        if objective_type == "lexicographic_optimize" and not any(
            token in combined for token in ("字典序", "lexicographic", "lexicographical", "lexicographically")
        ):
            errors.append("当前 objective 要求字典序规范，但题面未明确写出字典序规则。")
        return errors

    def _validate_structural_commitments(
        self,
        problem: GeneratedProblem,
        schema: dict[str, Any],
        plan: VariantPlan,
    ) -> list[str]:
        combined = "\n".join([problem.description, problem.notes, "\n".join(problem.constraints)]).lower()
        errors: list[str] = []
        input_structure = schema.get("input_structure", {})
        if not isinstance(input_structure, dict):
            input_structure = {}
        properties = input_structure.get("properties", {}) or {}
        if not isinstance(properties, dict):
            properties = {}
        if properties.get("ordered") and not any(token in combined for token in ("顺序", "依次", "in order")):
            errors.append("new_schema 带有顺序语义，但题面没有明确说明顺序约束。")
        if properties.get("cyclic") and not any(token in combined for token in ("循环", "首尾相接", "环", "cyclic")):
            errors.append("new_schema 带有循环语义，但题面没有明确说明循环语义。")
        return errors

    def _validate_rule_commitments(self, problem: GeneratedProblem, plan: VariantPlan) -> list[str]:
        if not plan.applied_rule:
            return []
        rule = copy.deepcopy(plan.rule_snapshot) if plan.rule_snapshot else {"id": plan.applied_rule, "handler": plan.applied_rule}
        handler = get_rule_handler(rule)
        outcome = handler.validate_problem(client=self.client, problem=problem, plan=plan)
        if outcome.events:
            plan.validation_trace.extend(dataclass_to_dict(event) for event in outcome.events)
        return list(outcome.errors)

    def _validate_source_reuse(
        self,
        problem: GeneratedProblem,
        original_problems: list[dict[str, Any]],
    ) -> list[str]:
        combined = normalize_forbidden_reuse_token(
            "\n".join(
                [problem.title, problem.description, problem.input_format, problem.output_format, problem.notes]
            )
        )
        errors: list[str] = []
        for original_problem in original_problems:
            forbidden = [
                normalize_forbidden_reuse_token(original_problem.get("problem_id", "")),
                normalize_forbidden_reuse_token(self._source_name(original_problem.get("source", ""))),
                normalize_forbidden_reuse_token(original_problem.get("title", "")),
                normalize_forbidden_reuse_token(original_problem.get("url", "")),
            ]
            for token in forbidden:
                if token and token in combined:
                    errors.append(f"题面包含不应复用的原题标识或标题片段：{token}")
                    return errors
        return errors

    def _source_name(self, source: Any) -> str:
        if isinstance(source, dict):
            for key in ("source_name", "name", "platform"):
                value = str(source.get(key, "")).strip()
                if value:
                    return value
            return ""
        return str(source)

    def _contains_html_artifact(self, text: str) -> bool:
        lowered = text.lower()
        return bool(re.search(r"<[^>]+>", text)) or "class=" in lowered or "style=" in lowered

    def _clean_text(self, text: str) -> str:
        cleaned = text.strip().replace("\\n", "\n")
        cleaned = re.sub(r"\\+$", "", cleaned)
        return cleaned.strip()

    def _extract_declared_line_count(self, text: str) -> int | None:
        patterns = [r"输入共\s*(\d+)\s*行", r"恰好\s*(\d+)\s*行", r"exactly\s*(\d+)\s*lines", r"(\d+)\s*行"]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def _repair_sample_input(self, text: str, expected_lines: int) -> str | None:
        stripped = text.strip()
        actual_lines = [line for line in stripped.splitlines() if line.strip()]
        if len(actual_lines) == expected_lines:
            return None
        candidates = [
            stripped.replace('","', "\n"),
            stripped.replace('", "', "\n"),
            stripped.replace('],[', "\n"),
            stripped.replace('] [', "\n"),
        ]
        for candidate in candidates:
            normalized = "\n".join(
                line.strip().strip('"').strip("'").strip("(").strip(")")
                for line in candidate.splitlines()
                if line.strip()
            )
            normalized_lines = [line for line in normalized.splitlines() if line.strip()]
            if len(normalized_lines) == expected_lines and not self._contains_html_artifact(normalized):
                return normalized
        return None

    def _build_contract_retry_prompt(
        self,
        schema_context: dict[str, Any],
        plan: VariantPlan,
        payload: dict[str, Any],
        errors: list[str],
        next_attempt: int,
        original_problems: list[dict[str, Any]],
        revision_context: dict[str, Any] | None,
        failure_history: list[dict[str, Any]],
    ) -> str:
        base_prompt = build_generation_user_prompt(
            schema_context,
            plan,
            original_problem_references=original_problems,
            revision_context=revision_context,
        )
        error_lines = "\n".join(f"- {error}" for error in errors)
        invalid_payload = json.dumps(payload, ensure_ascii=False, indent=2)
        history_summary = json.dumps(
            [
                {
                    "attempt": item["attempt"],
                    "errors": item["errors"],
                }
                for item in failure_history
            ],
            ensure_ascii=False,
            indent=2,
        )
        source_reuse_instruction = ""
        if any("题面包含不应复用的原题标识或标题片段" in error for error in errors):
            source_reuse_instruction = (
                "- 必须重写所有命中原题标识或标题片段的标题、叙事和说明文本；"
                "不得通过删除任务必要语义来规避校验，也不得改变 `new_schema`、任务定义或算法义务。\n"
            )
        return (
            f"{base_prompt}\n\n"
            "# 题面合同定向修复\n"
            f"上一次返回的题面 JSON 未通过题面合同校验。当前是第 {next_attempt} 次尝试。\n"
            "本轮只允许修复题面合同，不要改变 new_schema、difference_plan、目标语义或规则承诺。\n"
            "必须修复以下问题：\n"
            f"{error_lines}\n\n"
            "硬性要求：\n"
            "- 重新生成整份成功格式 JSON，不要只返回局部字段或补丁。\n"
            "- 不要把样例不足、输入/输出格式缺失、时间/空间限制缺失等合同错误改写成 `difference_insufficient`。\n"
            "- `samples` 至少 2 组，每组 input、output、explanation 均为非空纯文本。\n"
            "- `constraints` 必须明确时间限制和空间限制。\n"
            "- 如果目标是计数类，必须明确输出方案数/计数结果、不同方案或去重定义，并说明计数空间有限性来源或取模规则。\n"
            "- 样例输入必须是纯文本，不要包含引号拼接残留、HTML 片段或 Markdown 标记。\n"
            "- 必须按实例化后的 schema 写输入数量、目标函数和结构约束，不要退回种子题设定。\n\n"
            f"{source_reuse_instruction}"
            "此前失败摘要：\n"
            f"{history_summary}\n\n"
            "上一次的错误 JSON 如下，仅用于定位问题，不可局部复用：\n"
            f"{invalid_payload}"
        )

    def _build_retry_prompt(
        self,
        schema_context: dict[str, Any],
        plan: VariantPlan,
        payload: dict[str, Any],
        errors: list[str],
        next_attempt: int,
        original_problems: list[dict[str, Any]],
        revision_context: dict[str, Any] | None,
    ) -> str:
        base_prompt = build_generation_user_prompt(
            schema_context,
            plan,
            original_problem_references=original_problems,
            revision_context=revision_context,
        )
        error_lines = "\n".join(f"- {error}" for error in errors)
        invalid_payload = json.dumps(payload, ensure_ascii=False, indent=2)
        return (
            f"{base_prompt}\n\n"
            f"上一次返回未通过校验，请重新生成完整 JSON。当前是第 {next_attempt} 次尝试。\n"
            "必须修复以下问题：\n"
            f"{error_lines}\n\n"
            "额外要求：\n"
            "- 如果你判断 schema 本身不足以可靠生成题面，不要继续补全，直接返回 `status=\"schema_insufficient\"`。\n"
            "- 如果你判断差异计划无法在不复述原题任务的前提下落地，直接返回 `status=\"difference_insufficient\"`。\n"
            "- 样例输入必须是纯文本，不要包含引号拼接残留、HTML 片段或 Markdown 标记。\n"
            "- 必须按实例化后的 schema 写输入数量、目标函数和结构约束，不要退回种子题设定。\n"
            "- 重新生成整份 JSON，不要只修补局部字段。\n\n"
            "上一次的错误 JSON 如下，仅用于定位问题，不可复用：\n"
            f"{invalid_payload}"
        )
