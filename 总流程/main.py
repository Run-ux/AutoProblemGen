from __future__ import annotations

import argparse
import sys
from pathlib import Path

from orchestrator import DEFAULT_OUTPUT_ROOT, WorkflowConfig, run_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AutoProblemGen 端到端总流程")
    parser.add_argument("--input", required=True, help="原始单题 schema JSON 文件，或包含多个 schema JSON 的目录")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="总流程输出根目录")
    parser.add_argument("--run-id", help="本次运行 ID；默认使用当前时间戳")
    parser.add_argument("--variants", type=int, default=1, help="每题生成的变体数量")
    parser.add_argument("--theme", help="传给生成题面的主题 ID")
    parser.add_argument(
        "--quality-iterations",
        type=int,
        default=3,
        help="题面质量闭环轮数，必须为 1、2 或 3",
    )
    parser.add_argument(
        "--quality-full-score-max-iterations",
        type=int,
        default=10,
        help="pass 后五维质量未满分时的题面打磨追加轮数上限",
    )
    parser.add_argument("--embedding-threshold", type=float, default=0.85, help="四元组归一化 embedding 相似度阈值")
    parser.add_argument(
        "--verification-timeout-seconds",
        type=float,
        default=3600.0,
        help="单个题面 artifact 的测试/标准解验证超时时间",
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help=argparse.SUPPRESS,
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"--input 不存在：{input_path}")
    if args.variants <= 0:
        parser.error("--variants 必须是正整数。")
    if args.quality_iterations not in {1, 2, 3}:
        parser.error("--quality-iterations 必须是 1、2 或 3，不能关闭质量评价。")
    if args.quality_full_score_max_iterations <= 0:
        parser.error("--quality-full-score-max-iterations 必须是正整数。")
    if not (0.0 <= args.embedding_threshold <= 1.0):
        parser.error("--embedding-threshold 必须位于 [0, 1]。")
    if args.verification_timeout_seconds <= 0:
        parser.error("--verification-timeout-seconds 必须为正数。")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)

    config = WorkflowConfig(
        input_path=Path(args.input),
        output_root=Path(args.output_root),
        run_id=args.run_id,
        variants=args.variants,
        theme=args.theme,
        quality_iterations=args.quality_iterations,
        quality_full_score_max_iterations=args.quality_full_score_max_iterations,
        embedding_threshold=args.embedding_threshold,
        verification_timeout_seconds=args.verification_timeout_seconds,
        python_executable=args.python_executable,
    )
    summary = run_workflow(config)
    print(f"[workflow] status={summary['status']}")
    print(f"[workflow] summary={summary['paths']['summary']}")
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

