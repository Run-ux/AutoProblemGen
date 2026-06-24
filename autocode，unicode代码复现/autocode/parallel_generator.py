import json
import os
import glob
import multiprocessing
from typing import List, Dict, Any
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

def process_batch(problem_folders: List[str], base_dir: str, num_transformations: int, 
                  use_llm: bool, api_key: str, base_url: str, model: str, 
                  batch_num: int) -> Dict[str, Any]:
    logger = Logger(os.path.join(base_dir, f"autocode_batch_{batch_num}_log.txt"))
    
    generator = ProblemGenerator(
        seed=batch_num,
        use_llm=use_llm,
        api_key=api_key,
        base_url=base_url,
        model=model
    )
    
    logger.info(f"Batch {batch_num} started, processing {len(problem_folders)} problems")
    
    results = {
        "batch": batch_num,
        "total": len(problem_folders),
        "success": 0,
        "failed": 0,
        "details": []
    }
    
    for folder in problem_folders:
        folder_name = os.path.basename(folder)
        original_input_dir = os.path.join(folder, "original_input")
        
        if not os.path.exists(original_input_dir):
            results["failed"] += 1
            results["details"].append({"folder": folder_name, "status": "failed", "error": "original_input not found"})
            continue
        
        json_files = glob.glob(os.path.join(original_input_dir, "*.json"))
        if not json_files:
            results["failed"] += 1
            results["details"].append({"folder": folder_name, "status": "failed", "error": "no JSON files"})
            continue
        
        seed_file = json_files[0]
        other_methods_dir = os.path.join(folder, "other_methods")
        os.makedirs(other_methods_dir, exist_ok=True)
        output_path = os.path.join(other_methods_dir, "autocode.json")
        
        try:
            new_problem = generator.generate_from_file(seed_file, output_path, num_transformations)
            results["success"] += 1
            results["details"].append({
                "folder": folder_name,
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
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL")
    model = os.environ.get("OPENAI_MODEL", args.model)
    
    base_dir = args.input
    problem_folders = [f for f in glob.glob(os.path.join(base_dir, "*")) 
                       if os.path.isdir(f) and not f.startswith('_')]
    
    print(f"Found {len(problem_folders)} problem folders")
    print(f"Using {args.processes} parallel processes")
    print(f"Using LLM: {args.use_llm}")
    
    folders_per_process = len(problem_folders) // args.processes
    remainder = len(problem_folders) % args.processes
    
    batches = []
    start = 0
    for i in range(args.processes):
        end = start + folders_per_process + (1 if i < remainder else 0)
        batches.append(problem_folders[start:end])
        start = end
    
    print(f"Batch distribution: {[len(b) for b in batches]}")
    
    pool = multiprocessing.Pool(processes=args.processes)
    results = []
    
    for i, batch in enumerate(batches):
        result = pool.apply_async(process_batch, (
            batch, base_dir, args.transformations,
            args.use_llm, api_key, base_url, model, i
        ))
        results.append(result)
    
    pool.close()
    pool.join()
    
    all_results = [r.get() for r in results]
    
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
        "batches": all_results
    }
    
    with open(os.path.join(base_dir, "autocode_parallel_stats.json"), 'w', encoding='utf-8') as f:
        json.dump(final_stats, f, ensure_ascii=False, indent=2)
    
    print(f"Statistics saved to: {os.path.join(base_dir, 'autocode_parallel_stats.json')}")

if __name__ == "__main__":
    main()