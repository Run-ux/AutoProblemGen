# Algorithm Problem Quality Evaluator

使用大模型评估算法题目质量的工具，从4个维度对新题目进行打分和评价。

## 功能特性

评估器从以下4个维度对新题目进行评分（0-100分）：

1. **可解性 (Solvability)** - 题目是否有有效解，逻辑是否一致
2. **清晰度 (Clarity)** - 题目描述是否清晰易懂，输入输出格式是否明确
3. **新颖度 (Novelty)** - 新题目与种子题目的差异程度，是否有实质性变化
4. **难度 (Difficulty)** - 难度是否合适，与标注难度是否匹配

## 安装依赖

```bash
pip install openai python-dotenv
```

## 配置环境变量

在 `.env` 文件中配置你的API信息：

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=your_base_url_here
MODEL_NAME=gpt-4o-mini
MAX_TOKENS=4000
TEMPERATURE=0.2
```

## 使用方法

### 方法1：直接运行demo

```bash
python evaluator.py
```

### 方法2：从文件评估

```python
from evaluator import ProblemEvaluator

evaluator = ProblemEvaluator()
evaluator.evaluate_from_files(
    seed_path="seed_problem.json",
    new_path="new_problem.json",
    output_path="evaluation_result.json"
)
```

### 方法3：代码中使用

```python
from evaluator import ProblemEvaluator

evaluator = ProblemEvaluator()

seed_problem = {
    "title": "Longest Increasing Subsequence",
    "description": "Given an array nums, find the length of the longest strictly increasing subsequence.",
    "input_format": "First line: n (1 ≤ n ≤ 1000)\nSecond line: n integers",
    "output_format": "A single integer - the length of LIS",
    "constraints": ["1 ≤ n ≤ 1000", "0 ≤ nums[i] ≤ 10^6"],
    "examples": [{"input": "5\n1 3 2 4 5", "output": "4", "explanation": "The LIS is [1,2,4,5] with length 4"}],
    "difficulty": "Medium",
    "tags": ["dynamic-programming", "binary-search"]
}

new_problem = {
    # ... 新题目数据
}

result = evaluator.evaluate(seed_problem, new_problem)
print(f"Overall Score: {result.overall_score}/100")
```

## 输出格式

评估结果包含以下字段：

```json
{
  "solvability": 85,
  "clarity": 90,
  "novelty": 45,
  "difficulty": 80,
  "overall_score": 74.75,
  "solvability_reasoning": "题目逻辑一致，有明确解法...",
  "clarity_reasoning": "描述清晰，输入输出格式明确...",
  "novelty_reasoning": "与原题目差异较小，主要是变量名变化...",
  "difficulty_reasoning": "难度标注准确，约束合理...",
  "overall_comment": "整体质量良好，但新颖度有待提升..."
}
```

## 评分标准

- **90-100分**: 优秀 - 各方面表现卓越
- **75-89分**: 良好 - 大部分标准达标，有轻微问题
- **60-74分**: 可接受 - 满足基本要求，有明显缺陷
- **40-59分**: 较差 - 存在严重影响质量的问题
- **0-39分**: 不可接受 - 存在重大缺陷，无法使用

## 综合评分权重

- 可解性: 30%
- 清晰度: 25%
- 新颖度: 25%
- 难度: 20%

## 注意事项

1. 新颖度评分特别强调：如果只是简单的变量名替换或主题更换，新颖度分数会很低（40分以下）
2. 可解性评分关注题目是否真正可解，逻辑是否自洽
3. 清晰度评分关注题目描述是否让程序员能够理解要求
4. 难度评分会综合考虑实际复杂度和标注难度的一致性