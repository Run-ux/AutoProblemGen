import random
from typing import List, Dict, Any
from .schema import Problem
from .llm import LLMClient

class LLMTransformationEngine:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.transformation_types = [
            "ADD_CONSTRAINT",
            "REMOVE_CONSTRAINT", 
            "MODIFY_CONDITION",
            "CHANGE_DOMAIN",
            "ADD_OPERATION",
            "INCREASE_DIMENSION",
            "CHANGE_OBJECTIVE",
            "MODIFY_OUTPUT_FORMAT"
        ]
    
    def apply_transformation(self, problem: Problem, transformation_type: str = "random") -> Problem:
        if transformation_type == "random":
            transformation_type = random.choice(self.transformation_types)
        
        generated_data = self.llm_client.generate_problem(
            problem.to_dict(), transformation_type
        )
        
        return self._create_problem_from_llm(generated_data, problem, transformation_type)
    
    def apply_multiple_transformations(self, problem: Problem, num_transformations: int = 1) -> Problem:
        if num_transformations == 1:
            return self.apply_transformation(problem)
        
        generated_data = self.llm_client.generate_multiple_transformations(
            problem.to_dict(), num_transformations
        )
        
        transformations_applied = generated_data.get("transformations_applied", [])
        transformation_type = "+".join(transformations_applied) if transformations_applied else "llm_multi"
        
        return self._create_problem_from_llm(generated_data, problem, transformation_type)
    
    def _create_problem_from_llm(self, generated_data: Dict[str, Any], 
                                 original_problem: Problem, transformation_type: str) -> Problem:
        return Problem(
            title=generated_data.get("title", "Generated Problem"),
            description=generated_data.get("description", ""),
            constraints=original_problem.constraints,
            input_description=generated_data.get("input_description", original_problem.input_description),
            output_description=generated_data.get("output_description", original_problem.output_description),
            examples=original_problem.examples,
            difficulty=generated_data.get("difficulty", original_problem.difficulty + 100),
            tags=generated_data.get("tags", original_problem.tags),
            original_seed=original_problem.title,
            transformation_type=transformation_type
        )