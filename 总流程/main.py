from __future__ import annotations

import argparse

from orchestrator import WorkflowConfig, run_workflow
from runtime_config import RuntimeConfigError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AutoProblemGen 端到端总流程")
    parser.add_argument("--workflow-config", required=True, help="总流程配置文件路径")
    return parser


def validate_config(parser: argparse.ArgumentParser, config: WorkflowConfig) -> None:
    if not config.input_path.exists():
        parser.error(f"INPUT_PATH 不存在：{config.input_path}")
    if config.quality_iterations not in {1, 2, 3}:
        parser.error("QUALITY_ITERATIONS 必须是 1、2 或 3，不能关闭质量评价。")
    if config.quality_full_score_max_iterations <= 0:
        parser.error("QUALITY_FULL_SCORE_MAX_ITERATIONS 必须是正整数。")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = WorkflowConfig.from_file(args.workflow_config)
    except RuntimeConfigError as exc:
        parser.error(str(exc))
    validate_config(parser, config)

    summary = run_workflow(config)
    print(f"[workflow] status={summary['status']}")
    print(f"[workflow] summary={summary['paths']['summary']}")
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
