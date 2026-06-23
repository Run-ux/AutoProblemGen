"""
批量题目增强处理脚本
支持批量处理文件夹中的 JSON 文件，并输出到对应目录
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from augmenter import ProblemAugmenter, Problem


class BatchAugmenter:
    """批量增强处理器"""
    
    def __init__(self, 
                 input_base_dir: str = "input",
                 output_base_dir: str = "output",
                 use_llm: bool = False,
                 llm_transformation: str = "all"):
        """
        初始化批量增强器
        
        Args:
            input_base_dir: 输入基础目录
            output_base_dir: 输出基础目录
            use_llm: 是否使用 LLM 增强
            llm_transformation: LLM 变换类型
        """
        self.input_base_dir = Path(input_base_dir)
        self.output_base_dir = Path(output_base_dir)
        self.use_llm = use_llm
        self.llm_transformation = llm_transformation
        
        # 创建输出基础目录
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置日志
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger("BatchAugmenter")
        logger.setLevel(logging.INFO)
        
        # 清除已有的处理器
        logger.handlers.clear()
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        return logger
    
    def _setup_file_logger(self, log_file_path: Path) -> logging.Logger:
        """为特定批处理设置文件日志"""
        logger = logging.getLogger("BatchAugmenter")
        
        # 文件处理器
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        return logger
    
    def _get_json_files(self, input_dir: Path) -> List[Path]:
        """获取目录下所有 JSON 文件"""
        json_files = list(input_dir.glob("*.json"))
        return sorted(json_files)
    
    def _create_output_dir(self, input_subdir_name: str) -> Path:
        """创建输出目录，名称与输入子目录相关"""
        # 可以添加时间戳或其他标识
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir_name = f"{input_subdir_name}_{timestamp}"
        output_dir = self.output_base_dir / output_dir_name
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    
    def process_batch(self, 
                     input_subdir: str,
                     narrative: bool = True,
                     rule: bool = True,
                     efficiency: bool = True,
                     sequential: bool = True,
                     fusion: bool = True) -> dict:
        """
        批量处理指定子目录下的所有 JSON 文件
        
        Args:
            input_subdir: 输入子目录名称（相对于 input_base_dir）
            narrative: 应用叙事扰动
            rule: 应用规则修改
            efficiency: 应用效率缩放
            sequential: 应用顺序组合
            fusion: 应用概念融合
            
        Returns:
            处理结果统计
        """
        input_dir = self.input_base_dir / input_subdir
        
        # 检查输入目录是否存在
        if not input_dir.exists():
            self.logger.error(f"输入目录不存在: {input_dir}")
            return {"success": False, "error": f"输入目录不存在: {input_dir}"}
        
        # 获取所有 JSON 文件
        json_files = self._get_json_files(input_dir)
        
        if not json_files:
            self.logger.warning(f"目录 {input_dir} 中没有找到 JSON 文件")
            return {"success": True, "processed": 0, "failed": 0, "files": []}
        
        # 创建输出目录
        output_dir = self._create_output_dir(input_subdir)
        log_file_path = output_dir / "batch_log.txt"
        
        # 添加文件日志
        self._setup_file_logger(log_file_path)
        
        self.logger.info("=" * 60)
        self.logger.info(f"开始批量处理")
        self.logger.info(f"输入目录: {input_dir}")
        self.logger.info(f"输出目录: {output_dir}")
        self.logger.info(f"找到 {len(json_files)} 个 JSON 文件")
        self.logger.info(f"使用 LLM: {self.use_llm}")
        if self.use_llm:
            self.logger.info(f"LLM 变换类型: {self.llm_transformation}")
        self.logger.info("=" * 60)
        
        # 统计信息
        stats = {
            "success": True,
            "processed": 0,
            "failed": 0,
            "files": []
        }
        
        # 处理每个文件
        for json_file in json_files:
            self.logger.info(f"\n处理文件: {json_file.name}")
            
            try:
                # 读取种子题目
                with open(json_file, 'r', encoding='utf-8') as f:
                    seed_data = json.load(f)
                
                seed = Problem.from_dict(seed_data)
                
                # 增强题目
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
                
                # 保存结果
                output_file = output_dir / f"augmented_{json_file.name}"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(augmented, f, ensure_ascii=False, indent=2)
                
                self.logger.info(f"  ✓ 成功保存到: {output_file.name}")
                self.logger.info(f"  应用变换: {augmented.get('augmentation_history', [])}")
                
                stats["processed"] += 1
                stats["files"].append({
                    "input": str(json_file.name),
                    "output": str(output_file.name),
                    "status": "success",
                    "transformations": augmented.get('augmentation_history', [])
                })
                
            except Exception as e:
                self.logger.error(f"  ✗ 处理失败: {str(e)}")
                stats["failed"] += 1
                stats["files"].append({
                    "input": str(json_file.name),
                    "output": None,
                    "status": "failed",
                    "error": str(e)
                })
        
        # 保存统计信息
        stats_file = output_dir / "batch_stats.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        
        # 输出总结
        self.logger.info("\n" + "=" * 60)
        self.logger.info("批量处理完成")
        self.logger.info(f"成功: {stats['processed']} 个")
        self.logger.info(f"失败: {stats['failed']} 个")
        self.logger.info(f"统计信息已保存到: {stats_file.name}")
        self.logger.info("=" * 60)
        
        # 移除文件日志处理器（避免重复添加）
        handlers = self.logger.handlers[:]
        for handler in handlers:
            if isinstance(handler, logging.FileHandler):
                self.logger.removeHandler(handler)
                handler.close()
        
        return stats
    
    def list_input_dirs(self) -> List[str]:
        """列出所有可用的输入子目录"""
        if not self.input_base_dir.exists():
            return []
        
        dirs = [d.name for d in self.input_base_dir.iterdir() if d.is_dir()]
        return sorted(dirs)


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="批量题目增强处理工具")
    parser.add_argument("input_subdir", help="输入子目录名称（相对于 input 目录）")
    parser.add_argument("--input-base", default="input", help="输入基础目录（默认: input）")
    parser.add_argument("--output-base", default="output", help="输出基础目录（默认: output）")
    parser.add_argument("--use-llm", action="store_true", help="使用 LLM 增强")
    parser.add_argument("--llm-transformation", default="all", 
                       choices=["narrative", "rule", "efficiency", "sequential", "fusion", "all"],
                       help="LLM 变换类型（默认: all）")
    parser.add_argument("--no-narrative", action="store_true", help="不应用叙事扰动")
    parser.add_argument("--no-rule", action="store_true", help="不应用规则修改")
    parser.add_argument("--no-efficiency", action="store_true", help="不应用效率缩放")
    parser.add_argument("--no-sequential", action="store_true", help="不应用顺序组合")
    parser.add_argument("--no-fusion", action="store_true", help="不应用概念融合")
    parser.add_argument("--list", action="store_true", help="列出所有可用的输入子目录")
    
    args = parser.parse_args()
    
    # 创建批量增强器
    augmenter = BatchAugmenter(
        input_base_dir=args.input_base,
        output_base_dir=args.output_base,
        use_llm=args.use_llm,
        llm_transformation=args.llm_transformation
    )
    
    # 列出可用目录
    if args.list:
        dirs = augmenter.list_input_dirs()
        print("可用的输入子目录:")
        for d in dirs:
            print(f"  - {d}")
        if not dirs:
            print("  （没有找到子目录）")
        return
    
    # 批量处理
    stats = augmenter.process_batch(
        input_subdir=args.input_subdir,
        narrative=not args.no_narrative,
        rule=not args.no_rule,
        efficiency=not args.no_efficiency,
        sequential=not args.no_sequential,
        fusion=not args.no_fusion
    )
    
    # 退出码
    sys.exit(0 if stats["success"] else 1)


if __name__ == "__main__":
    main()