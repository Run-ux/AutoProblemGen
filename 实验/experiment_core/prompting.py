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
        "你是一名算法竞赛选手。请独立解决给定题目，并返回可执行的标准 Python 代码。"
        "不得修改题意，不得依赖网络、文件系统、第三方库或隐藏状态。"
    )
    user_prompt = "\n\n".join(
        [
            "# 题目",
            json.dumps(problem_payload, ensure_ascii=False, indent=2),
            "# 输出要求",
            "只返回一份 Python 代码。代码必须定义 solve(input_str: str) -> str；"
            "函数接收完整标准输入字符串并返回完整标准输出字符串。"
            "可以使用单个 ```python 代码块，也可以直接返回纯代码；不要返回第二个代码块。",
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
