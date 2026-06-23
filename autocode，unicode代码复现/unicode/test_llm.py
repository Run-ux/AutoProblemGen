from augmenter import ProblemAugmenter

ProblemAugmenter.augment_from_file(
    "seed_problem.json",
    "augmented_rule.json",
    use_llm=False
)
print("Rule-based augmentation complete")

ProblemAugmenter.augment_from_file(
    "seed_problem.json",
    "augmented_llm.json",
    use_llm=True,
    llm_transformation="all"
)
print("LLM-based augmentation complete")