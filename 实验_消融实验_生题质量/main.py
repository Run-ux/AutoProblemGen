from __future__ import annotations

import argparse
from pathlib import Path

from quality_ablation.generation import run_generations
from quality_ablation.judging import run_judging
from quality_ablation.manifest import build_manifest
from quality_ablation.reporting import build_report
from quality_ablation.utils import (
    ALL_CONDITIONS,
    DEFAULT_SUCCESSFUL_ROOT,
    DEFAULT_WORKFLOW_CONFIG,
    EXPERIMENT_ROOT,
    GENERATED_CONDITIONS,
    parse_conditions,
)


DEFAULT_MANIFEST = EXPERIMENT_ROOT / "manifests" / "quality_ablation_manifest.json"
DEFAULT_OUTPUT_ROOT = EXPERIMENT_ROOT / "output"
DEFAULT_RUN_ID = "quality_ablation"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "build-manifest":
        result = build_manifest(
            successful_root=Path(args.successful_root),
            output_path=Path(args.output),
            limit=args.limit,
        )
        print(
            f"manifest written: {result['manifest_path']} "
            f"(eligible={result['eligible_count']}, skipped={result['skipped_count']})"
        )
    elif args.command == "run":
        result = run_generations(
            manifest_path=Path(args.manifest),
            output_root=Path(args.output_root),
            run_id=args.run_id,
            workflow_config_path=Path(args.workflow_config),
            conditions=parse_conditions(args.conditions, default=GENERATED_CONDITIONS),
            limit=args.limit,
            resume=not args.no_resume,
            shard_count=args.shard_count,
            shard_index=args.shard_index,
        )
        print(f"run finished: {result['run_dir']}")
    elif args.command == "judge":
        result = run_judging(
            manifest_path=Path(args.manifest),
            run_dir=_resolve_run_dir(args),
            workflow_config_path=Path(args.workflow_config),
            conditions=parse_conditions(args.conditions, default=ALL_CONDITIONS),
            limit=args.limit,
            resume=not args.no_resume,
            blind_seed=args.blind_seed,
            shard_count=args.shard_count,
            shard_index=args.shard_index,
        )
        print(f"judge finished: {result['scores_path']}")
    elif args.command == "report":
        result = build_report(
            manifest_path=Path(args.manifest),
            run_dir=_resolve_run_dir(args),
            bootstrap_samples=args.bootstrap_samples,
        )
        print(f"report written: {result['report_path']}")
    else:
        parser.error(f"未知命令：{args.command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生题质量消融实验 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("build-manifest", help="扫描 successful_output 并冻结实验样本")
    manifest_parser.add_argument("--successful-root", default=str(DEFAULT_SUCCESSFUL_ROOT), help="successful_output 根目录")
    manifest_parser.add_argument("--output", default=str(DEFAULT_MANIFEST), help="manifest 输出路径")
    manifest_parser.add_argument("--limit", type=int, help="只取前 N 个 eligible 题，用于冒烟测试")

    run_parser = subparsers.add_parser("run", help="运行 no_tuple/no_rules/no_quality_loop 生成")
    add_manifest_arg(run_parser)
    add_run_location_args(run_parser)
    run_parser.add_argument(
        "--workflow-config",
        default=str(DEFAULT_WORKFLOW_CONFIG),
        help="总流程 workflow.env 路径，用于读取 LLM 配置",
    )
    run_parser.add_argument(
        "--conditions",
        action="append",
        help="实验组，可重复传入或用逗号分隔。run 默认只跑 no_tuple,no_rules,no_quality_loop",
    )
    run_parser.add_argument("--limit", type=int, help="只运行前 N 个 manifest 题")
    run_parser.add_argument("--no-resume", action="store_true", help="忽略已有 result.json，强制重跑")
    add_shard_args(run_parser)

    judge_parser = subparsers.add_parser("judge", help="构建盲评队列并调用 LLM judge")
    add_manifest_arg(judge_parser)
    add_run_location_args(judge_parser)
    judge_parser.add_argument(
        "--workflow-config",
        default=str(DEFAULT_WORKFLOW_CONFIG),
        help="总流程 workflow.env 路径，用于读取 LLM 配置",
    )
    judge_parser.add_argument(
        "--conditions",
        action="append",
        help="实验组，可重复传入或用逗号分隔。judge 默认评 full 与三个消融组",
    )
    judge_parser.add_argument("--limit", type=int, help="只评前 N 个 manifest 题")
    judge_parser.add_argument("--no-resume", action="store_true", help="不跳过 scores.jsonl 中已有 blind_id")
    judge_parser.add_argument("--blind-seed", type=int, default=20260624, help="盲评队列打乱种子")
    add_shard_args(judge_parser)

    report_parser = subparsers.add_parser("report", help="汇总分数、失败率和 paired delta")
    add_manifest_arg(report_parser)
    add_run_location_args(report_parser)
    report_parser.add_argument("--bootstrap-samples", type=int, default=2000, help="bootstrap 采样次数")

    return parser


def add_manifest_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="quality_ablation_manifest.json 路径")


def add_run_location_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="实验输出根目录")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID, help="本次实验 run id")
    parser.add_argument("--run-dir", help="已存在的 run 目录；若提供则优先于 output-root/run-id")


def add_shard_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--shard-count", type=int, default=1, help="题目分片总数，默认 1")
    parser.add_argument("--shard-index", type=int, default=0, help="当前分片编号，范围为 0 <= K < shard-count")


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    if getattr(args, "run_dir", None):
        return Path(args.run_dir)
    return Path(args.output_root) / args.run_id


if __name__ == "__main__":
    main()
