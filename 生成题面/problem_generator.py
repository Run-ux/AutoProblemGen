from __future__ import annotations

from typing import Any

from models import GeneratedProblem, VariantPlan
from prompt_builder import build_system_prompt, build_user_prompt
from qwen_client import QwenClient


class ProblemGenerator:
    def __init__(self, client: QwenClient | None, temperature: float = 0.7):
        self.client = client
        self.temperature = temperature

    def generate(
        self, schema: dict[str, Any], plan: VariantPlan, dry_run: bool = False
    ) -> GeneratedProblem:
        if dry_run:
            return self._build_template_problem(plan)

        if self.client is None:
            raise RuntimeError("未初始化 LLM 客户端，无法执行真实生成。")

        payload = self.client.chat_json(
            system_prompt=build_system_prompt(),
            user_prompt=build_user_prompt(schema, plan),
            temperature=self.temperature,
        )
        return self._normalize_payload(payload, plan)

    def _normalize_payload(
        self, payload: dict[str, Any], plan: VariantPlan
    ) -> GeneratedProblem:
        samples = []
        for item in payload.get("samples", []):
            if not isinstance(item, dict):
                continue
            samples.append(
                {
                    "input": str(item.get("input", "")).strip(),
                    "output": str(item.get("output", "")).strip(),
                    "explanation": str(item.get("explanation", "")).strip(),
                }
            )

        return GeneratedProblem(
            title=str(payload.get("title", f"{plan.theme.name}任务")).strip(),
            description=str(payload.get("description", "")).strip(),
            input_format=str(payload.get("input_format", "")).strip(),
            output_format=str(payload.get("output_format", "")).strip(),
            constraints=[
                str(item).strip() for item in payload.get("constraints", []) if str(item).strip()
            ],
            samples=samples,
            notes=str(payload.get("notes", "")).strip(),
        )

    def _build_template_problem(self, plan: VariantPlan) -> GeneratedProblem:
        parameter_lines = []
        for name, spec in plan.numerical_parameters.items():
            value = spec.get("value")
            desc = spec.get("description", "")
            parameter_lines.append(f"{name} = {value}（{desc}）")

        description_parts = [
            f"在“{plan.theme.name}”主题下，你需要设计一个满足既定规则的任务系统。",
            f"该任务的核心输入结构为：{plan.input_summary}。",
            f"目标为：{plan.objective.get('description', plan.objective.get('type', '未知目标'))}",
        ]
        if plan.constraint_summary:
            description_parts.append("核心约束包括：" + "；".join(plan.constraint_summary) + "。")
        if plan.invariant_summary:
            description_parts.append("题目应保持的结构性质包括：" + "；".join(plan.invariant_summary) + "。")
        if parameter_lines:
            description_parts.append("本次实例化参数：" + "；".join(parameter_lines) + "。")
        if plan.structural_options:
            description_parts.append(
                "启用的结构变体：" + "、".join(plan.structural_options) + "。"
            )

        return GeneratedProblem(
            title=f"{plan.theme.name} #{plan.variant_index}",
            description="\n\n".join(description_parts),
            input_format="根据 schema 自动实例化后的输入格式需由 LLM 或人工补全。",
            output_format="输出满足目标定义的结果。",
            constraints=[
                f"建议难度：{plan.difficulty}",
                "Time Limit: 1 second",
                "Memory Limit: 256 megabytes",
            ],
            samples=[
                {
                    "input": "TODO",
                    "output": "TODO",
                    "explanation": "dry-run 模式下不生成真实样例。",
                }
            ],
            notes="这是 dry-run 产物，用于验证流程是否跑通。",
        )

