from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = PROJECT_ROOT / "总流程"
VERIFICATION_DIR = PROJECT_ROOT / "生成测试用例和标准解法"
TUPLE_DIR = PROJECT_ROOT / "四元组抽取"

for path in (WORKFLOW_DIR, VERIFICATION_DIR, TUPLE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from orchestrator import WorkflowConfig  # noqa: E402
from execution_config import ExecutionConfig  # noqa: E402
from llm_config import LLMConfig  # noqa: E402


DEFAULT_WORKFLOW_CONFIG = WORKFLOW_DIR / "workflow.env"


def load_runtime_config(workflow_config_path: Path | None = None) -> dict[str, Any]:
    workflow_path = (workflow_config_path or DEFAULT_WORKFLOW_CONFIG).resolve()
    workflow_config = WorkflowConfig.from_file(workflow_path)
    return {
        "workflow_config": workflow_config,
        "generation_llm": workflow_config.generation_llm,
        "llm_config": LLMConfig.from_endpoint(workflow_config.generation_llm).with_max_prompt_chars(
            workflow_config.context_limits.max_llm_prompt_chars
        ),
        "execution_config": ExecutionConfig.from_runtime_limits(workflow_config.execution_limits),
        "context_limits": workflow_config.context_limits,
    }
