from __future__ import annotations

import sys
import unittest
from pathlib import Path

import path_setup  # noqa: F401

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / "总流程"
if str(WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_DIR))

from execution_config import (
    DEFAULT_BRUTEFORCE_MEMORY_LIMIT_MB,
    DEFAULT_BRUTEFORCE_TIMEOUT_SECONDS,
    DEFAULT_CHECKER_MEMORY_LIMIT_MB,
    DEFAULT_CHECKER_TIMEOUT_SECONDS,
    DEFAULT_TEST_INPUT_MEMORY_LIMIT_MB,
    DEFAULT_TEST_INPUT_TIMEOUT_SECONDS,
    ExecutionConfig,
)
from runtime_config import ExecutionLimits


class ExecutionConfigTests(unittest.TestCase):
    def test_defaults_are_safe_when_constructed_directly(self) -> None:
        config = ExecutionConfig()

        self.assertEqual(config.test_input_timeout_seconds, DEFAULT_TEST_INPUT_TIMEOUT_SECONDS)
        self.assertEqual(config.test_input_memory_limit_mb, DEFAULT_TEST_INPUT_MEMORY_LIMIT_MB)
        self.assertEqual(config.bruteforce_timeout_seconds, DEFAULT_BRUTEFORCE_TIMEOUT_SECONDS)
        self.assertEqual(config.bruteforce_memory_limit_mb, DEFAULT_BRUTEFORCE_MEMORY_LIMIT_MB)
        self.assertEqual(config.checker_timeout_seconds, DEFAULT_CHECKER_TIMEOUT_SECONDS)
        self.assertEqual(config.checker_memory_limit_mb, DEFAULT_CHECKER_MEMORY_LIMIT_MB)

    def test_from_runtime_limits_maps_total_workflow_config(self) -> None:
        limits = ExecutionLimits(
            test_input_timeout_seconds=1.5,
            test_input_memory_limit_mb=128,
            bruteforce_timeout_seconds=2.5,
            bruteforce_memory_limit_mb=256,
            checker_timeout_seconds=3.5,
            checker_memory_limit_mb=384,
        )

        config = ExecutionConfig.from_runtime_limits(limits)

        self.assertEqual(config.test_input_timeout_seconds, 1.5)
        self.assertEqual(config.test_input_memory_limit_mb, 128)
        self.assertEqual(config.bruteforce_timeout_seconds, 2.5)
        self.assertEqual(config.bruteforce_memory_limit_mb, 256)
        self.assertEqual(config.checker_timeout_seconds, 3.5)
        self.assertEqual(config.checker_memory_limit_mb, 384)


if __name__ == "__main__":
    unittest.main()
