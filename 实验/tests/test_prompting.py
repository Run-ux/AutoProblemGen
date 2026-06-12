from __future__ import annotations

import unittest

import path_setup  # noqa: F401
from experiment_core.prompting import CodeResponseError, build_prompts, extract_and_validate_code
from helpers import generation_artifact


class PromptingTests(unittest.TestCase):
    def test_prompt_only_contains_problem_statement_fields(self) -> None:
        artifact = generation_artifact()
        system_prompt, user_prompt = build_prompts(artifact["generated_problem"])

        combined = system_prompt + user_prompt
        self.assertIn("测试题", combined)
        self.assertNotIn("rule_a", combined)
        self.assertNotIn("changed_axes", combined)
        self.assertNotIn("standard_solution", combined)

    def test_extracts_single_python_block(self) -> None:
        code = extract_and_validate_code("```python\ndef solve(input_str):\n    return 'ok'\n```")
        self.assertIn("def solve", code)

    def test_accepts_plain_code(self) -> None:
        code = extract_and_validate_code("def solve(input_str):\n    return input_str")
        self.assertTrue(code.startswith("def solve"))

    def test_rejects_multiple_blocks(self) -> None:
        with self.assertRaisesRegex(CodeResponseError, "多个代码块"):
            extract_and_validate_code("```python\ndef solve(x): return x\n```\n```python\nprint(1)\n```")

    def test_rejects_syntax_error_and_missing_solve(self) -> None:
        with self.assertRaises(CodeResponseError) as syntax_context:
            extract_and_validate_code("def solve(:\n    pass")
        self.assertEqual(syntax_context.exception.classification, "syntax_error")
        with self.assertRaises(CodeResponseError) as interface_context:
            extract_and_validate_code("def main():\n    return 'x'")
        self.assertEqual(interface_context.exception.classification, "interface_error")


if __name__ == "__main__":
    unittest.main()
