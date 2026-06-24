"""
Algorithm Problem Quality Evaluator
Uses LLM to evaluate the quality of generated algorithmic problems across 4 dimensions:
1. Solvability - Whether the problem can be solved correctly
2. Clarity - How clear and understandable the problem description is
3. Novelty - How different the new problem is from the seed problem
4. Difficulty - Appropriate difficulty level
"""

import json
import os
from typing import Dict, Any
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
from openai import OpenAI


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
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )
        self.model = os.getenv("MODEL_NAME", "gpt-4o-mini")
        self.max_tokens = int(os.getenv("MAX_TOKENS", 4000))
        self.temperature = float(os.getenv("TEMPERATURE", 0.2))
    
    def generate_evaluation_prompt(self, seed_problem: Dict, new_problem: Dict) -> str:
        """Generate detailed prompt for LLM evaluation"""
        
        seed_json = json.dumps(seed_problem, ensure_ascii=False, indent=2)
        new_json = json.dumps(new_problem, ensure_ascii=False, indent=2)
        
        prompt = f"""
You are an expert competitive programming problem evaluator. Your task is to evaluate the quality of a newly generated algorithmic problem by comparing it with its seed (original) problem.

SEED PROBLEM (Original):
{seed_json}

NEW PROBLEM (Generated):
{new_json}

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
    
    def evaluate(self, seed_problem: Dict, new_problem: Dict) -> EvaluationResult:
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


if __name__ == "__main__":
    demo()