from __future__ import annotations

import unittest

import path_setup  # noqa: F401
from llm_client import LLMCallError, OpenAIChatLLMClient
from llm_config import LLMConfig


class LLMClientBudgetTests(unittest.TestCase):
    def test_prompt_budget_fails_before_api_call(self) -> None:
        client = OpenAIChatLLMClient.__new__(OpenAIChatLLMClient)
        client.config = LLMConfig(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test",
            max_prompt_chars=10,
        )

        with self.assertRaisesRegex(LLMCallError, "超过本地预算"):
            client._ensure_prompt_budget(
                call_id="unit-call",
                task_name="huge_prompt",
                system_prompt="12345",
                user_prompt="678901",
            )


if __name__ == "__main__":
    unittest.main()
