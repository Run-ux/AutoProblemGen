import json
import os
import glob
import multiprocessing
import datetime
from typing import List, Dict, Any, Optional

try:
    from .generator import ProblemGenerator, Logger
except ImportError:
    from generator import ProblemGenerator, Logger

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

def chunk_problem_folders(problem_folders: List[str], batch_size: int) -> List[List[str]]:
    return [
        problem_folders[index:index + batch_size]
        for index in range(0, len(problem_folders), batch_size)
    ]


def process_batch(problem_folders: List[str], base_dir: str, num_transformations: int,
                  use_llm: bool, api_key: Optional[str], base_url: Optional[str],
                  model: str, max_tokens: Optional[int],
                  batch_num: int) -> Dict[str, Any]:
    logger = Logger(os.path.join(base_dir, f"autocode_batch_{batch_num}_log.txt"))
    
    generator = ProblemGenerator(
        seed=batch_num,
        use_llm=use_llm,
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens
    )
    
    logger.info(f"Batch {batch_num} started, processing {len(problem_folders)} problems")
    
    results = {
        "batch": batch_num,
        "total": len(problem_folders),
        "success": 0,
        "failed": 0,
        "details": [],
        "start_time": datetime.datetime.now().isoformat()
    }
    
    for folder in problem_folders:
        folder_name = os.path.basename(folder)
        original_input_dir = os.path.join(folder, "original_input")
        logger.info(f"Processing folder: {folder_name}")
        
        if not os.path.exists(original_input_dir):
            results["failed"] += 1
            results["details"].append({"folder": folder_name, "status": "failed", "error": "original_input not found"})
            logger.warning(f"Batch {batch_num}: {folder_name} skipped - original_input not found")
            continue
        
        json_files = sorted(glob.glob(os.path.join(original_input_dir, "*.json")))
        if not json_files:
            results["failed"] += 1
            results["details"].append({"folder": folder_name, "status": "failed", "error": "no JSON files"})
            logger.warning(f"Batch {batch_num}: {folder_name} skipped - no JSON files")
            continue
        
        seed_file = json_files[0]
        other_methods_dir = os.path.join(folder, "other_methods")
        os.makedirs(other_methods_dir, exist_ok=True)
        output_path = os.path.join(other_methods_dir, "autocode.json")
        logger.info(f"Batch {batch_num}: {folder_name} seed file: {os.path.basename(seed_file)}")
        
        try:
            new_problem = generator.generate_from_file(seed_file, output_path, num_transformations)
            results["success"] += 1
            results["details"].append({
                "folder": folder_name,
                "seed_file": os.path.basename(seed_file),
                "output": output_path,
                "title": new_problem.title,
                "transformations": new_problem.transformation_type,
                "difficulty": new_problem.difficulty,
                "status": "success"
            })
            logger.success(f"Batch {batch_num}: {folder_name} -> {new_problem.title}")
        except Exception as e:
            results["failed"] += 1
            results["details"].append({"folder": folder_name, "status": "failed", "error": str(e)})
            logger.error(f"Batch {batch_num}: {folder_name} failed - {str(e)}")
    
    results["end_time"] = datetime.datetime.now().isoformat()
    duration = datetime.datetime.fromisoformat(results["end_time"]) - datetime.datetime.fromisoformat(results["start_time"])
    results["duration"] = str(duration)
    logger.info(f"Batch {batch_num} completed: {results['success']}/{results['total']}")
    
    stats_file = os.path.join(base_dir, f"autocode_batch_{batch_num}_stats.json")
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    return results

def main():
    import argparse
    
    load_env()
    
    parser = argparse.ArgumentParser(description='Parallel AutoCode Problem Generator')
    parser.add_argument('--input', '-i', required=True, help='Base directory containing problem folders')
    parser.add_argument('--transformations', '-t', type=int, default=1, help='Number of transformations')
    parser.add_argument('--use-llm', action='store_true', help='Use LLM for generation')
    parser.add_argument('--api-key', type=str, help='OpenAI API key')
    parser.add_argument('--base-url', type=str, help='API base URL')
    parser.add_argument('--model', type=str, default="gpt-4o", help='Model name')
    parser.add_argument('--processes', type=int, default=5, help='Number of parallel processes')
    parser.add_argument('--batch-size', type=int, default=5, help='Number of problem folders per batch')
    parser.add_argument('--max-tokens', type=int, help='Maximum completion tokens for LLM generation')
    
    args = parser.parse_args()

    if args.batch_size <= 0:
        parser.error("--batch-size must be a positive integer")
    if args.processes <= 0:
        parser.error("--processes must be a positive integer")
    
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL")
    model = os.environ.get("OPENAI_MODEL", args.model)
    
    base_dir = args.input
    if not os.path.isdir(base_dir):
        parser.error(f"Input path is not a directory: {base_dir}")

    problem_folders = sorted(
        f for f in glob.glob(os.path.join(base_dir, "*"))
        if os.path.isdir(f) and not os.path.basename(f).startswith('_')
    )
    batches = chunk_problem_folders(problem_folders, args.batch_size)
    pool_processes = min(args.processes, len(batches)) if batches else 0
    
    print(f"Found {len(problem_folders)} problem folders")
    print(f"Batch size: {args.batch_size}")
    print(f"Created {len(batches)} batches")
    print(f"Using {pool_processes} parallel processes")
    print(f"Using LLM: {args.use_llm}")

    if args.use_llm:
        print(f"Max tokens: {args.max_tokens or os.environ.get('MAX_TOKENS', 16000)}")

    print(f"Batch distribution: {[len(b) for b in batches]}")

    if not batches:
        all_results = []
    elif pool_processes == 1:
        all_results = [
            process_batch(
                batch, base_dir, args.transformations,
                args.use_llm, api_key, base_url, model, args.max_tokens, index
            )
            for index, batch in enumerate(batches, 1)
        ]
    else:
        with multiprocessing.Pool(processes=pool_processes) as pool:
            results = [
                pool.apply_async(process_batch, (
                    batch, base_dir, args.transformations,
                    args.use_llm, api_key, base_url, model, args.max_tokens, index
                ))
                for index, batch in enumerate(batches, 1)
            ]
            all_results = [result.get() for result in results]
    
    total_success = sum(r["success"] for r in all_results)
    total_failed = sum(r["failed"] for r in all_results)
    total = sum(r["total"] for r in all_results)
    
    print(f"\n{'='*60}")
    print(f"Parallel processing complete")
    print(f"Total: {total}")
    print(f"Success: {total_success}")
    print(f"Failed: {total_failed}")
    print(f"{'='*60}")
    
    final_stats = {
        "total": total,
        "success": total_success,
        "failed": total_failed,
        "batch_size": args.batch_size,
        "processes": pool_processes,
        "batches": all_results
    }
    
    with open(os.path.join(base_dir, "autocode_parallel_stats.json"), 'w', encoding='utf-8') as f:
        json.dump(final_stats, f, ensure_ascii=False, indent=2)
    
    print(f"Statistics saved to: {os.path.join(base_dir, 'autocode_parallel_stats.json')}")

if __name__ == "__main__":
    main()
