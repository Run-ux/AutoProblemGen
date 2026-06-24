"""
批量题目增强处理脚本
支持批量处理 successful_output 文件夹中的题目，并输出到 other_methods 目录
"""

import os
import sys
import json
import glob
import logging
import multiprocessing
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from augmenter import ProblemAugmenter, Problem


def chunk_problem_folders(problem_folders: List[str], batch_size: int) -> List[List[str]]:
    """按固定大小切分题目文件夹，便于单命令并行处理。"""
    return [
        problem_folders[index:index + batch_size]
        for index in range(0, len(problem_folders), batch_size)
    ]


def setup_worker_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """创建子进程专用 logger，避免多进程重复添加 handler。"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def process_problem_folder(problem_folder: str,
                           use_llm: bool,
                           llm_transformation: str,
                           max_tokens: Optional[int],
                           transform_options: Dict[str, bool],
                           logger: logging.Logger) -> Dict[str, Any]:
    """处理单个题目文件夹，输出 other_methods/unicode.json。"""
    folder_name = os.path.basename(problem_folder)
    logger.info(f"处理题目: {folder_name}")

    original_input_dir = os.path.join(problem_folder, "original_input")
    json_files = sorted(glob.glob(os.path.join(original_input_dir, "*.json")))

    if not json_files:
        logger.warning("  没有找到 original_input JSON 文件")
        return {
            "folder": folder_name,
            "status": "failed",
            "error": "没有找到 original_input JSON 文件"
        }

    seed_file = json_files[0]
    other_methods_dir = os.path.join(problem_folder, "other_methods")
    os.makedirs(other_methods_dir, exist_ok=True)
    output_path = os.path.join(other_methods_dir, "unicode.json")

    logger.info(f"  种子文件: {os.path.basename(seed_file)}")
    logger.info(f"  输出路径: {output_path}")

    try:
        with open(seed_file, 'r', encoding='utf-8') as f:
            seed_data = json.load(f)

        seed = Problem.from_dict(seed_data)
        augmenter = ProblemAugmenter(seed, max_tokens=max_tokens)
        augmented = augmenter.augment(
            use_llm=use_llm,
            llm_transformation=llm_transformation,
            **transform_options
        )

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(augmented, f, ensure_ascii=False, indent=2)

        title = augmented.get('title', 'Generated Problem')
        logger.info(f"  [OK] 成功生成: {title}")
        return {
            "folder": folder_name,
            "seed_file": os.path.basename(seed_file),
            "output": output_path,
            "status": "success",
            "title": title,
            "transformations": augmented.get('augmentation_history', [])
        }
    except Exception as e:
        logger.error(f"  [ERROR] 处理失败: {str(e)}")
        return {
            "folder": folder_name,
            "status": "failed",
            "error": str(e)
        }


def process_batch(problem_folders: List[str],
                  input_base_dir: str,
                  use_llm: bool,
                  llm_transformation: str,
                  max_tokens: Optional[int],
                  transform_options: Dict[str, bool],
                  batch_num: int) -> Dict[str, Any]:
    """处理一批题目文件夹，并写出批次统计。"""
    log_file = os.path.join(input_base_dir, f"unicode_batch_{batch_num}_log.txt")
    logger = setup_worker_logger(f"BatchAugmenter-{batch_num}", log_file)
    logger.info(f"批次 {batch_num} 开始，题目数: {len(problem_folders)}")

    stats = {
        "batch": batch_num,
        "total": len(problem_folders),
        "processed": 0,
        "failed": 0,
        "files": [],
        "start_time": datetime.now().isoformat()
    }

    for problem_folder in problem_folders:
        detail = process_problem_folder(
            problem_folder=problem_folder,
            use_llm=use_llm,
            llm_transformation=llm_transformation,
            max_tokens=max_tokens,
            transform_options=transform_options,
            logger=logger
        )
        stats["files"].append(detail)
        if detail["status"] == "success":
            stats["processed"] += 1
        else:
            stats["failed"] += 1

    stats["end_time"] = datetime.now().isoformat()
    stats["duration"] = str(datetime.fromisoformat(stats["end_time"]) - datetime.fromisoformat(stats["start_time"]))

    stats_file = os.path.join(input_base_dir, f"unicode_batch_{batch_num}_stats.json")
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    logger.info(f"批次 {batch_num} 完成: {stats['processed']}/{stats['total']}")
    return stats


class BatchAugmenter:
    """批量增强处理器"""
    
    def __init__(self, 
                 input_base_dir: str = "input",
                 use_llm: bool = False,
                 llm_transformation: str = "all",
                 max_tokens: Optional[int] = None):
        """
        初始化批量增强器
        
        Args:
            input_base_dir: 输入基础目录（successful_output）
            use_llm: 是否使用 LLM 增强
            llm_transformation: LLM 变换类型
        """
        self.input_base_dir = Path(input_base_dir)
        self.use_llm = use_llm
        self.llm_transformation = llm_transformation
        self.max_tokens = max_tokens
        
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger("BatchAugmenter")
        logger.setLevel(logging.INFO)
        
        logger.handlers.clear()
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        return logger
    
    def process_problem_folders(self, 
                               narrative: bool = True,
                               rule: bool = True,
                               efficiency: bool = True,
                               sequential: bool = True,
                               fusion: bool = True,
                               batch_size: int = 5,
                               processes: int = 5) -> dict:
        """
        批量处理 successful_output 下的所有题目文件夹
        
        Args:
            narrative: 应用叙事扰动
            rule: 应用规则修改
            efficiency: 应用效率缩放
            sequential: 应用顺序组合
            fusion: 应用概念融合
            
        Returns:
            处理结果统计
        """
        if batch_size <= 0:
            raise ValueError("batch_size 必须是正整数")
        if processes <= 0:
            raise ValueError("processes 必须是正整数")

        problem_folders = sorted(
            f for f in glob.glob(os.path.join(self.input_base_dir, "*"))
            if os.path.isdir(f) and not os.path.basename(f).startswith('_')
        )
        
        if not problem_folders:
            self.logger.error(f"在 {self.input_base_dir} 中没有找到题目文件夹")
            return {"success": False, "error": "没有找到题目文件夹"}
        
        self.logger.info(f"找到 {len(problem_folders)} 个题目文件夹")
        batches = chunk_problem_folders(problem_folders, batch_size)
        pool_processes = min(processes, len(batches)) if batches else 0
        self.logger.info(f"批次大小: {batch_size}")
        self.logger.info(f"批次数量: {len(batches)}")
        self.logger.info(f"并行进程数: {pool_processes}")
        self.logger.info(f"使用 LLM: {self.use_llm}")
        if self.use_llm:
            self.logger.info(f"LLM 变换类型: {self.llm_transformation}")
            self.logger.info(f"Max tokens: {self.max_tokens or os.getenv('MAX_TOKENS', 16000)}")
        
        transform_options = {
            "narrative": narrative,
            "rule": rule,
            "efficiency": efficiency,
            "sequential": sequential,
            "fusion": fusion
        }

        if pool_processes == 1:
            batch_results = [
                process_batch(
                    batch, str(self.input_base_dir), self.use_llm,
                    self.llm_transformation, self.max_tokens,
                    transform_options, index
                )
                for index, batch in enumerate(batches, 1)
            ]
        else:
            with multiprocessing.Pool(processes=pool_processes) as pool:
                async_results = [
                    pool.apply_async(process_batch, (
                        batch, str(self.input_base_dir), self.use_llm,
                        self.llm_transformation, self.max_tokens,
                        transform_options, index
                    ))
                    for index, batch in enumerate(batches, 1)
                ]
                batch_results = [result.get() for result in async_results]

        stats = {
            "success": True,
            "total": sum(item["total"] for item in batch_results),
            "processed": sum(item["processed"] for item in batch_results),
            "failed": sum(item["failed"] for item in batch_results),
            "batch_size": batch_size,
            "processes": pool_processes,
            "files": [detail for item in batch_results for detail in item["files"]],
            "batches": batch_results
        }
        
        self.logger.info("\n" + "=" * 60)
        self.logger.info("批量处理完成")
        self.logger.info(f"成功: {stats['processed']} 个")
        self.logger.info(f"失败: {stats['failed']} 个")
        self.logger.info("=" * 60)

        stats_file = os.path.join(self.input_base_dir, "unicode_parallel_stats.json")
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        self.logger.info(f"统计信息已保存到: {stats_file}")
        
        return stats


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="批量题目增强处理工具")
    parser.add_argument("--input", required=True, help="输入基础目录（successful_output）")
    parser.add_argument("--use-llm", action="store_true", help="使用 LLM 增强")
    parser.add_argument("--llm-transformation", default="all", 
                       choices=["narrative", "rule", "efficiency", "sequential", "fusion", "all"],
                       help="LLM 变换类型（默认: all）")
    parser.add_argument("--no-narrative", action="store_true", help="不应用叙事扰动")
    parser.add_argument("--no-rule", action="store_true", help="不应用规则修改")
    parser.add_argument("--no-efficiency", action="store_true", help="不应用效率缩放")
    parser.add_argument("--no-sequential", action="store_true", help="不应用顺序组合")
    parser.add_argument("--no-fusion", action="store_true", help="不应用概念融合")
    parser.add_argument("--batch-size", type=int, default=5, help="每个批次处理的题目数量（默认: 5）")
    parser.add_argument("--processes", type=int, default=5, help="并行进程数（默认: 5）")
    parser.add_argument("--max-tokens", type=int, help="LLM 生成的最大 completion token 数")
    
    args = parser.parse_args()
    
    augmenter = BatchAugmenter(
        input_base_dir=args.input,
        use_llm=args.use_llm,
        llm_transformation=args.llm_transformation,
        max_tokens=args.max_tokens
    )
    
    stats = augmenter.process_problem_folders(
        narrative=not args.no_narrative,
        rule=not args.no_rule,
        efficiency=not args.no_efficiency,
        sequential=not args.no_sequential,
        fusion=not args.no_fusion,
        batch_size=args.batch_size,
        processes=args.processes
    )
    
    sys.exit(0 if stats["success"] and stats["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
