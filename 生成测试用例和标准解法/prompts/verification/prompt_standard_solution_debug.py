from __future__ import annotations

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
    failing_input: str,
    expected_output: str,
    actual_output: str,
    error_report: str,
) -> str:
    return "\n\n".join(
        [
            generated_problem_section(artifact),
            schema_section(artifact),
            "# 初始标准解完整代码",
            initial_code,
            "# 当前迭代标准解完整代码",
            current_code,
            "# 触发失败的测试输入",
            failing_input,
            "# 小规模真值输出",
            expected_output,
            "# 当前标准解实际输出",
            actual_output,
            "# 完整错误信息或判定信息",
            error_report,
            """# 修复要求
- 优先定位导致当前失败用例不通过的根本原因，并做通用修复。
- 标准解应保持高效算法定位，允许修正算法、边界处理和复杂度问题。
- 必须严格贴合题意，不得引入题面未给出的假设。
- 保持输入输出格式完全一致，不要添加额外输出。
- 不要依赖非标准库或外部文件。
- 不要静默吞掉错误。
- 修复后代码必须是完整可编译源码，并实现 solve(input_str: str) -> str。""",
            json_contract(
                """
{
  "code": "修改后的完整 Python 代码字符串，只包含可执行源码，不包含 Markdown"
}
"""
            ),
        ]
    )
