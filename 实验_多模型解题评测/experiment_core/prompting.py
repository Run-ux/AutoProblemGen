from __future__ import annotations

import ast
import json
import re
from typing import Any


CODE_FENCE_RE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)


class CodeResponseError(ValueError):
    def __init__(self, message: str, *, classification: str) -> None:
        super().__init__(message)
        self.classification = classification


def build_prompts(generated_problem: dict[str, Any]) -> tuple[str, str]:
    allowed_fields = (
        "title",
        "description",
        "input_format",
        "output_format",
        "constraints",
        "samples",
        "notes",
    )
    problem_payload = {field: generated_problem.get(field) for field in allowed_fields}
    system_prompt = (
        "你是一名严谨的算法竞赛 Python 选手。请独立解决给定题目，"
        "优先保证正确性、边界条件和复杂度满足约束。"
        "你只能依据题面信息作答，不得修改题意，不得依赖网络、文件系统、第三方库、随机性或隐藏状态。"
        "最终答案必须是可执行的标准 Python 代码。"
    )
    user_prompt = "\n\n".join(
        [
            "# 题目",
            json.dumps(problem_payload, ensure_ascii=False, indent=2),
            "# 输出要求",
            "只返回一份 Python 代码，可以放在单个 ```python 代码块中，也可以直接返回纯代码；"
            "不要返回解释、题解、复杂度说明或第二个代码块。",
            "代码必须定义顶层函数 solve(input_str: str) -> str：\n"
            "- input_str 是完整标准输入字符串；\n"
            "- 返回值必须是完整标准输出字符串；\n"
            "- 不要从真实 stdin 读取，不要向 stdout 打印；\n"
            "- 不要依赖 if __name__ == \"__main__\" 才能工作；\n"
            "- 可以使用 Python 标准库，但不得使用第三方库。",
            "请在生成代码前于内部完成以下检查，但不要把检查过程输出：\n"
            "1. 理解题目目标、输入输出格式、约束、样例和 notes 中的细节；\n"
            "2. 选择能通过最大约束的算法，并核对时间和空间复杂度；\n"
            "3. 特别检查空/最小规模、最大规模、重复值、边界值、精度/取模/排序稳定性等题面相关边界；\n"
            "4. 如逻辑较复杂，请拆分为含义清晰的辅助函数，变量命名应反映用途；\n"
            "5. 最终自检导入、解析输入、输出格式、换行和返回类型。",
        ]
    )
    return system_prompt, user_prompt


def extract_and_validate_code(response_text: str) -> str:
    matches = CODE_FENCE_RE.findall(response_text)
    if len(matches) > 1:
        raise CodeResponseError("响应包含多个代码块，无法唯一确定候选程序。", classification="response_parse_error")
    if len(matches) == 1:
        language, code = matches[0]
        language = language.strip().lower()
        if language not in {"", "python", "py", "python3"}:
            raise CodeResponseError(f"不支持的代码块语言: {language}", classification="response_parse_error")
    else:
        code = response_text.strip()
    if not code.strip():
        raise CodeResponseError("响应中没有代码。", classification="response_parse_error")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise CodeResponseError(f"Python 语法错误: {exc}", classification="syntax_error") from exc
    solve_nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "solve"]
    if not solve_nodes:
        raise CodeResponseError("候选代码缺少顶层 solve 函数。", classification="interface_error")
    if isinstance(solve_nodes[0], ast.AsyncFunctionDef):
        raise CodeResponseError("solve 不能是异步函数。", classification="interface_error")
    positional_count = len(solve_nodes[0].args.posonlyargs) + len(solve_nodes[0].args.args)
    if positional_count < 1 and solve_nodes[0].args.vararg is None:
        raise CodeResponseError("solve 必须接收 input_str 参数。", classification="interface_error")
    return code.strip() + "\n"
