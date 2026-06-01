from __future__ import annotations

from .._common import generated_problem_section, json_contract, schema_section


def build_system_prompt() -> str:
    return (
        "你是算法竞赛测试输入生成器调试助手。你的任务是修复测试输入生成代码和校验代码，"
        "使其稳定生成符合题意的合法输入。最终只输出单个 JSON 对象。"
    )


def build_user_prompt(
    artifact: dict,
    *,
    source: str,
    constraint_analysis: str,
    generate_test_input_code: str,
    validate_test_input_code: str,
    failure_stage: str,
    error_report: str,
    failing_input: str = "",
) -> str:
    sections = [
        generated_problem_section(artifact),
        schema_section(artifact),
        "# 当前测试输入来源",
        source,
        "# 当前约束分析",
        constraint_analysis,
        "# 当前 generate_test_input_code",
        generate_test_input_code,
        "# 当前 validate_test_input_code",
        validate_test_input_code,
        "# 失败阶段",
        failure_stage,
        "# 错误报告",
        error_report,
    ]
    if failing_input:
        sections.extend(["# 触发失败的输入", failing_input])
    sections.extend(
        [
            """# 修复要求
- 重新生成整组 constraint_analysis、generate_test_input_code、validate_test_input_code。
- generate_test_input() 必须不接收参数，并返回一条非空输入字符串；不要返回列表、元组、None 或调试对象。
- validate_test_input(input_string) 必须校验题面格式、数据范围和结构关系；合法返回 True，非法返回 False。
- validate_test_input(input_string) 必须能处理空输入、格式错误、类型错误和越界数据，不应抛出未处理异常。
- 修复 validate 误拒时，要以题面和 schema 为准，不要为了放过失败输入而放宽必要约束。
- 使用 cyaron==0.7.0；生成代码必须包含 import cyaron as cy。
- 不支持 cy.Integer()；应使用 cy.randint。
- 使用 cy.String.random，不要使用 cy.String。
- 若需要打乱列表，使用标准库 random.shuffle；不要使用 cy.shuffle 或 cyaron.shuffle。
- 不要依赖非标准库、外部文件、全局输入或网络。
- 不要硬编码样例或失败输入。""",
            json_contract(
                """
{
  "constraint_analysis": "按题目描述写明修复后的输入约束。",
  "generate_test_input_code": "完整 Python 代码字符串，包含 import cyaron as cy 和 def generate_test_input(): ...",
  "validate_test_input_code": "完整 Python 代码字符串，包含 def validate_test_input(input_string): ..."
}
"""
            ),
        ]
    )
    return "\n\n".join(sections)
