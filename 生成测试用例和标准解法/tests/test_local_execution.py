from __future__ import annotations

import importlib.util
import unittest

import path_setup  # noqa: F401
from local_execution import (
    EXECUTION_ERROR,
    EXECUTION_MEMORY_LIMIT,
    EXECUTION_OK,
    EXECUTION_TIMEOUT,
    run_python_function,
)


class LocalExecutionTests(unittest.TestCase):
    def test_run_python_function_returns_value(self) -> None:
        result = run_python_function(
            "def solve(input_str):\n    return input_str.strip() + '!'",
            "solve",
            ["ok"],
            timeout_seconds=2,
            memory_limit_mb=512,
        )

        self.assertEqual(result.status, EXECUTION_OK)
        self.assertEqual(result.return_value, "ok!")

    def test_run_python_function_accepts_non_ascii_code_payload(self) -> None:
        result = run_python_function(
            "def solve(input_str):\n    # 中文注释不能破坏子进程编码\n    return '答案:' + input_str.strip()",
            "solve",
            ["通过"],
            timeout_seconds=2,
            memory_limit_mb=512,
        )

        self.assertEqual(result.status, EXECUTION_OK)
        self.assertEqual(result.return_value, "答案:通过")

    def test_run_python_function_captures_runtime_error(self) -> None:
        result = run_python_function(
            "def solve(input_str):\n    raise ValueError('bad input')",
            "solve",
            ["x"],
            timeout_seconds=2,
            memory_limit_mb=512,
        )

        self.assertEqual(result.status, EXECUTION_ERROR)
        self.assertEqual(result.phase, "runtime")
        self.assertEqual(result.error_type, "ValueError")
        self.assertIn("bad input", result.error_message)

    def test_run_python_function_captures_timeout(self) -> None:
        result = run_python_function(
            "import time\n\ndef solve(input_str):\n    time.sleep(2)\n    return 'x'",
            "solve",
            [""],
            timeout_seconds=0.2,
            memory_limit_mb=512,
        )

        self.assertEqual(result.status, EXECUTION_TIMEOUT)
        self.assertEqual(result.error_type, "TimeoutExpired")

    def test_run_python_function_captures_memory_limit(self) -> None:
        result = run_python_function(
            "import time\n\ndef solve(input_str):\n    time.sleep(2)\n    return 'x'",
            "solve",
            [""],
            timeout_seconds=5,
            memory_limit_mb=1,
        )

        self.assertEqual(result.status, EXECUTION_MEMORY_LIMIT)
        self.assertEqual(result.error_type, "MemoryLimitExceeded")

    def test_run_python_function_strips_lone_surrogates_before_exec(self) -> None:
        result = run_python_function(
            "def solve(input_str):\n    marker = '\udcae'\n    return 'ok' + marker",
            "solve",
            [""],
            timeout_seconds=2,
            memory_limit_mb=512,
        )

        self.assertEqual(result.status, EXECUTION_OK)
        self.assertEqual(result.return_value, "ok")

    @unittest.skipUnless(importlib.util.find_spec("cyaron"), "cyaron 未安装")
    def test_run_python_function_allows_cyaron_and_shuffle_compat(self) -> None:
        result = run_python_function(
            "import cyaron as cy\n\ndef solve(input_str):\n    values = [3, 1, 2]\n    cy.shuffle(values)\n    return ' '.join(map(str, sorted(values)))",
            "solve",
            [""],
            timeout_seconds=2,
            memory_limit_mb=512,
        )

        self.assertEqual(result.status, EXECUTION_OK)
        self.assertEqual(result.return_value, "1 2 3")


if __name__ == "__main__":
    unittest.main()
