# 生成测试用例和标准解法

本目录实现从上游 artifact 构建 LLM prompt，并通过 OpenAI 兼容 Chat Completions API 真实生成以下产物：

- 标准解
- 小规模真值 oracle（暴力解）
- 随机测试输入生成器
- 对抗测试输入生成器
- 小规模挑战测试输入
- checker
- 固定类别错误解
- 基于 schema 错误策略分析的错误解

## 范围边界

- 已实现：artifact 字段抽取、prompt 模块、LLM API 调用、严格 JSON 解析、JSON 输出合同校验、生成后本地验证闭环、错误解池增强验证、单元测试。
- 未实现：题包流水线、CLI、旧项目迁移。
- 不复用 `D:\AutoProblemGen\测试用例和标准解法共迭代` 的代码实现。

## 配置来源

安装依赖：

```powershell
pip install -r requirements.txt
```

本模块不再维护模块级 `.env.example`，也不再读取本地 `.env`。主线入口由总流程统一调用：

```powershell
python D:\AutoProblemGen\总流程\main.py --workflow-config D:\AutoProblemGen\总流程\workflow.env
```

说明：

- generation LLM 配置来自 `总流程/generation_llm.env`，用于标准解、小规模真值 oracle（暴力解）、测试输入、checker 和错误解池生成。
- 执行限制来自 `总流程/workflow.env` 中的 `EXECUTION_*` 字段，用于约束本地子进程执行生成器、小规模真值 oracle（暴力解）和 checker 的时间/空间限制；`STANDARD_SOLUTION_MAX_REPAIR_ITERATIONS` 控制标准解 debug 最大候选生成轮数，拒绝候选同样计数。
- `generate_all_artifacts` 必须接收总流程传入的 `LLMConfig` 或显式 client。
- `generate_verified_artifacts` 必须额外接收总流程传入的 `ExecutionConfig`。
- 缺少 LLM 配置或执行限制时会 fail-fast，不会尝试读取模块本地配置文件。
- 初始 LLM 产物生成会并行执行彼此独立的标准解、暴力解、输入生成器、checker、固定类别错误解和错误策略分析任务；模块内部默认最多同时执行 8 个初始生成任务，不新增配置项。

## 库函数入口

```python
from generation_pipeline import generate_all_artifacts
from llm_config import LLMConfig

config = LLMConfig.from_endpoint(generation_endpoint_config)
result = generate_all_artifacts(artifact, config)
```

只生成产物时使用 `generate_all_artifacts`。需要执行需求 1-5 的验证闭环时使用：

```python
from generation_pipeline import generate_verified_artifacts
from execution_config import ExecutionConfig
from llm_config import LLMConfig

config = LLMConfig.from_endpoint(generation_endpoint_config)
execution_config = ExecutionConfig.from_runtime_limits(execution_limits)
result = generate_verified_artifacts(artifact, config, execution_config=execution_config)
```

返回结构：

```python
{
    "standard_solution": {...},
    "bruteforce_solution": {...},
    "test_inputs": {
        "random": {...},
        "adversarial": {...},
        "small_challenge": {...},
    },
    "checker": {...},
    "wrong_solutions": {
        "fixed_categories": {...},
        "strategy_analysis": {...},
        "strategy_based": [...],
    },
    "metadata": {...},
}
```

`generate_verified_artifacts` 在上述结构基础上额外返回：

```python
{
    "verified_test_inputs": {
        "status": "ok",
        "cases": [...],
        "count": 30,  # 基础输入数量；错误解池阶段可能追加 targeted 输入
        "source_counts": {
            "random": 10,
            "adversarial": 10,
            "small_challenge": 10,
        },
        "test_input_repair_history": [],
        "test_input_repair_iteration_count": 0,
    },
    "bruteforce_verification": {
        "status": "ok",
        "final_code": "...",
        "solved_cases": [...],
        "large_scale_inputs": [...],
        "repair_history": [...],
    },
    "checker_verification": {...},
    "standard_solution_verification": {...},
    "large_scale_truth_outputs": {
        "status": "ok",
        "cases": [...],
        "count": 0,
        "attempted_count": 0,
        "failed_cases": [...],
        "failure_count": 0,
    },
    "wrong_solution_pool_verification": {...},
    "execution_metadata": {...},
}
```

验证入口会把修复后的标准解写回 `standard_solution.code`，并保留 `standard_solution.initial_code`；会把修复后的暴力解法写回 `bruteforce_solution.code`，并保留 `bruteforce_solution.initial_code`；需要 checker 且完成验证时，也会把修复后的 checker 写回 `checker.checker_code`，并保留 `checker.initial_checker_code`。

调用默认启用 `response_format={"type": "json_object"}`。普通生成入口会并行执行无依赖的初始 prompt，并解析和校验 LLM 返回的 JSON；若返回非法 JSON、缺字段或字段类型不符合合同，会把错误摘要和截断后的原始响应反馈给同一 prompt，最多额外重试 2 轮。验证入口会在受限子进程中执行生成代码，但不落盘。

## 验证闭环行为

- 验证闭环仍按数据依赖顺序执行：先完成初始 LLM 生成，再收集输入、验证暴力解、验证 checker、增强错误解池、验证标准解和生成大规模真值。
- 输入收集：随机输入和对抗输入各运行生成器 10 次，并通过各自 `validate_test_input`；若生成器运行失败、返回值不是非空字符串，或 validate 误拒生成输入，会调用测试输入 debug prompt 重新生成整组 `constraint_analysis/generate_test_input_code/validate_test_input_code`，每个来源最多额外修复 2 轮，成功后从该来源第 1 条重新收集 10 条，并把修复后的 payload 写回 `test_inputs`。小规模挑战输入使用初始返回加 9 次额外 LLM 调用凑满 10 条，并用修复后的随机输入 validate 函数校验。
- 小规模真值 oracle（暴力解）：对 30 条输入逐一运行 `solve`。它只要求为小规模合法输入产出可信真值，不要求覆盖题面最大输入规模。编译错误、接口错误和可缩小到小规模的运行时错误会触发暴力 debug LLM 修复，并从头重新验证；超时或超内存输入会归为 `large_scale_inputs`，不触发 debug。
- 真值用例：最终只保留小规模真值 oracle 能正常返回字符串输出的 `solved_cases`，数量允许少于已验证输入总数；`large_scale_inputs` 和 `large_scale_runtime_failures` 后续由标准解生成真值。
- checker：当 `needs_checker=false` 时跳过 checker 闭环；当需要 checker 时，先用 `solved_cases` 验证不误拒合法输出，再由反例生成 LLM 构造错误输出集合验证不误收非法输出。
- 标准解：错误解池补测后，用全部 `solved_cases` 验证标准解。无 checker 题做输出字符串精确比对；有 checker 题使用修复后的 checker 判定标准解输出。流水线始终维护失败数最少的当前最佳版本；每个 LLM 修复结果只作为候选，全量重跑后必须同时满足“未破坏当前已通过用例”和“失败数严格下降”才会被采纳，否则记录原因并回退。debug prompt 最多携带 10 条代表性失败用例、3 条按来源和输入输出规模选择的通过锚点，以及历次修复摘要；最近两次尝试额外携带相对当时最佳版本的统一 diff。
- 大规模真值：标准解通过小规模真值后，运行 `large_scale_inputs` 和 `large_scale_runtime_failures` 并把标准解输出写入 `large_scale_truth_outputs`；若标准解超时或超内存，会记录到 `failed_cases` 并继续后续大规模输入；若标准解运行错误或未返回字符串，会 fail-fast，不产出可疑真值。
- 标准解执行限制：从 `generated_problem.constraints` 解析带明确标签的题面限制，例如 `时间限制: 2s`、`time limit: 2 seconds`、`空间限制: 512MB`、`memory limit: 256 MB`。缺少时间或空间限制时会 fail-fast。
- 修复循环：标准解修复轮数由 `STANDARD_SOLUTION_MAX_REPAIR_ITERATIONS` 控制，表示候选生成次数，拒绝候选同样计数。达到上限仍失败会 fail-fast，并在失败 JSON 的 `details` 中保留历史最佳代码、最佳版本失败摘要和完整 `repair_history`；暴力解法、checker 误拒和 checker 误收修复仍不设轮数上限，直到本地执行结果通过对应阶段。
- 错误解池增强：基础 checker 验证完成后，默认执行单题临时错误解池；无 checker 题使用输出字符串差异识别错误解问题，有 checker 题只使用已修复 checker 判定错误解输出是否暴露问题。
- 定向补测：错误解池会为全部当前尚未暴露问题的错误解生成单条 targeted 输入；输入通过现有 validate 函数且暴力解能产出真值时，会追加到 `verified_test_inputs` 和 `solved_cases`。当原始未暴露问题的错误解累计暴露比例达到 0.8，或某轮没有新增有效输入时停止。

## Artifact 字段

题面字段只从 `generated_problem` 中读取以下字段：

- `title`
- `description`
- `input_format`
- `output_format`
- `constraints`
- `samples`
- `notes`

其中 `constraints` 还必须包含标准解执行所需的题面时间和空间限制，且要带明确标签和单位。当前支持 `ms/s/seconds/秒` 和 `KB/MB/GB`。

需要题目结构信息的 prompt 额外读取 `new_schema_snapshot` 的以下字段；当前标准解、暴力解、checker、schema 错误策略分析和按策略错误解会读取这些字段：

- `input_structure`
- `core_constraints`
- `objective`
- `invariant`

字段缺失时会抛出 `ValueError`。本模块只读取 `output_format`，不兼容 `ouput_format`。

## Prompt 模块

每个 prompt 模块统一暴露：

```python
def build_system_prompt() -> str:
    ...

def build_user_prompt(...) -> str:
    ...
```

模块分组如下：

- `prompts.tool_generation.prompt_random_test_input`
- `prompts.tool_generation.prompt_adversarial_test_input`
- `prompts.tool_generation.prompt_small_challenge_test_input`
- `prompts.tool_generation.prompt_checker`
- `prompts.standard_solution.prompt_standard_solution`
- `prompts.bruteforce_solution.prompt_bruteforce_solution`
- `prompts.verification.prompt_bruteforce_debug`
- `prompts.verification.prompt_standard_solution_debug`
- `prompts.verification.prompt_checker_counterexample`
- `prompts.verification.prompt_checker_false_accept_debug`
- `prompts.verification.prompt_checker_false_reject_debug`
- `prompts.verification.prompt_test_input_debug`
- `prompts.tool_generation.prompt_wrong_solution_targeted_test_input`
- `prompts.wrong_solution.prompt_fixed_category_wrong_solution`
- `prompts.wrong_solution.prompt_schema_mistake_analysis`
- `prompts.wrong_solution.prompt_strategy_wrong_solution`

## JSON 输出合同

所有 prompt 都要求 LLM 最终只输出单个 JSON 对象，不允许 JSON 外解释或 Markdown 代码块。流水线会严格 `json.loads`；遇到 JSON/字段合同错误时只通过重新调用 LLM 修复，不在本地拼接或猜测脏文本。

- 随机/对抗测试输入：`constraint_analysis`、`generate_test_input_code`、`validate_test_input_code`。生成代码使用 `cyaron==0.7.0`；需要打乱列表时使用标准库 `random.shuffle`，不要调用 `cyaron.shuffle`。
- 小规模挑战输入：`test_input`
- 标准解：`status`、`block_reason`、`solution_markdown`、`code`、`time_complexity`、`space_complexity`
- 暴力解：`status`、`block_reason`、`bruteforce_markdown`、`code`、`time_complexity`、`space_complexity`
- checker：不需要时返回 `needs_checker=false`、`reason`；需要时返回 `needs_checker=true`、`output_rule_analysis`、`checker_code`、`notes`
- 标准解 debug：`analysis`、`fix_plan`、`code`
- 暴力 debug：`code`
- checker 误拒/误收修复：`analysis`、`fix_plan`、`checker_code`
- checker 反例生成：`counterexamples`、`skipped`；进入 `counterexamples` 的反例 `confidence` 必须大于等于 `0.85`
- 错误解池定向输入：`test_input`
- schema 错误策略分析：`strategies` 列表，每项包含 `title`、`wrong_idea`、`plausible_reason`、`failure_reason`、`trigger_case`
- 固定错误解/按策略错误解：`code`

解法类代码统一要求实现：

```python
def solve(input_str: str) -> str:
    ...
```

checker 代码统一要求实现：

```python
def check_output(input_string, output_string) -> bool:
    ...
```

## 测试

```powershell
python -m unittest discover -s tests
```
