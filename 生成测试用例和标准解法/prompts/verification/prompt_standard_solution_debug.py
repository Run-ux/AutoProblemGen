from __future__ import annotations

import json

from .._common import generated_problem_section, json_contract, schema_section


def build_system_prompt() -> str:
    return (
        "你是一个算法竞赛标准解调试助手。你的任务是修复给定的标准解代码，"
        "使其严格符合题意、通过已知小规模真值用例，并能够在题面限制内运行。"
        "最终只输出单个 JSON 对象。"
    )


def build_user_prompt(
    artifact: dict,
    *,
    initial_code: str,
    current_code: str,
    failure_summary: dict,
    failed_cases: list[dict],
    anchor_cases: list[dict],
    repair_attempts: list[dict],
) -> str:
    return "\n\n".join(
        [
            generated_problem_section(artifact),
            schema_section(artifact),
            "# 初始标准解完整代码",
            initial_code,
            "# 当前迭代标准解完整代码",
            current_code,
            "# 本轮失败分类统计",
            json.dumps(failure_summary, ensure_ascii=False, indent=2),
            "# 本轮代表性失败样例",
            json.dumps(failed_cases, ensure_ascii=False, indent=2),
            "# 已通过锚点用例",
            json.dumps(anchor_cases, ensure_ascii=False, indent=2),
            "# 历次修复尝试摘要",
            json.dumps(repair_attempts, ensure_ascii=False, indent=2),
            """# 修复要求
- 先综合本轮全部失败样例，输出根因分析，再输出修复计划，最后产出完整代码。
- 优先定位导致失败批次不通过的共同根因，并做通用修复。
- 修复后必须继续通过全部锚点用例，不得破坏当前已经正确的行为。
- 必须参考历次尝试的拒绝原因，不要重复已经验证失败的修复方向。
- 标准解应保持高效算法定位，允许修正算法、边界处理和复杂度问题。
- 必须严格贴合题意，不得引入题面未给出的假设。
- 保持输入输出格式完全一致，不要添加额外输出。
- 不要依赖非标准库或外部文件。
- 不要静默吞掉错误。
- 修复后代码必须是完整可编译源码，并实现 solve(input_str: str) -> str。""",
            json_contract(
                """
{
  "analysis": "根因分析，说明失败批次暴露的通用问题",
  "fix_plan": "修复计划，说明将如何修改算法或边界处理",
  "code": "修改后的完整 Python 代码字符串，只包含可执行源码，不包含 Markdown"
}
"""
            ),
        ]
    )
