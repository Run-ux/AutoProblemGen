"""核心约束维度 Prompt。"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from ..label_vocab import (
        CONSTRAINT_SOURCE_SECTIONS,
    )
    from ..problem_schema import prepare_problem_record
    from .prompt_sections import build_problem_context
except ImportError:
    from label_vocab import (
        CONSTRAINT_SOURCE_SECTIONS,
    )
    from problem_schema import prepare_problem_record
    from prompts.prompt_sections import build_problem_context

if TYPE_CHECKING:
    from typing import Any, Dict


def build_system_prompt() -> str:
    return """你是编程竞赛题目约束条件分析专家。

你的任务是从题目全文中抽取核心语义约束。

科研定义：
- 核心约束指对合法对象、合法操作、合法状态或合法解集合产生语义作用的限制。
- 该维度只记录会改变可行性、转移合法性、可选解集合或目标定义的约束。
- 纯输入规模上界、时间限制与内存限制不属于该维度。

硬规则：
1. 只输出严格 JSON 对象，不输出任何解释文字。
2. name 是开放标签，必须使用稳定、抽象的小写英文加下划线格式。
3. name 应概括约束的算法语义，不得写成题目情境词、具体数值或整句条件。
4. source_sections 只能写证据所在的题面分节，不得写推理来源或代码来源。

证据优先级：
1. 题面全文中的任务描述
2. Input 分节
3. Output 分节
4. Constraints 分节
5. 标题

边界规则：
- 排除纯输入规模边界，例如 1 ≤ n ≤ 10^5。
- 排除时间限制与内存限制。
- 保留具有语义作用的范围约束，例如度数上界、操作次数上界、字符集限制、容量上限、可用步数上限。
- 同一语义约束只保留一条；若多个句子共同支撑同一约束，合并到同一条 description。
- name 不得使用 distinct_leq_k、max_min_diff_leq_d 这类实例化标签，具体数值与场景写入 description 或 formal。
- source_sections 只允许使用 description、input、output、constraints。
- 题面没有可确认的核心语义约束时，返回 {{"constraints": []}}。

判别边界：
- 具有语义作用的范围限制可以抽象为 range_bound 一类标签，但不要用于 n、m、q 或 a_i 的普通输入范围。
- 操作步数、修改次数或资源配额上界应与允许操作类型区分命名。
- 状态合法转移、顺序限制、互异性、覆盖、排除、包含、博弈最优性等不同语义应拆成不同抽象标签。
- 对同义或近义约束使用同一个稳定标签，避免同一语义在一题内出现多种命名。
"""


def build_user_prompt(problem: Dict[str, Any]) -> str:
    problem = prepare_problem_record(problem)
    context = build_problem_context(problem)
    return f"""请根据下列题目信息抽取核心约束。

{context}

字段说明：
1. constraints[].name 表示约束的开放抽象标签。存在约束项时填写稳定的小写英文加下划线标签；没有约束项时不出现。常见误填：把具体数值、题目名词或整句限制直接写进 name。
2. constraints[].description 表示该题中这条约束的具体语义内容。存在该约束项时始终填写；只有整条约束不存在时才不出现。常见误填：只写标签释义，不写当前题目的具体限制。
3. constraints[].formal 表示便于机器解析或后续分析的形式化表达。题面存在清晰公式、逻辑式或边界表达时填写；没有必要时留空。常见误填：把自然语言 description 原样重复到 formal。
4. constraints[].source_sections 表示证据出现在题面哪个分节。需要追溯证据位置时填写；无法明确定位时留空。常见误填：把推理来源、代码来源或不在允许集合中的值写进去。

请输出 JSON：
{{
  "constraints": [
    {{
      "name": "稳定抽象标签，例如 operation_limit",
      "description": "该题中的具体约束描述",
      "formal": "形式化表达，可留空",
      "source_sections": ["description", "input"]
    }}
  ]
}}

要求：
1. 字段说明优先于字段名直觉，不要仅凭命名猜测字段含义。
2. name 使用开放标签，但必须稳定、抽象、小写英文加下划线。
3. 不创建实例化标签，不把具体题目对象、数值、变量名写进 name。
4. description 负责表达该题中的具体限制条件。
5. formal 可选，source_sections 可选，且元素只能来自 description、input、output、constraints。
6. 纯输入规模边界与时间内存限制不要抽取。
7. 多句支撑同一约束时合并为一条。
8. 没有可确认约束时返回 {{"constraints": []}}。
"""


CONSTRAINTS_SCHEMA = {
    "type": "object",
    "required": ["constraints"],
    "additionalProperties": True,
    "properties": {
        "constraints": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "description"],
                "additionalProperties": True,
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "formal": {"type": "string"},
                    "source_sections": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": CONSTRAINT_SOURCE_SECTIONS,
                        },
                    },
                },
            },
        }
    },
}
