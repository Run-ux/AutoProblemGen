import json
import argparse
import random
import os
import glob
import datetime
from typing import Dict, Any, Optional, List
from .schema import Problem
from .transformations import TransformationEngine
from .llm_transformations import LLMTransformationEngine
from .llm import LLMClient

class Logger:
    def __init__(self, log_file: str = None):
        self.log_file = log_file
        self.logs = []
    
    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.logs.append(log_entry)
        print(log_entry)
        
        if self.log_file:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
    
    def info(self, message: str):
        self.log(message, "INFO")
    
    def success(self, message: str):
        self.log(message, "SUCCESS")
    
    def warning(self, message: str):
        self.log(message, "WARNING")
    
    def error(self, message: str):
        self.log(message, "ERROR")

class ProblemGenerator:
    def __init__(self, seed: Optional[int] = None, use_llm: bool = False,
                 api_key: Optional[str] = None, base_url: Optional[str] = None,
                 model: str = "gpt-4o"):
        if seed is not None:
            random.seed(seed)
        
        self.use_llm = use_llm
        
        if use_llm:
            self.llm_client = LLMClient(api_key=api_key, base_url=base_url, model=model)
            self.engine = LLMTransformationEngine(self.llm_client)
        else:
            self.engine = TransformationEngine()
    
    def generate_from_file(self, input_path: str, output_path: str, 
                           num_transformations: int = 1) -> Problem:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        seed_problem = Problem.from_dict(data)
        new_problem = self.engine.apply_multiple_transformations(
            seed_problem, num_transformations
        )
        
        output_data = new_problem.to_dict()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        return new_problem
    
    def generate_from_dict(self, seed_data: Dict[str, Any], 
                          num_transformations: int = 1) -> Dict[str, Any]:
        seed_problem = Problem.from_dict(seed_data)
        new_problem = self.engine.apply_multiple_transformations(
            seed_problem, num_transformations
        )
        return new_problem.to_dict()
    
    def batch_generate(self, input_dir: str, output_dir: str, 
                       num_transformations: int = 1, logger: Logger = None) -> Dict[str, Any]:
        if logger is None:
            logger = Logger()
        
        json_files = glob.glob(os.path.join(input_dir, "*.json"))
        
        if not json_files:
            logger.warning(f"No JSON files found in input directory: {input_dir}")
            return {"total": 0, "success": 0, "failed": 0, "details": []}
        
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"Found {len(json_files)} JSON files in input directory")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Number of transformations: {num_transformations}")
        logger.info(f"Using LLM: {self.use_llm}")
        
        results = {
            "total": len(json_files),
            "success": 0,
            "failed": 0,
            "details": [],
            "start_time": datetime.datetime.now().isoformat()
        }
        
        for i, json_file in enumerate(json_files, 1):
            filename = os.path.basename(json_file)
            output_filename = f"generated_{filename}"
            output_path = os.path.join(output_dir, output_filename)
            
            logger.info(f"\n[{i}/{len(json_files)}] Processing: {filename}")
            
            try:
                new_problem = self.generate_from_file(json_file, output_path, num_transformations)
                
                logger.success(f"Successfully generated: {new_problem.title}")
                logger.info(f"  Original: {new_problem.original_seed}")
                logger.info(f"  Transformations: {new_problem.transformation_type}")
                logger.info(f"  Difficulty: {new_problem.difficulty}")
                logger.info(f"  Output: {output_path}")
                
                results["success"] += 1
                results["details"].append({
                    "input": filename,
                    "output": output_filename,
                    "title": new_problem.title,
                    "original": new_problem.original_seed,
                    "transformations": new_problem.transformation_type,
                    "difficulty": new_problem.difficulty,
                    "status": "success"
                })
                
            except Exception as e:
                logger.error(f"Failed to process {filename}: {str(e)}")
                
                results["failed"] += 1
                results["details"].append({
                    "input": filename,
                    "output": None,
                    "title": None,
                    "original": None,
                    "transformations": None,
                    "difficulty": None,
                    "status": "failed",
                    "error": str(e)
                })
        
        results["end_time"] = datetime.datetime.now().isoformat()
        duration = datetime.datetime.fromisoformat(results["end_time"]) - datetime.datetime.fromisoformat(results["start_time"])
        results["duration"] = str(duration)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Batch processing complete")
        logger.info(f"Total: {results['total']}")
        logger.info(f"Success: {results['success']}")
        logger.info(f"Failed: {results['failed']}")
        logger.info(f"Duration: {results['duration']}")
        logger.info(f"{'='*60}")
        
        stats_file = os.path.join(output_dir, "batch_stats.json")
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"Batch statistics saved to: {stats_file}")
        
        return results

def main():
    parser = argparse.ArgumentParser(
        description='AutoCode Problem Generator - Generate new competitive programming problems from seed problems'
    )
    parser.add_argument(
        '--input', '-i', required=True,
        help='Path to the input seed problem JSON file or directory'
    )
    parser.add_argument(
        '--output', '-o',
        help='Path to the output new problem JSON file or directory'
    )
    parser.add_argument(
        '--transformations', '-t', type=int, default=1,
        help='Number of transformations to apply (default: 1)'
    )
    parser.add_argument(
        '--seed', '-s', type=int,
        help='Random seed for reproducibility'
    )
    parser.add_argument(
        '--use-llm', action='store_true',
        help='Use LLM for problem generation (requires API key)'
    )
    parser.add_argument(
        '--api-key', type=str,
        help='OpenAI API key (or set OPENAI_API_KEY environment variable)'
    )
    parser.add_argument(
        '--base-url', type=str,
        help='OpenAI API base URL (or set OPENAI_BASE_URL environment variable)'
    )
    parser.add_argument(
        '--model', type=str, default="gpt-4o",
        help='LLM model to use (default: gpt-4o)'
    )
    parser.add_argument(
        '--batch', action='store_true',
        help='Enable batch mode for processing multiple JSON files'
    )
    
    args = parser.parse_args()
    
    input_path = args.input
    output_path = args.output
    
    if args.batch:
        input_dir = input_path
        
        if not os.path.isdir(input_dir):
            print(f"Error: Input path is not a directory: {input_dir}")
            return
        
        input_folder_name = os.path.basename(os.path.normpath(input_dir))
        
        if output_path:
            output_dir = output_path
        else:
            output_dir = os.path.join("autocode", "output", f"{input_folder_name}_generated")
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"{output_dir}_{timestamp}"
        
        log_file = os.path.join(output_dir, "batch_log.txt")
        
        os.makedirs(output_dir, exist_ok=True)
        
        logger = Logger(log_file)
        
        logger.info(f"{'='*60}")
        logger.info("AutoCode Problem Generator - Batch Mode")
        logger.info(f"{'='*60}")
        
        generator = ProblemGenerator(
            seed=args.seed,
            use_llm=args.use_llm,
            api_key=args.api_key,
            base_url=args.base_url,
            model=args.model
        )
        
        generator.batch_generate(input_dir, output_dir, args.transformations, logger)
        
    else:
        if not output_path:
            print("Error: Output path is required for single file mode")
            return
        
        generator = ProblemGenerator(
            seed=args.seed,
            use_llm=args.use_llm,
            api_key=args.api_key,
            base_url=args.base_url,
            model=args.model
        )
        
        new_problem = generator.generate_from_file(
            input_path, output_path, args.transformations
        )
        
        print(f"\nSuccessfully generated new problem: {new_problem.title}")
        print(f"Original seed: {new_problem.original_seed}")
        print(f"Transformation type: {new_problem.transformation_type}")
        print(f"New difficulty: {new_problem.difficulty}")
        print(f"Output saved to: {output_path}")

if __name__ == "__main__":
    main()