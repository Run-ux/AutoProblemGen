"""
批量题目增强处理脚本
支持批量处理 successful_output 文件夹中的题目，并输出到 other_methods 目录
"""

import os
import sys
import json
import glob
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from augmenter import ProblemAugmenter, Problem


class BatchAugmenter:
    """批量增强处理器"""
    
    def __init__(self, 
                 input_base_dir: str = "input",
                 use_llm: bool = False,
                 llm_transformation: str = "all"):
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
                               fusion: bool = True) -> dict:
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
        problem_folders = [f for f in glob.glob(os.path.join(self.input_base_dir, "*")) 
                           if os.path.isdir(f) and not os.path.basename(f).startswith('_')]
        
        if not problem_folders:
            self.logger.error(f"在 {self.input_base_dir} 中没有找到题目文件夹")
            return {"success": False, "error": "没有找到题目文件夹"}
        
        self.logger.info(f"找到 {len(problem_folders)} 个题目文件夹")
        self.logger.info(f"使用 LLM: {self.use_llm}")
        if self.use_llm:
            self.logger.info(f"LLM 变换类型: {self.llm_transformation}")
        
        stats = {
            "success": True,
            "processed": 0,
            "failed": 0,
            "files": []
        }
        
        for problem_folder in problem_folders:
            folder_name = os.path.basename(problem_folder)
            self.logger.info(f"\n处理题目: {folder_name}")
            
            try:
                original_input_dir = os.path.join(problem_folder, "original_input")
                json_files = glob.glob(os.path.join(original_input_dir, "*.json"))
                
                if not json_files:
                    self.logger.warning(f"  没有找到 original_input JSON 文件")
                    stats["failed"] += 1
                    stats["files"].append({
                        "folder": folder_name,
                        "status": "failed",
                        "error": "没有找到 original_input JSON 文件"
                    })
                    continue
                
                seed_file = json_files[0]
                
                other_methods_dir = os.path.join(problem_folder, "other_methods")
                os.makedirs(other_methods_dir, exist_ok=True)
                
                output_path = os.path.join(other_methods_dir, "unicode.json")
                
                with open(seed_file, 'r', encoding='utf-8') as f:
                    seed_data = json.load(f)
                
                seed = Problem.from_dict(seed_data)
                
                augmenter = ProblemAugmenter(seed)
                augmented = augmenter.augment(
                    use_llm=self.use_llm,
                    llm_transformation=self.llm_transformation,
                    narrative=narrative,
                    rule=rule,
                    efficiency=efficiency,
                    sequential=sequential,
                    fusion=fusion
                )
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(augmented, f, ensure_ascii=False, indent=2)
                
                title = augmented.get('title', 'Generated Problem')
                self.logger.info(f"  ✓ 成功生成: {title}")
                self.logger.info(f"  输出到: {output_path}")
                
                stats["processed"] += 1
                stats["files"].append({
                    "folder": folder_name,
                    "output": output_path,
                    "status": "success",
                    "title": title,
                    "transformations": augmented.get('augmentation_history', [])
                })
                
            except Exception as e:
                self.logger.error(f"  ✗ 处理失败: {str(e)}")
                stats["failed"] += 1
                stats["files"].append({
                    "folder": folder_name,
                    "status": "failed",
                    "error": str(e)
                })
        
        self.logger.info("\n" + "=" * 60)
        self.logger.info("批量处理完成")
        self.logger.info(f"成功: {stats['processed']} 个")
        self.logger.info(f"失败: {stats['failed']} 个")
        self.logger.info("=" * 60)
        
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
    
    args = parser.parse_args()
    
    augmenter = BatchAugmenter(
        input_base_dir=args.input,
        use_llm=args.use_llm,
        llm_transformation=args.llm_transformation
    )
    
    stats = augmenter.process_problem_folders(
        narrative=not args.no_narrative,
        rule=not args.no_rule,
        efficiency=not args.no_efficiency,
        sequential=not args.no_sequential,
        fusion=not args.no_fusion
    )
    
    sys.exit(0 if stats["success"] and stats["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
