from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"


def setup_logging() -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
    return logging.getLogger(__name__)


def collect_problem_ids(directory: Path) -> set[str]:
    return {path.stem for path in directory.glob("*.json")}


def clean_failures(output_dir: Path, apply: bool, logger: logging.Logger) -> dict[str, int]:
    failure_dir = output_dir / "_failures"
    if not output_dir.exists():
        raise FileNotFoundError(f"输出目录不存在: {output_dir}")
    if not failure_dir.exists():
        raise FileNotFoundError(f"失败目录不存在: {failure_dir}")

    success_ids = collect_problem_ids(output_dir)
    failure_files = sorted(failure_dir.glob("*.json"))

    duplicates = [path for path in failure_files if path.stem in success_ids]
    remaining = len(failure_files) - len(duplicates)

    logger.info("成功文件数: %d", len(success_ids))
    logger.info("失败文件数: %d", len(failure_files))
    logger.info("重复失败文件数: %d", len(duplicates))
    logger.info("清理后保留失败文件数: %d", remaining)

    if apply:
        for path in duplicates:
            path.unlink()
        logger.info("已删除 %d 个重复失败文件", len(duplicates))
    else:
        logger.info("当前为 dry-run，未删除任何文件")

    return {
        "success_count": len(success_ids),
        "failure_count": len(failure_files),
        "duplicate_failure_count": len(duplicates),
        "remaining_failure_count": remaining,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="清理已成功重跑但仍残留在 _failures 中的失败记录")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="带有 _failures 子目录的输出目录，例如 finiteness_verification/output/phase1/voted_with_transform",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行删除；不传时仅做统计预览",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logger = setup_logging()
    clean_failures(output_dir=Path(args.output_dir), apply=args.apply, logger=logger)


if __name__ == "__main__":
    main()
