from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from orchestrator import WorkflowConfig, run_workflow
from runtime_config import RuntimeConfigError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AutoProblemGen 端到端总流程")
    parser.add_argument("--workflow-config", required=True, help="总流程配置文件路径")
    parser.add_argument(
        "--input-path",
        help="仅本次运行覆盖 workflow.env 中的 INPUT_PATH，可指向单个 JSON 文件或题目 JSON 目录。",
    )
    parser.add_argument(
        "--skip-previous-failures",
        action="store_true",
        help="跳过历史已跑过但未 verified 且输入 hash 未变化的题，只处理未跑过的题。",
    )
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
    if args.input_path:
        config = replace(config, input_path=Path(args.input_path).resolve())
    validate_config(parser, config)

    summary = run_workflow(config, skip_previous_failures=args.skip_previous_failures)
    print(f"[workflow] status={summary['status']}")
    print(f"[workflow] summary={summary['paths']['summary']}")
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
