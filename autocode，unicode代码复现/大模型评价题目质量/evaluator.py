"""
Algorithm Problem Quality Evaluator
Uses LLM to evaluate the quality of generated algorithmic problems across 4 dimensions:
1. Solvability - Whether the problem can be solved correctly
2. Clarity - How clear and understandable the problem description is
3. Novelty - How different the new problem is from the seed problem
4. Difficulty - Appropriate difficulty level
"""

import argparse
import glob
import json
import os
import sys
from typing import Dict, Any, Union, List, Optional, Tuple
from dataclasses import dataclass, asdict

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        return False

try:
    from openai import OpenAI
except ModuleNotFoundError:
    OpenAI = None


# Windows 管道环境默认编码可能不是 UTF-8，统一输出避免中文日志乱码。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# Load environment variables
load_dotenv()


@dataclass
class EvaluationResult:
    """Represents the evaluation result of a problem"""
    solvability: float  # 0-100
    clarity: float  # 0-100
    novelty: float  # 0-100
    difficulty: float  # 0-100
    overall_score: float  # 0-100, weighted average
    solvability_reasoning: str
    clarity_reasoning: str
    novelty_reasoning: str
    difficulty_reasoning: str
    overall_comment: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


class ProblemEvaluator:
    """LLM-powered problem quality evaluator"""
    
    def __init__(self):
        if OpenAI is None:
            raise RuntimeError("缺少 openai 依赖，请先执行: pip install openai")

        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )
        self.model = os.getenv("MODEL_NAME", "gpt-4o-mini")
        self.max_tokens = int(os.getenv("MAX_TOKENS", 4000))
        self.temperature = float(os.getenv("TEMPERATURE", 0.2))
    
    def generate_evaluation_prompt(self, seed_problem: Dict, new_problem: Union[Dict, str]) -> str:
        """Generate detailed prompt for LLM evaluation"""
        
        seed_json = json.dumps(seed_problem, ensure_ascii=False, indent=2)
        if isinstance(new_problem, dict):
            new_json = json.dumps(new_problem, ensure_ascii=False, indent=2)
            new_problem_section = f"NEW PROBLEM (Generated):\n{new_json}"
        else:
            new_problem_section = f"NEW PROBLEM (Generated):\n{new_problem}"
        
        prompt = f"""
You are an expert competitive programming problem evaluator. Your task is to evaluate the quality of a newly generated algorithmic problem by comparing it with its seed (original) problem.

SEED PROBLEM (Original):
{seed_json}

{new_problem_section}

Evaluate the new problem across the following 4 dimensions:

1. **Solvability (可解性)** - 0-100分
   - Does the problem have a valid solution?
   - Is the problem statement logically consistent?
   - Are the constraints and requirements achievable?
   - Do the examples match the problem description?
   - Are there any contradictions or ambiguities that make the problem unsolvable?

2. **Clarity (清晰度)** - 0-100分
   - Is the problem description clear and easy to understand?
   - Are the input/output formats well-defined?
   - Are the constraints explicitly stated?
   - Are the examples helpful and properly explained?
   - Is the language precise and unambiguous?
   - Would a typical competitive programmer understand what to do?

3. **Novelty (新颖度)** - 0-100分
   - How different is the new problem from the seed problem?
   - Has the core algorithmic approach changed significantly?
   - Are there substantial modifications beyond just variable renaming?
   - Does the problem introduce new concepts, constraints, or twists?
   - Is it a meaningful transformation or just cosmetic changes?
   - Note: Simply changing variable names or swapping similar themes should result in LOW novelty scores

4. **Difficulty (难度)** - 0-100分
   - Is the difficulty level appropriate for the target audience?
   - Does the difficulty match the stated difficulty level (Easy/Medium/Hard)?
   - Is the problem challenging enough without being impossible?
   - Are the constraints reasonable for the intended solution complexity?
   - Is there a good balance between problem complexity and time constraints?

SCORING GUIDELINES:
- 90-100: Excellent - meets all criteria exceptionally well
- 75-89: Good - meets most criteria with minor issues
- 60-74: Acceptable - meets basic criteria but has noticeable flaws
- 40-59: Poor - has significant issues affecting quality
- 0-39: Unacceptable - major flaws make the problem unusable

CRITICAL REQUIREMENTS:
1. For Novelty: If the new problem is essentially the same as the seed with only cosmetic changes (variable names, theme, etc.), give a LOW score (below 40). The problem must have substantial algorithmic or structural differences to merit a high novelty score.
2. For Solvability: If the problem is unsolvable, contradictory, or has broken examples, give a score below 40.
3. For Clarity: If the problem description is confusing, ambiguous, or missing critical information, give a score below 60.
4. For Difficulty: Consider both the actual complexity and the stated difficulty level.

Return ONLY a valid JSON object with this exact structure:
{{
  "solvability": <number 0-100>,
  "clarity": <number 0-100>,
  "novelty": <number 0-100>,
  "difficulty": <number 0-100>,
  "solvability_reasoning": "<detailed explanation for solvability score>",
  "clarity_reasoning": "<detailed explanation for clarity score>",
  "novelty_reasoning": "<detailed explanation for novelty score>",
  "difficulty_reasoning": "<detailed explanation for difficulty score>",
  "overall_comment": "<summary comment on overall quality and main strengths/weaknesses>"
}}

Do NOT include any other text, explanations, or markdown formatting.
"""
        return prompt
    
    def evaluate(self, seed_problem: Dict, new_problem: Union[Dict, str]) -> EvaluationResult:
        """Evaluate the new problem using LLM"""
        prompt = self.generate_evaluation_prompt(seed_problem, new_problem)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert competitive programming problem evaluator. Provide objective, detailed evaluations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )
            
            result = response.choices[0].message.content
            
            try:
                evaluation_data = json.loads(result)
                
                # Calculate weighted overall score
                # Weights: Solvability (30%), Clarity (25%), Novelty (25%), Difficulty (20%)
                overall_score = (
                    evaluation_data.get("solvability", 0) * 0.30 +
                    evaluation_data.get("clarity", 0) * 0.25 +
                    evaluation_data.get("novelty", 0) * 0.25 +
                    evaluation_data.get("difficulty", 0) * 0.20
                )
                
                evaluation_data["overall_score"] = round(overall_score, 2)
                
                return EvaluationResult(
                    solvability=evaluation_data.get("solvability", 0),
                    clarity=evaluation_data.get("clarity", 0),
                    novelty=evaluation_data.get("novelty", 0),
                    difficulty=evaluation_data.get("difficulty", 0),
                    overall_score=evaluation_data["overall_score"],
                    solvability_reasoning=evaluation_data.get("solvability_reasoning", ""),
                    clarity_reasoning=evaluation_data.get("clarity_reasoning", ""),
                    novelty_reasoning=evaluation_data.get("novelty_reasoning", ""),
                    difficulty_reasoning=evaluation_data.get("difficulty_reasoning", ""),
                    overall_comment=evaluation_data.get("overall_comment", "")
                )
                
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                print(f"Response: {result[:500]}")
                # Return default evaluation on error
                return self._get_default_evaluation()
                
        except Exception as e:
            print(f"LLM API error: {e}")
            return self._get_default_evaluation()
    
    def _get_default_evaluation(self) -> EvaluationResult:
        """Return default evaluation when API fails"""
        return EvaluationResult(
            solvability=0,
            clarity=0,
            novelty=0,
            difficulty=0,
            overall_score=0,
            solvability_reasoning="API error - unable to evaluate",
            clarity_reasoning="API error - unable to evaluate",
            novelty_reasoning="API error - unable to evaluate",
            difficulty_reasoning="API error - unable to evaluate",
            overall_comment="Evaluation failed due to API error"
        )
    
    def evaluate_from_files(self, seed_path: str, new_path: str, output_path: str) -> None:
        """Evaluate problems from JSON files and save result"""
        with open(seed_path, 'r', encoding='utf-8') as f:
            seed_problem = json.load(f)
        
        with open(new_path, 'r', encoding='utf-8') as f:
            new_problem = json.load(f)
        
        result = self.evaluate(seed_problem, new_problem)
        
        # Prepare output with both problems and evaluation
        output = {
            "seed_problem": seed_problem,
            "new_problem": new_problem,
            "evaluation": result.to_dict()
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"Evaluation completed. Results saved to: {output_path}")
        print(f"Overall Score: {result.overall_score}/100")
        print(f"  Solvability: {result.solvability}/100")
        print(f"  Clarity: {result.clarity}/100")
        print(f"  Novelty: {result.novelty}/100")
        print(f"  Difficulty: {result.difficulty}/100")

    @staticmethod
    def default_input_dir() -> str:
        """返回仓库默认的 successful_output 输入目录。"""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(project_root, "input", "successful_output")

    @staticmethod
    def _score_fields(result: EvaluationResult) -> Dict[str, float]:
        """只保留最终落盘需要的分数字段。"""
        return {
            "solvability": result.solvability,
            "clarity": result.clarity,
            "novelty": result.novelty,
            "difficulty": result.difficulty,
            "overall_score": result.overall_score
        }

    @staticmethod
    def _write_scores(scores_path: str, scores: Dict[str, Any]) -> None:
        with open(scores_path, 'w', encoding='utf-8') as f:
            json.dump(scores, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _list_problem_folders(base_dir: str) -> List[str]:
        return sorted(
            folder for folder in glob.glob(os.path.join(base_dir, "*"))
            if os.path.isdir(folder) and not os.path.basename(folder).startswith('_')
        )

    @staticmethod
    def _resolve_batch_dirs(root_dir: str, batch_name: Optional[str]) -> List[str]:
        if not os.path.isdir(root_dir):
            raise FileNotFoundError(f"输入目录不存在: {root_dir}")

        if batch_name:
            batch_dir = batch_name if os.path.isabs(batch_name) else os.path.join(root_dir, batch_name)
            if not os.path.isdir(batch_dir):
                raise FileNotFoundError(f"指定 batch 不存在: {batch_dir}")
            return [batch_dir]

        batch_dirs = sorted(
            folder for folder in glob.glob(os.path.join(root_dir, "batch*"))
            if os.path.isdir(folder)
        )
        return batch_dirs if batch_dirs else [root_dir]

    def _load_seed_problem(self, folder_path: str) -> Tuple[Dict[str, Any], str]:
        original_input_dir = os.path.join(folder_path, "original_input")
        if not os.path.isdir(original_input_dir):
            raise FileNotFoundError(f"original_input 目录不存在: {original_input_dir}")

        json_files = sorted(glob.glob(os.path.join(original_input_dir, "*.json")))
        if not json_files:
            raise FileNotFoundError(f"original_input 中没有 JSON 文件: {original_input_dir}")

        seed_path = json_files[0]
        with open(seed_path, 'r', encoding='utf-8') as f:
            seed_data = json.load(f)

        if not isinstance(seed_data, dict):
            raise ValueError(f"种子题 JSON 顶层必须是对象: {seed_path}")

        # 兼容旧数据：部分文件会把原题包在 original_problem 字段中。
        seed_problem = seed_data.get("original_problem", seed_data)
        if not isinstance(seed_problem, dict):
            raise ValueError(f"original_problem 字段必须是对象: {seed_path}")

        return seed_problem, seed_path

    def _evaluate_json_candidate(self, seed_problem: Dict[str, Any],
                                 candidate_path: str,
                                 folder_name: str,
                                 display_name: str) -> Dict[str, Any]:
        if not os.path.exists(candidate_path):
            error = f"文件不存在: {candidate_path}"
            print(f"[ERROR] {folder_name} - {display_name}: {error}")
            return {"error": error}

        try:
            with open(candidate_path, 'r', encoding='utf-8') as f:
                candidate_problem = json.load(f)
            if not isinstance(candidate_problem, dict):
                raise ValueError("候选题 JSON 顶层必须是对象")

            print(f"[EVAL] {folder_name} - {display_name}")
            result = self.evaluate(seed_problem, candidate_problem)
            return self._score_fields(result)
        except Exception as e:
            print(f"[ERROR] {folder_name} - {display_name}: {e}")
            return {"error": str(e)}

    def _evaluate_output_md(self, seed_problem: Dict[str, Any],
                            folder_path: str,
                            folder_name: str) -> Dict[str, Any]:
        output_dir = os.path.join(folder_path, "output")
        if not os.path.isdir(output_dir):
            error = f"output 目录不存在: {output_dir}"
            print(f"[ERROR] {folder_name} - output_md: {error}")
            return {"error": error}

        md_files = sorted(
            file_name for file_name in os.listdir(output_dir)
            if file_name.lower().endswith(".md")
        )
        if not md_files:
            error = f"output 中没有 md 文件: {output_dir}"
            print(f"[ERROR] {folder_name} - output_md: {error}")
            return {"error": error}

        last_md = md_files[-1]
        md_path = os.path.join(output_dir, last_md)
        try:
            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()

            print(f"[EVAL] {folder_name} - {last_md}")
            result = self.evaluate(seed_problem, md_content)
            return self._score_fields(result)
        except Exception as e:
            print(f"[ERROR] {folder_name} - {last_md}: {e}")
            return {"error": str(e)}

    def evaluate_folder(self, folder_path: str) -> Dict[str, Any]:
        """评估单个题目文件夹，并在题目目录下覆盖写入 scores.json。"""
        folder_name = os.path.basename(os.path.normpath(folder_path))
        scores_path = os.path.join(folder_path, "scores.json")

        try:
            seed_problem, seed_path = self._load_seed_problem(folder_path)
            print(f"[SEED] {folder_name} - {os.path.basename(seed_path)}")
        except Exception as e:
            error = f"种子题加载失败: {e}"
            print(f"[ERROR] {folder_name}: {error}")
            scores = {
                "_error": error,
                "autocode": {"error": error},
                "unicode": {"error": error},
                "output_md": {"error": error}
            }
            self._write_scores(scores_path, scores)
            print(f"[DONE] {folder_name} - scores saved to {scores_path}")
            return {
                "folder": folder_name,
                "status": "failed",
                "error": error,
                "scores_path": scores_path
            }

        scores = {
            "autocode": self._evaluate_json_candidate(
                seed_problem,
                os.path.join(folder_path, "other_methods", "autocode.json"),
                folder_name,
                "other_methods/autocode.json"
            ),
            "unicode": self._evaluate_json_candidate(
                seed_problem,
                os.path.join(folder_path, "other_methods", "unicode.json"),
                folder_name,
                "other_methods/unicode.json"
            ),
            "output_md": self._evaluate_output_md(seed_problem, folder_path, folder_name)
        }

        self._write_scores(scores_path, scores)
        print(f"[DONE] {folder_name} - scores saved to {scores_path}")

        has_error = any(isinstance(item, dict) and "error" in item for item in scores.values())
        return {
            "folder": folder_name,
            "status": "failed" if has_error else "success",
            "scores_path": scores_path
        }

    def batch_evaluate(self, root_dir: str, batch_name: Optional[str] = None) -> Dict[str, Any]:
        """评估 successful_output 下的 batch 或兼容旧版单层题目目录。"""
        root_dir = os.path.abspath(root_dir)
        target_dirs = self._resolve_batch_dirs(root_dir, batch_name)

        summary = {
            "input": root_dir,
            "batch": batch_name,
            "total": 0,
            "success": 0,
            "failed": 0,
            "details": []
        }

        for target_dir in target_dirs:
            target_name = os.path.basename(os.path.normpath(target_dir))
            problem_folders = self._list_problem_folders(target_dir)
            print(f"[BATCH] {target_name} - found {len(problem_folders)} problem folders")

            for index, folder_path in enumerate(problem_folders, 1):
                folder_name = os.path.basename(os.path.normpath(folder_path))
                print(f"[PROBLEM] {target_name} [{index}/{len(problem_folders)}] {folder_name}")
                result = self.evaluate_folder(folder_path)
                result["batch"] = target_name
                summary["details"].append(result)
                summary["total"] += 1
                if result["status"] == "success":
                    summary["success"] += 1
                else:
                    summary["failed"] += 1

        print(
            f"[SUMMARY] total={summary['total']} "
            f"success={summary['success']} failed={summary['failed']}"
        )
        return summary


def demo():
    """Demonstrate the evaluator with sample problems"""
    sample_seed = {
        "title": "Longest Increasing Subsequence",
        "description": "Given an array nums, find the length of the longest strictly increasing subsequence.",
        "input_format": "First line: n (1 ≤ n ≤ 1000)\nSecond line: n integers",
        "output_format": "A single integer - the length of LIS",
        "constraints": [
            "1 ≤ n ≤ 1000",
            "0 ≤ nums[i] ≤ 10^6"
        ],
        "examples": [
            {
                "input": "5\n1 3 2 4 5",
                "output": "4",
                "explanation": "The LIS is [1,2,4,5] with length 4"
            }
        ],
        "difficulty": "Medium",
        "tags": ["dynamic-programming", "binary-search"]
    }
    
    sample_new = {
        "title": "Longest Non-decreasing Subsequence",
        "description": "Given an array arr, find the length of the longest non-decreasing subsequence.",
        "input_format": "First line: n (1 ≤ n ≤ 1000)\nSecond line: n integers",
        "output_format": "A single integer - the length of the longest non-decreasing subsequence",
        "constraints": [
            "1 ≤ n ≤ 1000",
            "0 ≤ arr[i] ≤ 10^6"
        ],
        "examples": [
            {
                "input": "5\n1 3 2 4 5",
                "output": "5",
                "explanation": "The longest non-decreasing subsequence is [1,3,2,4,5] with length 5"
            }
        ],
        "difficulty": "Medium",
        "tags": ["dynamic-programming", "binary-search"]
    }
    
    evaluator = ProblemEvaluator()
    result = evaluator.evaluate(sample_seed, sample_new)
    
    print("=" * 60)
    print("EVALUATION RESULT")
    print("=" * 60)
    print(f"Overall Score: {result.overall_score}/100")
    print(f"\nSolvability: {result.solvability}/100")
    print(f"  {result.solvability_reasoning}")
    print(f"\nClarity: {result.clarity}/100")
    print(f"  {result.clarity_reasoning}")
    print(f"\nNovelty: {result.novelty}/100")
    print(f"  {result.novelty_reasoning}")
    print(f"\nDifficulty: {result.difficulty}/100")
    print(f"  {result.difficulty_reasoning}")
    print(f"\nOverall Comment:")
    print(f"  {result.overall_comment}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="大模型题目质量批量评分工具")
    parser.add_argument(
        "legacy_input",
        nargs="?",
        help="兼容旧用法的位置参数输入目录，等价于 --input"
    )
    parser.add_argument(
        "--input",
        "-i",
        default=ProblemEvaluator.default_input_dir(),
        help="successful_output 根目录，默认使用仓库下的 input/successful_output"
    )
    parser.add_argument(
        "--batch",
        help="只处理指定 batch 文件夹，例如 batch1；不指定时处理所有 batch*"
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    target_dir = args.legacy_input or args.input

    try:
        ProblemEvaluator._resolve_batch_dirs(os.path.abspath(target_dir), args.batch)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    try:
        evaluator = ProblemEvaluator()
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    evaluator.batch_evaluate(target_dir, args.batch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
