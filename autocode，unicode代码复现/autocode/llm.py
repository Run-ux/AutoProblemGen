import os
import json
from typing import Optional, Dict, Any
from openai import OpenAI

class LLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o",
        max_tokens: Optional[int] = None
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.model = model
        self.max_tokens = self._resolve_max_tokens(max_tokens)
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or pass it explicitly.")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url if self.base_url else None
        )

    @staticmethod
    def _resolve_max_tokens(max_tokens: Optional[int]) -> int:
        value = max_tokens if max_tokens is not None else os.environ.get("MAX_TOKENS", 16000)
        try:
            resolved = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("MAX_TOKENS must be a positive integer.") from exc

        if resolved <= 0:
            raise ValueError("MAX_TOKENS must be a positive integer.")
        return resolved
    
    def generate_problem(self, seed_problem: Dict[str, Any], transformation_type: str = "random") -> Dict[str, Any]:
        system_prompt = """
You are a competitive programming problem setter. Your task is to generate a new problem based on a given seed problem.

Rules:
1. Read the seed problem carefully
2. Apply transformation to create a new, distinct problem
3. The new problem should be solvable and have a clear solution
4. Keep the structure similar but change the key elements

Transformation types you can use:
- ADD_CONSTRAINT: Add a new constraint to the problem
- REMOVE_CONSTRAINT: Remove or relax an existing constraint
- MODIFY_CONDITION: Change the problem's objective or condition
- CHANGE_DOMAIN: Shift the problem domain (array → tree, graph, matrix, string)
- ADD_OPERATION: Add allowed operations to the problem
- INCREASE_DIMENSION: Increase the dimensionality of the problem
- CHANGE_OBJECTIVE: Change from maximize to minimize or vice versa

Output format (JSON only, no markdown):
{
  "title": "New Problem Title",
  "description": "New problem description",
  "input_description": "Input format description",
  "output_description": "Output format description",
  "difficulty": 1500,
  "tags": ["tag1", "tag2"]
}
"""
        
        user_prompt = f"""
Seed Problem:
{json.dumps(seed_problem, ensure_ascii=False, indent=2)}

Transformation type: {transformation_type}

Please generate a new problem based on the seed problem and transformation type.
Follow the output format exactly.
"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=self.max_tokens
        )
        
        content = response.choices[0].message.content.strip()
        
        try:
            start = content.index('{')
            end = content.rindex('}') + 1
            json_str = content[start:end]
            return json.loads(json_str)
        except (ValueError, json.JSONDecodeError):
            return self._parse_fallback(content)
    
    def _parse_fallback(self, content: str) -> Dict[str, Any]:
        lines = content.split('\n')
        result = {
            "title": "Generated Problem",
            "description": content,
            "input_description": "",
            "output_description": "",
            "difficulty": 1500,
            "tags": []
        }
        
        for line in lines:
            line = line.strip()
            if line.startswith('title') or line.startswith('Title'):
                result["title"] = line.split(':', 1)[1].strip().strip('"').strip("'")
            elif line.startswith('difficulty') or line.startswith('Difficulty'):
                try:
                    result["difficulty"] = int(line.split(':', 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith('tags') or line.startswith('Tags'):
                try:
                    tags_str = line.split(':', 1)[1].strip()
                    if tags_str.startswith('[') and tags_str.endswith(']'):
                        result["tags"] = [t.strip().strip('"').strip("'") for t in tags_str[1:-1].split(',')]
                except (ValueError, IndexError):
                    pass
        
        return result
    
    def generate_multiple_transformations(self, seed_problem: Dict[str, Any], num_transformations: int = 2) -> Dict[str, Any]:
        system_prompt = """
You are a competitive programming problem setter. Your task is to generate a new problem by applying multiple transformations to a seed problem.

Rules:
1. Read the seed problem carefully
2. Apply multiple transformations in sequence to create a significantly different problem
3. The new problem should be solvable and have a clear solution
4. Each transformation should build on the previous one
5. Keep the problem structure consistent with competitive programming standards

Common transformation sequences:
- ADD_CONSTRAINT → CHANGE_OBJECTIVE
- CHANGE_DOMAIN → ADD_OPERATION  
- INCREASE_DIMENSION → MODIFY_CONDITION
- REMOVE_CONSTRAINT → ADD_OPERATION → CHANGE_OBJECTIVE

Output format (JSON only):
{
  "title": "New Problem Title",
  "description": "New problem description",
  "input_description": "Input format description",
  "output_description": "Output format description",
  "difficulty": 1500,
  "tags": ["tag1", "tag2"],
  "transformations_applied": ["transformation1", "transformation2"]
}
"""
        
        user_prompt = f"""
Seed Problem:
{json.dumps(seed_problem, ensure_ascii=False, indent=2)}

Number of transformations: {num_transformations}

Please generate a new problem by applying {num_transformations} transformations to the seed problem.
Follow the output format exactly.
"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.8,
            max_tokens=self.max_tokens
        )
        
        content = response.choices[0].message.content.strip()
        
        try:
            start = content.index('{')
            end = content.rindex('}') + 1
            json_str = content[start:end]
            return json.loads(json_str)
        except (ValueError, json.JSONDecodeError):
            return self._parse_fallback(content)
