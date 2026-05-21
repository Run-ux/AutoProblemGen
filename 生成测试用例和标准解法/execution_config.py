from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_TEST_INPUT_TIMEOUT_SECONDS = 5.0
DEFAULT_TEST_INPUT_MEMORY_LIMIT_MB = 512
DEFAULT_BRUTEFORCE_TIMEOUT_SECONDS = 5.0
DEFAULT_BRUTEFORCE_MEMORY_LIMIT_MB = 512
DEFAULT_CHECKER_TIMEOUT_SECONDS = 5.0
DEFAULT_CHECKER_MEMORY_LIMIT_MB = 512


@dataclass(frozen=True)
class ExecutionConfig:
    """本地执行生成代码、暴力解法和 checker 时使用的资源限制。"""

    test_input_timeout_seconds: float = DEFAULT_TEST_INPUT_TIMEOUT_SECONDS
    test_input_memory_limit_mb: int = DEFAULT_TEST_INPUT_MEMORY_LIMIT_MB
    bruteforce_timeout_seconds: float = DEFAULT_BRUTEFORCE_TIMEOUT_SECONDS
    bruteforce_memory_limit_mb: int = DEFAULT_BRUTEFORCE_MEMORY_LIMIT_MB
    checker_timeout_seconds: float = DEFAULT_CHECKER_TIMEOUT_SECONDS
    checker_memory_limit_mb: int = DEFAULT_CHECKER_MEMORY_LIMIT_MB

    @classmethod
    def from_runtime_limits(cls, limits: Any) -> "ExecutionConfig":
        return cls(
            test_input_timeout_seconds=float(limits.test_input_timeout_seconds),
            test_input_memory_limit_mb=int(limits.test_input_memory_limit_mb),
            bruteforce_timeout_seconds=float(limits.bruteforce_timeout_seconds),
            bruteforce_memory_limit_mb=int(limits.bruteforce_memory_limit_mb),
            checker_timeout_seconds=float(limits.checker_timeout_seconds),
            checker_memory_limit_mb=int(limits.checker_memory_limit_mb),
        )
