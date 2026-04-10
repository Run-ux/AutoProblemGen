from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .models import DimensionScore, Issue


class ProblemQualityJudge:
    def __init__(self, client: Any | None = None):
        self.client = client

    def evaluate(
        self,
        new_schema: dict[str, Any],
        generated_problem: dict[str, Any],
        hard_checks: list[dict[str, Any]],
        review_context: dict[str, Any],
    ) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("当前版本的题目质量评价需要可用的 LLM Judge 接口。")
        return self._evaluate_with_llm(new_schema, generated_problem, hard_checks, review_context)

    def _evaluate_with_llm(
        self,
        new_schema: dict[str, Any],
        generated_problem: dict[str, Any],
        hard_checks: list[dict[str, Any]],
        review_context: dict[str, Any],
    ) -> dict[str, Any]:
        system_prompt = """你是一名算法竞赛题面审稿人。请根据 new_schema、生成题面、hard_checks 和 review_context，评估题面质量。

评分时使用以下统一 rubric：

1. variant_fidelity
- 定义：看 new_schema 中已经确定的任务变体、输入对象、目标函数、结构选项，是否真实落地到 generated_problem 的 description、input_format、output_format、constraints、samples。
- 不要看：它和原题像不像；这里只评估“new_schema 是否被准确实现”。

2. spec_completeness
- 定义：看题面是否提供了独立做题所需的关键信息，尤其是任务说明、输入格式、输出格式、约束、必要说明是否齐全。
- 如果读者仍需要自行猜测核心规则、边界条件或输出对象，则应降低分数。

3. cross_section_consistency
- 定义：看 description、input_format、output_format、constraints、samples 之间是否互相一致，是否出现字段数量、目标定义、样例格式、符号含义的冲突。
- 如果某一部分与另一部分矛盾，优先降这一维。

4. sample_quality
- 定义：看样例数量是否基本充足，样例输入输出是否与题意和格式匹配，解释是否有助于理解任务。
- 样例少、样例不能覆盖关键结构、样例解释缺失或误导，都应扣分。

5. oj_readability
- 定义：看题面是否符合正常 OJ 题面的表达习惯，结构清楚、措辞明确、噪声少、无明显来源污染或无关文本。
- 不要求文采，只看是否便于参赛者快速准确理解。

评分锚点：
- 5 分：该维度表现稳定，基本无明显问题，只有轻微可忽略瑕疵。
- 3 分：该维度存在明确但可修复的问题，不至于完全影响做题。
- 1 分：该维度存在严重问题，明显影响理解、实现或正确判题。

使用 hard_checks 的规则：
- hard_checks 是强证据。若某项 hard_check 明确失败，相关维度通常不能给高分。
- rationale 和 issues 必须尽量引用 hard_checks 或输入中的字段路径作为证据。
- 只依据给定字段路径做判断，不要臆测缺失信息。

使用 review_context 的规则：
- review_context 只作为辅助上下文，用来理解上游规划希望落地哪些变化。
- 主证据仍以 new_schema、generated_problem 和 hard_checks 为准。
- 如果 review_context 的声称内容与 new_schema 或 generated_problem 冲突，应以 new_schema 和 generated_problem 为准。
- 如果 review_context 声称存在某种结构变化、算法增量或 helper 落地，但题面没有兑现，应在 issues 中明确指出“规划意图未落地”。

必须返回严格 JSON，格式如下：
{
  "scores": {
    "variant_fidelity": {"score": 1-5, "rationale": string, "evidence_refs": string[]},
    "spec_completeness": {"score": 1-5, "rationale": string, "evidence_refs": string[]},
    "cross_section_consistency": {"score": 1-5, "rationale": string, "evidence_refs": string[]},
    "sample_quality": {"score": 1-5, "rationale": string, "evidence_refs": string[]},
    "oj_readability": {"score": 1-5, "rationale": string, "evidence_refs": string[]}
  },
  "issues": [
    {
      "severity": "major|minor",
      "title": string,
      "detail": string,
      "evidence_refs": string[],
      "fix_hint": string
    }
  ],
  "strengths": string[],
  "suggested_revisions": string[]
}

输出要求：
- 五个 scores 字段都必须返回。
- score 只能是 1 到 5 的整数。
- evidence_refs 只填输入中出现的字段路径或 hard_checks 中的 evidence_refs。
- 不要输出 JSON 之外的任何解释。"""
        user_prompt = json.dumps(
            {
                "new_schema": new_schema,
                "generated_problem": generated_problem,
                "hard_checks": hard_checks,
                "review_context": review_context,
            },
            ensure_ascii=False,
            indent=2,
        )
        result = self.client.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
        )
        return _validate_quality_result(result)


class SourceDivergenceJudge:
    def __init__(self, client: Any | None = None):
        self.client = client

    def evaluate(
        self,
        original_problem: dict[str, Any],
        original_schema: dict[str, Any],
        new_schema: dict[str, Any],
        generated_problem: dict[str, Any],
        hard_checks: list[dict[str, Any]],
        schema_distance: float,
        review_context: dict[str, Any],
    ) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("当前版本的题目质量评价需要可用的 LLM Judge 接口。")
        return self._evaluate_with_llm(
            original_problem,
            original_schema,
            new_schema,
            generated_problem,
            hard_checks,
            schema_distance,
            review_context,
        )

    def _evaluate_with_llm(
        self,
        original_problem: dict[str, Any],
        original_schema: dict[str, Any],
        new_schema: dict[str, Any],
        generated_problem: dict[str, Any],
        hard_checks: list[dict[str, Any]],
        schema_distance: float,
        review_context: dict[str, Any],
    ) -> dict[str, Any]:
        system_prompt = """你是一名算法竞赛命题审稿人。你的任务是判断新题是否只是原题换皮。

你要综合 original_problem、original_schema、new_schema、generated_problem、hard_checks、schema_distance 和 review_context 进行判断。

评分 rubric：

1. semantic_difference
- 定义：原题与新题在任务语义上的真实差异程度，取值 0.0 到 1.0。
- 高分表示：输入对象、约束结构、目标函数、求解关注点发生了实质变化，熟悉原题的选手不能只靠替换变量名或故事映射就直接套解。
- 低分表示：核心任务、状态定义、决策对象、最优性目标基本没变，只是换背景或轻微改写表述。

2. solution_transfer_risk
- 定义：熟悉原题标准解的选手，能否几乎原样迁移思路、状态设计、关键性质和实现框架到新题，取值 0.0 到 1.0。
- 高分表示：只需改命名、实体映射或很小的边角逻辑就能沿用原解。
- 低分表示：必须重新建模或重新选择关键算法，原题解法不能直接迁移。

3. surface_retheme_risk
- 定义：新题是否主要做了表层换皮，取值 0.0 到 1.0。
- 高分表示：标题、叙事、句式、任务定义、样例套路、名词映射与原题高度对应，文本或结构复用明显。
- 低分表示：即使主题相关，表述组织、任务展开和样例设计也没有明显复用痕迹。

判断时的重点：
- 先看 new_schema 相比 original_schema 是否真的改变了关键轴，再看 generated_problem 是否把这些变化真实落地。
- schema_distance 是强结构信号，但不是唯一依据；如果 schema_distance 不低，但新题语义和解法迁移风险仍然很接近原题，仍应判为换皮。
- hard_checks 中与 source_leakage、结构落地失败相关的失败项，是重要负面证据。
- 不要因为背景故事不同就高估 semantic_difference；关键看“会不会迫使解题者改变问题建模和解法”。
- review_context.distance_breakdown.axis_scores 与 review_context.changed_axes_realized 可用来定位变化轴，但它们只是结构先验，不能替代对 new_schema 和 generated_problem 的复核。
- review_context.algorithmic_delta_claim 与 review_context.anti_shallow_rationale 只视为上游声明，不能直接采信。
- 如果 review_context 声称变化明显，但 new_schema 或 generated_problem 没有兑现这些变化，solution_transfer_risk 仍应保持高值。
- surface_retheme_risk 继续以 original_problem 与 generated_problem 的文本和任务结构对照为主，不要因为 review_context 的规划说明而降低风险判断。

分数锚点：
- semantic_difference: 0.8-1.0 表示实质差异明显；0.4-0.6 表示有变化但核心求解框架仍较接近；0.0-0.2 表示基本只是换皮。
- solution_transfer_risk: 0.8-1.0 表示原解几乎可直接迁移；0.4-0.6 表示可部分复用但需要明显调整；0.0-0.2 表示原解基本不能直接迁移。
- surface_retheme_risk: 0.8-1.0 表示文本/叙事/样例复用明显；0.4-0.6 表示有局部复用；0.0-0.2 表示表层重合很少。

verdict 规则：
- 若新题主要是表层重主题、原题解法可直接迁移、或 semantic_difference 明显偏低，应返回 reject_as_retheme。
- 只有在“语义差异真实成立”且“解法迁移风险不高”时，才返回 pass。
- 当证据冲突时，宁可保守，不要轻易放过疑似换皮题。

必须返回严格 JSON：
{
  "semantic_difference": 0.0-1.0,
  "solution_transfer_risk": 0.0-1.0,
  "surface_retheme_risk": 0.0-1.0,
  "verdict": "pass|reject_as_retheme",
  "rationale": string,
  "evidence_refs": string[]
}

输出要求：
- 三个分数都必须是 0.0 到 1.0 的浮点数。
- rationale 要明确说明“哪些轴真的变了，哪些地方仍然高度可迁移/可复用”。
- evidence_refs 只填输入中出现的字段路径或 hard_checks 中的 evidence_refs。
- 不要输出 JSON 之外的任何解释。"""
        user_prompt = json.dumps(
            {
                "schema_distance": schema_distance,
                "original_problem": {
                    "title": original_problem.get("title", ""),
                    "description": original_problem.get("description", ""),
                    "input": original_problem.get("input", ""),
                    "output": original_problem.get("output", ""),
                    "constraints": original_problem.get("constraints", ""),
                },
                "original_schema": original_schema,
                "new_schema": new_schema,
                "generated_problem": generated_problem,
                "hard_checks": hard_checks,
                "review_context": review_context,
            },
            ensure_ascii=False,
            indent=2,
        )
        result = self.client.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
        )
        return _validate_divergence_result(result)


def _validate_quality_result(result: Any) -> dict[str, Any]:
    payload = _require_dict(result, "quality judge response")
    raw_scores = _require_dict(payload.get("scores"), "quality judge scores")
    dimensions = [
        "variant_fidelity",
        "spec_completeness",
        "cross_section_consistency",
        "sample_quality",
        "oj_readability",
    ]
    dimension_scores: list[dict[str, Any]] = []
    for dimension in dimensions:
        item = _require_dict(raw_scores.get(dimension), f"quality score {dimension}")
        dimension_scores.append(
            asdict(
                DimensionScore(
                    dimension=dimension,
                    score=float(_require_int_in_range(item.get("score"), f"{dimension}.score", 1, 5)),
                    rationale=_require_string(item.get("rationale"), f"{dimension}.rationale"),
                    evidence_refs=_require_string_list(item.get("evidence_refs"), f"{dimension}.evidence_refs"),
                )
            )
        )

    issues: list[dict[str, Any]] = []
    raw_issues = payload.get("issues", [])
    if not isinstance(raw_issues, list):
        raise ValueError("quality judge issues 必须是数组。")
    for index, item in enumerate(raw_issues):
        issue = _require_dict(item, f"quality issue {index}")
        severity = _require_string(issue.get("severity"), f"quality issue {index}.severity")
        if severity not in {"major", "minor"}:
            raise ValueError(f"quality issue {index}.severity 非法：{severity}")
        issues.append(
            asdict(
                Issue(
                    issue_type="quality_issue",
                    severity=severity,
                    title=_require_string(issue.get("title"), f"quality issue {index}.title"),
                    detail=_require_string(issue.get("detail"), f"quality issue {index}.detail"),
                    evidence_refs=_require_string_list(
                        issue.get("evidence_refs"),
                        f"quality issue {index}.evidence_refs",
                    ),
                    fix_hint=_require_string(issue.get("fix_hint"), f"quality issue {index}.fix_hint"),
                )
            )
        )

    return {
        "dimension_scores": dimension_scores,
        "issues": issues,
        "strengths": _require_string_list(payload.get("strengths"), "quality strengths"),
        "suggested_revisions": _require_string_list(
            payload.get("suggested_revisions"),
            "quality suggested_revisions",
        ),
    }


def _validate_divergence_result(result: Any) -> dict[str, Any]:
    payload = _require_dict(result, "divergence judge response")
    verdict = _require_string(payload.get("verdict"), "divergence verdict")
    if verdict not in {"pass", "reject_as_retheme"}:
        raise ValueError(f"divergence verdict 非法：{verdict}")
    return {
        "semantic_difference": _require_float_in_range(
            payload.get("semantic_difference"),
            "semantic_difference",
            0.0,
            1.0,
        ),
        "solution_transfer_risk": _require_float_in_range(
            payload.get("solution_transfer_risk"),
            "solution_transfer_risk",
            0.0,
            1.0,
        ),
        "surface_retheme_risk": _require_float_in_range(
            payload.get("surface_retheme_risk"),
            "surface_retheme_risk",
            0.0,
            1.0,
        ),
        "verdict": verdict,
        "rationale": _require_string(payload.get("rationale"), "divergence rationale"),
        "evidence_refs": _require_string_list(payload.get("evidence_refs"), "divergence evidence_refs"),
    }


def _require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} 必须是对象。")
    return value


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} 必须是字符串。")
    return value


def _require_string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} 必须是字符串数组。")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{name}[{index}] 必须是字符串。")
        result.append(item)
    return result


def _require_int_in_range(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 必须是整数。")
    integer = int(value)
    if integer != value or integer < minimum or integer > maximum:
        raise ValueError(f"{name} 超出范围：{value}")
    return integer


def _require_float_in_range(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 必须是数值。")
    number = float(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{name} 超出范围：{value}")
    return number
