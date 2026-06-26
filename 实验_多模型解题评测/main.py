from __future__ import annotations

import argparse
from pathlib import Path

from experiment_core import build_manifest, generate_reports, run_experiment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成题质量评测实验")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("build-manifest", help="扫描总流程产物并冻结实验题目清单")
    manifest_parser.add_argument("--workflow-output-root", required=True, type=Path)
    manifest_parser.add_argument("--output", required=True, type=Path)

    run_parser = subparsers.add_parser("run", help="让配置模型解题并执行隐藏测试")
    run_source = run_parser.add_mutually_exclusive_group(required=True)
    run_source.add_argument("--manifest", type=Path)
    run_source.add_argument("--workflow-output-root", type=Path)
    run_parser.add_argument("--models", required=True, type=Path)
    run_parser.add_argument("--output-root", required=True, type=Path)
    run_parser.add_argument("--run-id", required=True)

    report_parser = subparsers.add_parser("report", help="汇总已有评测明细")
    report_parser.add_argument("--run-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build-manifest":
        result = build_manifest(args.workflow_output_root, args.output)
        print(f"[manifest] included={result['manifest']['problem_count']} excluded={result['excluded_count']}")
        print(f"[manifest] output={args.output.resolve()}")
        print(f"[manifest] excluded_output={result['exclusion_path']}")
        return 0
    if args.command == "run":
        result = run_experiment(
            manifest_path=args.manifest,
            workflow_output_root=args.workflow_output_root,
            models_path=args.models,
            output_root=args.output_root,
            run_id=args.run_id,
        )
        print(f"[experiment] run_dir={result['run_dir']}")
        print(
            f"[experiment] completed={result['completed_count']} "
            f"infrastructure_errors={result['infrastructure_error_count']} skipped={result['skipped_count']}"
        )
        return 0 if result["infrastructure_error_count"] == 0 else 2
    summary = generate_reports(args.run_dir)
    print(f"[report] status={summary['status']} output={args.run_dir.resolve()}")
    return 0 if summary["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
