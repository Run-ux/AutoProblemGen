from __future__ import annotations

import argparse
from pathlib import Path

from ablation_core import build_manifest, generate_report, run_ablation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TestCase-Eval 外部提交消融实验")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("build-manifest", help="抽取 TestCase-Eval 题目与提交清单")
    manifest_parser.add_argument("--output", required=True, type=Path)
    manifest_parser.add_argument("--sample-size", type=int, default=80)
    manifest_parser.add_argument("--seed", type=int, default=20260617)
    manifest_parser.add_argument("--min-right", type=int, default=3)
    manifest_parser.add_argument("--min-wrong", type=int, default=50)
    manifest_parser.add_argument("--eval-right-per-problem", type=int, default=3)
    manifest_parser.add_argument("--eval-wrong-per-problem", type=int, default=50)

    run_parser = subparsers.add_parser("run", help="运行四元组抽取、测试生成和真实提交评测")
    run_parser.add_argument("--manifest", required=True, type=Path)
    run_parser.add_argument("--output-root", required=True, type=Path)
    run_parser.add_argument("--run-id", required=True)
    run_parser.add_argument("--workflow-config", type=Path, default=Path(r"D:\AutoProblemGen\总流程\workflow.env"))
    run_parser.add_argument("--limit", type=int, default=None, help="仅跑前 N 题，便于冒烟测试")
    run_parser.add_argument("--no-resume", action="store_true", help="忽略已有每题缓存并重新运行")

    report_parser = subparsers.add_parser("report", help="汇总已有运行结果")
    report_parser.add_argument("--run-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build-manifest":
        manifest = build_manifest(
            output_path=args.output,
            sample_size=args.sample_size,
            seed=args.seed,
            min_right=args.min_right,
            min_wrong=args.min_wrong,
            eval_right_per_problem=args.eval_right_per_problem,
            eval_wrong_per_problem=args.eval_wrong_per_problem,
        )
        print(f"[manifest] problems={manifest['problem_count']} output={args.output.resolve()}")
        return 0
    if args.command == "run":
        result = run_ablation(
            manifest_path=args.manifest,
            output_root=args.output_root,
            run_id=args.run_id,
            workflow_config_path=args.workflow_config,
            limit=args.limit,
            resume=not args.no_resume,
        )
        print(f"[run] run_dir={result['run_dir']}")
        print(f"[run] completed={result['completed_count']} failed={result['failed_count']}")
        return 0 if result["failed_count"] == 0 else 2
    summary = generate_report(args.run_dir)
    print(f"[report] status={summary['status']} completed={summary['completed_problem_count']}")
    return 0 if summary["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
