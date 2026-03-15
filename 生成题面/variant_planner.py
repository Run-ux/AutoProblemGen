from __future__ import annotations

import random
from typing import Any

from models import Theme, VariantPlan


THEMES = [
    Theme(
        theme_id="cyber_city",
        name="赛博城市调度",
        tone="冷静、工程化、略带未来感",
        keywords=["节点", "数据流", "权限", "缓存", "链路", "控制台"],
        mapping_hint="把原始结构映射成网络节点、任务包或访问记录。",
    ),
    Theme(
        theme_id="arcane_lab",
        name="奥术实验室",
        tone="神秘、规则驱动、强调仪式感",
        keywords=["符文", "法阵", "共鸣", "晶核", "炼成", "序列"],
        mapping_hint="把状态变化映射成符文叠加、法阵拼接或能量共鸣。",
    ),
    Theme(
        theme_id="interstellar_logistics",
        name="星际物流",
        tone="宏观、任务导向、强调资源与路径",
        keywords=["货舱", "航线", "补给", "跃迁", "殖民地", "调度中心"],
        mapping_hint="把对象映射成货物、航线、站点、任务波次。",
    ),
    Theme(
        theme_id="campus_ops",
        name="校园运营",
        tone="日常、轻松、贴近现实",
        keywords=["社团", "教室", "队伍", "课表", "仓库", "窗口"],
        mapping_hint="把抽象约束映射成排队、分配、排课或借还流程。",
    ),
]


class VariantPlanner:
    def __init__(self, seed: int | None = None):
        self.seed = seed if seed is not None else random.randrange(1, 10**9)

    def build_plan(
        self, schema: dict[str, Any], variant_index: int, theme_id: str | None = None
    ) -> VariantPlan:
        rng = random.Random(self.seed + variant_index)
        theme = self._select_theme(rng, theme_id)

        transform_space = schema.get("transform_space", {})
        objective = self._select_objective(schema, transform_space, rng)
        numerical_parameters = self._materialize_parameters(transform_space, rng)
        structural_options = self._select_structural_options(transform_space, rng)

        return VariantPlan(
            problem_id=schema.get("problem_id", "unknown"),
            variant_index=variant_index,
            seed=self.seed + variant_index,
            theme=theme,
            objective=objective,
            numerical_parameters=numerical_parameters,
            structural_options=structural_options,
            difficulty=self._infer_difficulty(schema),
            input_summary=self._summarize_input_structure(schema.get("input_structure", {})),
            constraint_summary=self._summarize_constraints(
                schema.get("core_constraints", {}).get("constraints", [])
            ),
            invariant_summary=self._summarize_invariants(
                schema.get("invariant", {}).get("invariants", [])
            ),
        )

    def _select_theme(self, rng: random.Random, theme_id: str | None) -> Theme:
        if theme_id:
            for theme in THEMES:
                if theme.theme_id == theme_id:
                    return theme
            raise ValueError(f"Unknown theme_id: {theme_id}")
        return rng.choice(THEMES)

    def _select_objective(
        self,
        schema: dict[str, Any],
        transform_space: dict[str, Any],
        rng: random.Random,
    ) -> dict[str, Any]:
        original = schema.get("objective", {})
        options = transform_space.get("objective_options", [])
        if not options:
            return {
                "type": original.get("type", "unknown"),
                "description": original.get("description", ""),
            }
        chosen = rng.choice(options)
        return {
            "type": chosen,
            "description": self._describe_objective(chosen, original.get("description", "")),
        }

    def _materialize_parameters(
        self, transform_space: dict[str, Any], rng: random.Random
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, spec in transform_space.get("numerical_parameters", {}).items():
            min_value = spec.get("min")
            max_value = spec.get("max")
            if isinstance(min_value, int) and isinstance(max_value, int):
                choices = {
                    min_value,
                    max_value,
                    (min_value + max_value) // 2,
                    rng.randint(min_value, max_value),
                }
                value = rng.choice(sorted(choices))
            else:
                value = spec.get("default", "N/A")
            result[name] = {
                "value": value,
                "min": min_value,
                "max": max_value,
                "description": spec.get("description", ""),
            }
        return result

    def _select_structural_options(
        self, transform_space: dict[str, Any], rng: random.Random
    ) -> list[str]:
        options = list(transform_space.get("structural_options", []))
        if not options:
            return []
        count = rng.randint(0, min(2, len(options)))
        return rng.sample(options, count)

    def _infer_difficulty(self, schema: dict[str, Any]) -> str:
        invariants = schema.get("invariant", {}).get("invariants", [])
        constraints = schema.get("core_constraints", {}).get("constraints", [])
        score = len(invariants) + len(constraints)
        if score <= 2:
            return "Easy"
        if score <= 4:
            return "Medium"
        return "Hard"

    def _summarize_input_structure(self, data: dict[str, Any]) -> str:
        input_type = data.get("type", "unknown")
        length = data.get("length", {})
        value_range = data.get("value_range", {})
        parts = [f"类型={input_type}"]
        if length:
            parts.append(f"长度范围={length.get('min', '?')}..{length.get('max', '?')}")
        if value_range:
            parts.append(
                f"值范围={value_range.get('min', '?')}..{value_range.get('max', '?')}"
            )
        properties = data.get("properties", {})
        if properties:
            props = ", ".join(f"{key}={value}" for key, value in properties.items())
            parts.append(f"属性={props}")
        return "；".join(parts)

    def _summarize_constraints(self, constraints: list[dict[str, Any]]) -> list[str]:
        return [item.get("description", "") for item in constraints if item.get("description")]

    def _summarize_invariants(self, invariants: list[dict[str, Any]]) -> list[str]:
        return [item.get("description", "") for item in invariants if item.get("description")]

    def _describe_objective(self, objective_type: str, fallback: str) -> str:
        mapping = {
            "minimize": "求最小代价或最小长度。",
            "minimize_length": "求满足条件的最短结果。",
            "minimize_value": "求满足条件的最小值。",
            "maximize": "求最大收益或最大可行值。",
            "maximize_value": "求满足条件的最大值。",
            "count": "统计满足条件的方案数。",
            "count_minimal_strings": "统计达到最优结果的方案数。",
            "enumeration": "统计所有满足条件的对象数量。",
            "decision": "判断是否存在满足条件的方案。",
            "boolean_decision": "判断方案是否存在。",
            "lexicographically_first_minimal_string": "求最优结果中字典序最小的构造。",
        }
        return mapping.get(objective_type, fallback or objective_type)

