"""
UniCode Problem Augmentation Implementation
Based on the paper: "UniCode: Augmenting Evaluation for Code Reasoning"
Implements 5 augmentation axes with LLM-powered transformations:
1. Narrative Perturbation - Change variable names, thematic backgrounds
2. Rule Modification - Alter operational rules or boundary conditions
3. Efficiency Scaling - Change input scale to require different algorithms
4. Sequential Composition - Chain multiple algorithmic steps
5. Concept Fusion - Merge distinct algorithmic concepts
"""

import json
import random
import re
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
from openai import OpenAI


# Load environment variables
load_dotenv()


@dataclass
class Problem:
    """Represents a competitive programming problem"""
    title: str
    description: str
    input_format: str
    output_format: str
    constraints: List[str]
    examples: List[Dict[str, str]]
    difficulty: str  # Easy, Medium, Hard
    tags: List[str]  # e.g., ["dynamic-programming", "greedy"]
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        return result
    
    def to_dict_for_prompt(self) -> Dict:
        """精简数据用于 prompt，排除不必要的字段"""
        result = asdict(self)
        # 这些字段不存在于 Problem dataclass，但可能在原始数据中
        # 不需要排除，因为 dataclass 只有定义的字段
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Problem':
        return cls(
            title=data.get('title', ''),
            description=data.get('description', ''),
            input_format=data.get('input_format', data.get('input', '')),
            output_format=data.get('output_format', data.get('output', '')),
            constraints=data.get('constraints', []),
            examples=data.get('examples', []),
            difficulty=data.get('difficulty', 'Medium'),
            tags=data.get('tags', [])
        )


class LLMAugmenter:
    """LLM-powered problem augmentation through conversation"""
    
    def __init__(self, model: str = None):
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )
        self.model = model or os.getenv("MODEL_NAME", "deepseek-v4-pro")
        self.max_tokens = int(os.getenv("MAX_TOKENS", 8000))  # 增加到8000
        self.temperature = float(os.getenv("TEMPERATURE", 0.7))
    
    def generate_prompt(self, problem: Problem, transformation_type: str) -> str:
        """Generate a concise prompt for the LLM to perform the transformation"""
        
        transformation_desc = {
            "narrative": "Change variable names and thematic background while preserving core algorithmic logic",
            "rule": "Modify operational rules and boundary conditions while preserving core algorithmic category",
            "efficiency": "Scale up input size to require more efficient algorithm",
            "sequential": "Add additional sequential algorithmic steps",
            "fusion": "Fuse with another algorithmic concept",
            "all": "Apply all transformations: narrative perturbation, rule modification, efficiency scaling, sequential composition, and concept fusion"
        }
        
        desc = transformation_desc.get(transformation_type, transformation_desc["all"])
        
        # 使用精简的数据
        problem_json = json.dumps(problem.to_dict_for_prompt(), ensure_ascii=False, indent=2)
        
        prompt = f"""
You are a competitive programming problem setter. Transform the given seed problem by applying the following transformation:

{desc}

Rules:
1. Keep the core algorithmic challenge unchanged
2. Make the problem significantly different from the original
3. Ensure all problem components are consistent (description, input/output format, constraints, examples)

Output format (JSON only, no markdown):
{{
  "title": "New Problem Title",
  "description": "New problem description",
  "input_format": "Input format description",
  "output_format": "Output format description",
  "constraints": ["constraint1", "constraint2"],
  "examples": [{{"input": "...", "output": "...", "explanation": "..."}}],
  "difficulty": "...",
  "tags": ["tag1", "tag2"]
}}

Seed Problem:
{problem_json}
"""
        return prompt
    
    def transform(self, problem: Problem, transformation_type: str = "all") -> Dict:
        """Transform problem using LLM"""
        prompt = self.generate_prompt(problem, transformation_type)
        
        # 动态估算需要的输出 token 数
        seed_size = len(json.dumps(problem.to_dict_for_prompt()))
        estimated_tokens = min(seed_size // 3 + 4000, 16000)  # 最大16000
        actual_max_tokens = max(self.max_tokens, estimated_tokens)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert competitive programming problem generator."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=actual_max_tokens,
                temperature=self.temperature
            )
            
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            
            # 检查是否被截断
            if finish_reason == "length":
                print(f"⚠️  Warning: Output was truncated! max_tokens={actual_max_tokens}, consider increasing")
            
            if not content:
                print(f"LLM returned empty response. Finish reason: {finish_reason}")
                return problem.to_dict()
            
            content = content.strip()
            
            try:
                start = content.index('{')
                end = content.rindex('}') + 1
                json_str = content[start:end]
                return json.loads(json_str)
            except (ValueError, json.JSONDecodeError):
                print(f"JSON decode error. Finish reason: {finish_reason}. Response: {content[:500]}")
                return self._parse_fallback(content)
                
        except Exception as e:
            print(f"LLM API error: {e}")
            return problem.to_dict()
    
    def _parse_fallback(self, content: str) -> Dict[str, Any]:
        """Fallback parser for non-standard JSON responses"""
        lines = content.split('\n')
        result = {
            "title": "Generated Problem",
            "description": content,
            "input_format": "",
            "output_format": "",
            "constraints": [],
            "examples": [],
            "difficulty": "Medium",
            "tags": []
        }
        
        for line in lines:
            line = line.strip()
            if line.startswith('"title"') or line.startswith("'title'"):
                try:
                    parts = line.split(':', 1)[1].strip()
                    result["title"] = parts.strip('",\'' )
                except (ValueError, IndexError):
                    pass
            elif line.startswith('"description"') or line.startswith("'description'"):
                try:
                    parts = line.split(':', 1)[1].strip()
                    result["description"] = parts.strip('",\'' )
                except (ValueError, IndexError):
                    pass
            elif line.startswith('"difficulty"') or line.startswith("'difficulty'"):
                try:
                    parts = line.split(':', 1)[1].strip()
                    result["difficulty"] = parts.strip('",\'' )
                except (ValueError, IndexError):
                    pass
        
        return result


class NarrativePerturbation:
    """Axis 1: Modify variable names, thematic backgrounds, inject irrelevant context"""
    
    THEMES = [
        ("stock", "inventory"),
        ("array", "sequence"),
        ("path", "route"),
        ("graph", "network"),
        ("tree", "hierarchy"),
        ("game", "competition"),
        ("battle", "match"),
        ("city", "location"),
        ("person", "member"),
        ("money", "points"),
    ]
    
    VARIABLE_PATTERNS = [
        ("nums", "arr"), ("nums", "values"), ("nums", "data"),
        ("s", "str"), ("s", "text"), ("s", "content"),
        ("n", "size"), ("n", "length"), ("n", "count"),
        ("target", "goal"), ("target", "objective"),
        ("k", "threshold"), ("k", "limit"),
        ("x", "item"), ("x", "elem"),
    ]
    
    CONTEXT_INJECTIONS = [
        "In a futuristic setting, ",
        "During the annual competition, ",
        "As part of a complex system, ",
        "Inspired by real-world scenarios, ",
        "In a theoretical model, ",
    ]
    
    @classmethod
    def transform(cls, problem: Problem) -> Problem:
        new_prob = Problem.from_dict(problem.to_dict())
        
        for old, new in cls.THEMES:
            if old.lower() in new_prob.description.lower():
                new_prob.description = re.sub(
                    rf'\b{old}\b', new, new_prob.description, flags=re.IGNORECASE
                )
        
        for old, new in cls.VARIABLE_PATTERNS:
            new_prob.description = re.sub(
                rf'\b{old}\b', new, new_prob.description
            )
            new_prob.input_format = re.sub(
                rf'\b{old}\b', new, new_prob.input_format
            )
        
        if random.random() < 0.3:
            context = random.choice(cls.CONTEXT_INJECTIONS)
            new_prob.description = context + new_prob.description
        
        return new_prob


class RuleModification:
    """Axis 2: Alter operational rules or boundary conditions"""
    
    RULE_TRANSFORMS = [
        (r'\bincreasing\b', 'non-decreasing'),
        (r'\bstrictly\s+greater\b', 'greater or equal'),
        (r'\bgreater\s+than\b', 'greater than or equal to'),
        (r'\bless\s+than\b', 'less than or equal to'),
        (r'\bnon-decreasing\b', 'strictly increasing'),
        (r'\bgreater\s+than\s+or\s+equal\b', 'greater than'),
        (r'\bexactly\s+k\b', 'at most k'),
        (r'\bat\s+most\b', 'at least'),
        (r'\bincluding\b', 'excluding'),
        (r'\bcontain\b', 'do not contain'),
    ]
    
    @classmethod
    def transform(cls, problem: Problem) -> Problem:
        new_prob = Problem.from_dict(problem.to_dict())
        
        for pattern, replacement in cls.RULE_TRANSFORMS:
            if re.search(pattern, new_prob.description, re.IGNORECASE):
                new_prob.description = re.sub(
                    pattern, replacement, new_prob.description, flags=re.IGNORECASE
                )
                break
        
        return new_prob


class EfficiencyScaling:
    """Axis 3: Change input scale to require different algorithmic approaches"""
    
    SCALE_FACTORS = {
        "small": (10, 50),
        "medium": (100, 1000),
        "large": (10**4, 10**5),
        "very_large": (10**5, 10**6),
    }
    
    @classmethod
    def transform(cls, problem: Problem, target_scale: str = "large") -> Problem:
        new_prob = Problem.from_dict(problem.to_dict())
        
        min_val, max_val = cls.SCALE_FACTORS.get(target_scale, cls.SCALE_FACTORS["large"])
        
        new_constraints = []
        for constraint in new_prob.constraints:
            constraint = re.sub(
                r'n\s*=\s*\d+', 
                f'n = {random.randint(min_val, max_val)}', 
                constraint,
                flags=re.IGNORECASE
            )
            constraint = re.sub(
                r'≤\s*\d+',
                f'≤ {max_val}',
                constraint
            )
            new_constraints.append(constraint)
        
        new_prob.constraints = new_constraints
        new_prob.description += f" Note: With n up to {max_val}, O(n²) solutions may not pass."
        
        return new_prob


class SequentialComposition:
    """Axis 4: Chain multiple algorithmic steps"""
    
    CHAINABLE_OPS = [
        "compute LIS",
        "compute prefix sum",
        "compute suffix sum",
        "find maximum subarray",
        "compute factorial",
        "find GCD",
        "compute modular exponentiation",
    ]
    
    @classmethod
    def transform(cls, problem: Problem) -> Problem:
        new_prob = Problem.from_dict(problem.to_dict())
        
        chain_op = random.choice(cls.CHAINABLE_OPS)
        
        new_prob.description += f" Furthermore, after the main computation, {chain_op} is required."
        new_prob.tags = new_prob.tags + ["sequential"]
        
        return new_prob


class ConceptFusion:
    """Axis 5: Merge distinct algorithmic concepts"""
    
    FUSION_PAIRS = [
        (["dynamic-programming"], ["graph", "shortest-path"]),
        (["greedy"], ["string", "parsing"]),
        (["sorting"], ["binary-search"]),
        (["dynamic-programming"], ["game-theory"]),
        (["graph", "bfs"], ["dynamic-programming"]),
    ]
    
    @classmethod
    def transform(cls, problem: Problem) -> Problem:
        new_prob = Problem.from_dict(problem.to_dict())
        
        base_concepts, add_concepts = random.choice(cls.FUSION_PAIRS)
        
        has_base = any(c in new_prob.tags for c in base_concepts)
        
        if has_base:
            new_tags = list(set(new_prob.tags + add_concepts))
            new_prob.tags = new_tags
            new_prob.description += f" Additionally, the solution must consider {', '.join(add_concepts)} aspects."
        
        return new_prob


class ProblemAugmenter:
    """Main class for augmenting problems using multiple axes and LLM"""
    
    def __init__(self, seed_problem: Problem):
        self.seed = seed_problem
        self.llm_augmenter = LLMAugmenter()
    
    def augment(self, 
                 axes: Optional[List[str]] = None,
                 use_llm: bool = False,
                 llm_transformation: str = "all",
                 narrative: bool = True,
                 rule: bool = True,
                 efficiency: bool = True,
                 sequential: bool = True,
                 fusion: bool = True) -> Dict:
        """
        Apply selected augmentation axes to create a new problem.
        
        Args:
            axes: Specific axes to apply (overrides individual flags)
            use_llm: Use LLM for transformation instead of rule-based
            llm_transformation: Type of LLM transformation ("narrative", "rule", "efficiency", "sequential", "fusion", "all")
            narrative: Apply narrative perturbation
            rule: Apply rule modification
            efficiency: Apply efficiency scaling
            sequential: Apply sequential composition
            fusion: Apply concept fusion
            
        Returns:
            Augmented problem as dict
        """
        if use_llm:
            result = self.llm_augmenter.transform(self.seed, llm_transformation)
            result["augmentation_history"] = [f"llm_{llm_transformation}"]
            result["seed_title"] = self.seed.title
            return result
        
        if axes is None:
            axes_to_apply = []
            if narrative:
                axes_to_apply.append("narrative")
            if rule:
                axes_to_apply.append("rule")
            if efficiency:
                axes_to_apply.append("efficiency")
            if sequential:
                axes_to_apply.append("sequential")
            if fusion:
                axes_to_apply.append("fusion")
        
        problem = Problem.from_dict(self.seed.to_dict())
        applied = []
        
        for axis in axes_to_apply:
            if axis == "narrative":
                problem = NarrativePerturbation.transform(problem)
                applied.append("narrative_perturbation")
            elif axis == "rule":
                problem = RuleModification.transform(problem)
                applied.append("rule_modification")
            elif axis == "efficiency":
                problem = EfficiencyScaling.transform(problem)
                applied.append("efficiency_scaling")
            elif axis == "sequential":
                problem = SequentialComposition.transform(problem)
                applied.append("sequential_composition")
            elif axis == "fusion":
                problem = ConceptFusion.transform(problem)
                applied.append("concept_fusion")
        
        result = problem.to_dict()
        result["augmentation_history"] = applied
        result["seed_title"] = self.seed.title
        
        return result
    
    @classmethod
    def augment_from_file(cls, 
                          input_path: str, 
                          output_path: str,
                          use_llm: bool = False,
                          llm_transformation: str = "all",
                          **kwargs) -> None:
        """Read seed problem from JSON, augment, and save result"""
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        seed = Problem.from_dict(data)
        augmenter = cls(seed)
        augmented = augmenter.augment(
            use_llm=use_llm,
            llm_transformation=llm_transformation,
            **kwargs
        )
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(augmented, f, ensure_ascii=False, indent=2)


def demo():
    """Demonstrate both rule-based and LLM-based augmentation"""
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
                "explanation": "The LIS is [1,3,2,4,5] with length 4"
            }
        ],
        "difficulty": "Medium",
        "tags": ["dynamic-programming", "binary-search"]
    }
    
    seed = Problem.from_dict(sample_seed)
    augmenter = ProblemAugmenter(seed)
    
    print("=" * 60)
    print("SEED PROBLEM:")
    print("=" * 60)
    print(json.dumps(sample_seed, indent=2))
    
    print("\n" + "=" * 60)
    print("RULE-BASED AUGMENTED PROBLEM:")
    print("=" * 60)
    rule_based = augmenter.augment(use_llm=False)
    print(json.dumps(rule_based, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    demo()