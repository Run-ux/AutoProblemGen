from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from runtime_config import RUNTIME_GENERATION_LLM_ENV, execution_limits_from_runtime_env


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_MODULE_DIR = PROJECT_ROOT / "生成测试用例和标准解法"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="总流程验证阶段子进程入口")
    parser.add_argument("--artifact", required=True, help="生成题面的 artifact JSON 路径")
    parser.add_argument("--output", required=True, help="验证结果 JSON 输出路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    artifact_path = Path(args.artifact)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        sys.path.insert(0, str(ARTIFACT_MODULE_DIR))
        from execution_config import ExecutionConfig
        from generation_pipeline import generate_verified_artifacts
        from llm_config import LLMConfig

        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        llm_config = LLMConfig.from_runtime_env(RUNTIME_GENERATION_LLM_ENV)
        execution_config = ExecutionConfig.from_runtime_limits(execution_limits_from_runtime_env())
        result = generate_verified_artifacts(artifact, llm_config, execution_config=execution_config)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] verified artifacts saved to: {output_path}")
        return 0
    except Exception as exc:
        error_payload = {
            "status": "failed",
            "artifact_path": str(artifact_path),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        output_path.write_text(json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ERROR] verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
