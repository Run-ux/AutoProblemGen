from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

@dataclass
class TestCase:
    input: str
    output: str

@dataclass  
class ProblemConstraints:
    time_limit: str = "2 seconds"
    memory_limit: str = "256 megabytes"
    input_format: str = ""
    output_format: str = ""

@dataclass
class Problem:
    title: str
    description: str
    constraints: ProblemConstraints = field(default_factory=ProblemConstraints)
    input_description: str = ""
    output_description: str = ""
    examples: List[TestCase] = field(default_factory=list)
    difficulty: int = 1000
    tags: List[str] = field(default_factory=list)
    original_seed: Optional[str] = None
    transformation_type: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "constraints": {
                "time_limit": self.constraints.time_limit,
                "memory_limit": self.constraints.memory_limit,
                "input_format": self.constraints.input_format,
                "output_format": self.constraints.output_format
            },
            "input_description": self.input_description,
            "output_description": self.output_description,
            "examples": [{"input": e.input, "output": e.output} for e in self.examples],
            "difficulty": self.difficulty,
            "tags": self.tags,
            "original_seed": self.original_seed,
            "transformation_type": self.transformation_type
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Problem":
        constraints_data = data.get("constraints", {})
        constraints = ProblemConstraints(
            time_limit=constraints_data.get("time_limit", "2 seconds"),
            memory_limit=constraints_data.get("memory_limit", "256 megabytes"),
            input_format=constraints_data.get("input_format", ""),
            output_format=constraints_data.get("output_format", "")
        )
        examples = [TestCase(input=e["input"], output=e["output"]) 
                   for e in data.get("examples", [])]
        return cls(
            title=data["title"],
            description=data["description"],
            constraints=constraints,
            input_description=data.get("input_description", ""),
            output_description=data.get("output_description", ""),
            examples=examples,
            difficulty=data.get("difficulty", 1000),
            tags=data.get("tags", []),
            original_seed=data.get("original_seed"),
            transformation_type=data.get("transformation_type")
        )