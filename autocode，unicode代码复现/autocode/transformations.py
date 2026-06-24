import random
from typing import List, Dict, Any
try:
    from .schema import Problem, ProblemConstraints, TestCase
except ImportError:
    from schema import Problem, ProblemConstraints, TestCase

class TransformationEngine:
    def __init__(self):
        self.transformations = [
            self.add_constraint,
            self.remove_constraint, 
            self.modify_constraint,
            self.add_condition,
            self.modify_condition,
            self.change_domain,
            self.change_objective,
            self.increase_dimension,
            self.add_operation,
            self.modify_output_format
        ]
    
    def apply_transformation(self, problem: Problem) -> Problem:
        transformation = random.choice(self.transformations)
        return transformation(problem)
    
    def apply_multiple_transformations(self, problem: Problem, num_transformations: int = 1) -> Problem:
        result = problem
        used_transformations = []
        for _ in range(num_transformations):
            available = [t for t in self.transformations if t.__name__ not in used_transformations]
            if not available:
                break
            transformation = random.choice(available)
            result = transformation(result)
            used_transformations.append(transformation.__name__)
        result.transformation_type = '+'.join(used_transformations)
        result.original_seed = problem.title
        return result
    
    def add_constraint(self, problem: Problem) -> Problem:
        new_constraints = [
            "Additionally, all elements in the array must be distinct.",
            "Additionally, the array must be sorted in non-decreasing order.",
            "Additionally, the sum of all elements must not exceed 10^9.",
            "Additionally, the array must contain at least one even number.",
            "Additionally, no element can be zero.",
            "Additionally, the first element must be equal to the last element.",
            "Additionally, the array must be a permutation of 1 to n.",
            "Additionally, all elements must be positive integers.",
            "Additionally, adjacent elements must differ by at most 1.",
            "Additionally, the array must have at least one peak element (greater than neighbors)."
        ]
        
        selected = random.choice(new_constraints)
        new_description = problem.description + "\n\n" + selected
        new_difficulty = problem.difficulty + random.randint(50, 200)
        
        return Problem(
            title=problem.title + " (Constrained)",
            description=new_description,
            constraints=problem.constraints,
            input_description=problem.input_description,
            output_description=problem.output_description,
            examples=problem.examples,
            difficulty=new_difficulty,
            tags=problem.tags + ["constraint"],
            original_seed=problem.original_seed,
            transformation_type="add_constraint"
        )
    
    def remove_constraint(self, problem: Problem) -> Problem:
        constraint_patterns = [
            ("distinct", "all elements are distinct"),
            ("sorted", "sorted in non-decreasing order"),
            ("positive", "all elements must be positive"),
            ("non-negative", "all elements must be non-negative"),
            ("permutation", "permutation of 1 to n"),
            ("unique", "all elements are unique"),
            ("even", "contains at least one even"),
            ("odd", "contains at least one odd"),
            ("zero", "no element can be zero"),
            ("peak", "at least one peak element")
        ]
        
        new_description = problem.description
        removed = False
        
        for pattern, desc in constraint_patterns:
            if pattern.lower() in new_description.lower():
                sentences = new_description.split('\n')
                new_sentences = []
                for sentence in sentences:
                    if desc.lower() not in sentence.lower():
                        new_sentences.append(sentence)
                new_description = '\n'.join(new_sentences)
                removed = True
                break
        
        if not removed:
            sentences = new_description.split('. ')
            if len(sentences) > 2:
                remove_idx = random.randint(1, min(3, len(sentences)-1))
                sentences.pop(remove_idx)
                new_description = '. '.join(sentences)
        
        new_difficulty = max(500, problem.difficulty - random.randint(50, 150))
        
        return Problem(
            title=problem.title + " (Relaxed)",
            description=new_description,
            constraints=problem.constraints,
            input_description=problem.input_description,
            output_description=problem.output_description,
            examples=problem.examples,
            difficulty=new_difficulty,
            tags=problem.tags + ["relaxation"],
            original_seed=problem.original_seed,
            transformation_type="remove_constraint"
        )
    
    def modify_constraint(self, problem: Problem) -> Problem:
        modifications = [
            ("minimum", "maximum"),
            ("maximum", "minimum"),
            ("at least", "at most"),
            ("at most", "at least"),
            ("exactly", "at most"),
            ("exactly", "at least"),
            ("non-decreasing", "non-increasing"),
            ("non-increasing", "non-decreasing"),
            ("greater than", "less than"),
            ("less than", "greater than"),
            ("equal to", "not equal to"),
            ("not equal to", "equal to"),
            ("divisible by", "not divisible by"),
            ("not divisible by", "divisible by"),
            ("prime", "composite"),
            ("composite", "prime")
        ]
        
        new_description = problem.description
        
        for old, new in modifications:
            if old.lower() in new_description.lower():
                new_description = new_description.replace(old, new, 1)
                break
        
        new_difficulty = problem.difficulty + random.randint(-50, 100)
        
        return Problem(
            title=problem.title + " (Modified)",
            description=new_description,
            constraints=problem.constraints,
            input_description=problem.input_description,
            output_description=problem.output_description,
            examples=problem.examples,
            difficulty=new_difficulty,
            tags=problem.tags + ["modification"],
            original_seed=problem.original_seed,
            transformation_type="modify_constraint"
        )
    
    def add_condition(self, problem: Problem) -> Problem:
        new_conditions = [
            "After finding the answer, you must also report the number of ways to achieve this answer.",
            "Additionally, you need to output the positions of the selected elements.",
            "Moreover, if there are multiple solutions, output the lexicographically smallest one.",
            "Furthermore, you must ensure that the solution uses at most k operations.",
            "Additionally, you need to find the second best solution as well.",
            "Moreover, you must verify that the solution is unique.",
            "Furthermore, output the solution in a specific order: sorted by value.",
            "Additionally, you need to handle queries offline.",
            "Moreover, you must use an online algorithm with O(1) per query time.",
            "Furthermore, your solution must use constant extra space."
        ]
        
        selected = random.choice(new_conditions)
        new_description = problem.description + "\n\n" + selected
        new_difficulty = problem.difficulty + random.randint(100, 300)
        
        return Problem(
            title=problem.title + " (Extended)",
            description=new_description,
            constraints=problem.constraints,
            input_description=problem.input_description,
            output_description=problem.output_description,
            examples=problem.examples,
            difficulty=new_difficulty,
            tags=problem.tags + ["extension"],
            original_seed=problem.original_seed,
            transformation_type="add_condition"
        )
    
    def modify_condition(self, problem: Problem) -> Problem:
        condition_changes = [
            ("find the maximum", "find the minimum"),
            ("find the minimum", "find the maximum"),
            ("count the number", "find the sum"),
            ("find the sum", "count the number"),
            ("find all", "find any"),
            ("find any", "find all"),
            ("output the answer", "output the answer modulo 10^9+7"),
            ("output the answer", "output the answer as a fraction in simplest form"),
            ("solve for", "solve for in O(n) time"),
            ("solve for", "solve for in O(n log n) time")
        ]
        
        new_description = problem.description
        
        for old, new in condition_changes:
            if old.lower() in new_description.lower():
                new_description = new_description.replace(old, new, 1)
                break
        
        new_difficulty = problem.difficulty + random.randint(-50, 200)
        
        return Problem(
            title=problem.title + " (Condition Changed)",
            description=new_description,
            constraints=problem.constraints,
            input_description=problem.input_description,
            output_description=problem.output_description,
            examples=problem.examples,
            difficulty=new_difficulty,
            tags=problem.tags + ["condition_change"],
            original_seed=problem.original_seed,
            transformation_type="modify_condition"
        )
    
    def change_domain(self, problem: Problem) -> Problem:
        domain_changes = [
            ("array", "string"),
            ("array", "tree"),
            ("array", "graph"),
            ("array", "matrix"),
            ("string", "array"),
            ("string", "tree"),
            ("tree", "graph"),
            ("tree", "array"),
            ("graph", "tree"),
            ("graph", "matrix"),
            ("matrix", "array"),
            ("matrix", "graph")
        ]
        
        new_description = problem.description
        changed = False
        
        for old, new in domain_changes:
            if f" {old} " in new_description.lower():
                new_description = new_description.replace(old, new, 1)
                changed = True
                break
        
        if not changed:
            return problem
        
        new_difficulty = problem.difficulty + random.randint(100, 300)
        
        return Problem(
            title=problem.title + " (Domain Shift)",
            description=new_description,
            constraints=problem.constraints,
            input_description=problem.input_description,
            output_description=problem.output_description,
            examples=problem.examples,
            difficulty=new_difficulty,
            tags=problem.tags + ["domain_shift"],
            original_seed=problem.original_seed,
            transformation_type="change_domain"
        )
    
    def change_objective(self, problem: Problem) -> Problem:
        objective_changes = [
            ("maximize", "minimize"),
            ("minimize", "maximize"),
            ("find the largest", "find the smallest"),
            ("find the smallest", "find the largest"),
            ("find the best", "find the worst"),
            ("find the worst", "find the best"),
            ("find the optimal", "find the suboptimal"),
            ("find the suboptimal", "find the optimal"),
            ("maximize the number", "minimize the number"),
            ("minimize the number", "maximize the number")
        ]
        
        new_description = problem.description
        
        for old, new in objective_changes:
            if old.lower() in new_description.lower():
                new_description = new_description.replace(old, new, 1)
                break
        
        new_difficulty = problem.difficulty + random.randint(-50, 150)
        
        return Problem(
            title=problem.title + " (Objective Changed)",
            description=new_description,
            constraints=problem.constraints,
            input_description=problem.input_description,
            output_description=problem.output_description,
            examples=problem.examples,
            difficulty=new_difficulty,
            tags=problem.tags + ["objective_change"],
            original_seed=problem.original_seed,
            transformation_type="change_objective"
        )
    
    def increase_dimension(self, problem: Problem) -> Problem:
        dimension_changes = [
            ("1-dimensional", "2-dimensional"),
            ("one-dimensional", "two-dimensional"),
            ("single row", "matrix"),
            ("single column", "matrix"),
            ("1D", "2D"),
            ("1-d", "2-d"),
            ("linear", "planar"),
            ("row", "matrix"),
            ("column", "matrix")
        ]
        
        new_description = problem.description
        
        for old, new in dimension_changes:
            if old.lower() in new_description.lower():
                new_description = new_description.replace(old, new, 1)
                break
        
        if "array" in new_description.lower() and "matrix" not in new_description.lower():
            if random.random() > 0.5:
                new_description = new_description.replace("array", "matrix", 1)
        
        new_difficulty = problem.difficulty + random.randint(150, 350)
        
        return Problem(
            title=problem.title + " (Higher Dimension)",
            description=new_description,
            constraints=problem.constraints,
            input_description=problem.input_description,
            output_description=problem.output_description,
            examples=problem.examples,
            difficulty=new_difficulty,
            tags=problem.tags + ["dimension_increase"],
            original_seed=problem.original_seed,
            transformation_type="increase_dimension"
        )
    
    def add_operation(self, problem: Problem) -> Problem:
        new_operations = [
            "You can perform the following operation any number of times: reverse any subarray.",
            "You can perform the following operation any number of times: swap any two adjacent elements.",
            "You can perform the following operation any number of times: rotate the array by one position to the left.",
            "You can perform the following operation any number of times: flip any element (0↔1).",
            "You can perform the following operation any number of times: increment any element by 1.",
            "You can perform the following operation any number of times: delete any element.",
            "You can perform the following operation any number of times: insert any element at any position.",
            "You can perform the following operation any number of times: merge two adjacent elements into their sum.",
            "You can perform the following operation any number of times: split any element into two parts.",
            "You can perform the following operation any number of times: apply bitwise XOR with any value."
        ]
        
        selected = random.choice(new_operations)
        new_description = problem.description + "\n\n" + selected
        new_difficulty = problem.difficulty + random.randint(100, 300)
        
        return Problem(
            title=problem.title + " (Operations Added)",
            description=new_description,
            constraints=problem.constraints,
            input_description=problem.input_description,
            output_description=problem.output_description,
            examples=problem.examples,
            difficulty=new_difficulty,
            tags=problem.tags + ["operations"],
            original_seed=problem.original_seed,
            transformation_type="add_operation"
        )
    
    def modify_output_format(self, problem: Problem) -> Problem:
        format_changes = [
            ("output a single integer", "output all possible answers"),
            ("output all possible answers", "output a single integer"),
            ("output the answer", "output the answer as a binary string"),
            ("output the answer", "output the answer in hexadecimal"),
            ("output the answer", "output the answer modulo 10007"),
            ("output the answer", "output the answer with exactly 6 decimal places"),
            ("output the answer", "output the answer as a fraction a/b"),
            ("output the answer", "output YES or NO instead"),
            ("output YES or NO", "output the answer as an integer"),
            ("output the indices", "output the values"),
            ("output the values", "output the indices")
        ]
        
        new_output = problem.output_description
        
        for old, new in format_changes:
            if old.lower() in new_output.lower():
                new_output = new_output.replace(old, new, 1)
                break
        
        new_difficulty = problem.difficulty + random.randint(-50, 100)
        
        return Problem(
            title=problem.title + " (Output Changed)",
            description=problem.description,
            constraints=problem.constraints,
            input_description=problem.input_description,
            output_description=new_output,
            examples=problem.examples,
            difficulty=new_difficulty,
            tags=problem.tags + ["output_format"],
            original_seed=problem.original_seed,
            transformation_type="modify_output_format"
        )