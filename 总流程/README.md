# AutoProblemGen 总流程运行说明

本目录是 AutoProblemGen 的端到端编排入口，负责串联以下阶段：

1. 调用同级目录 `四元组抽取/extract.py` 抽取题目四元组；默认复用同一输出目录下已有的四元组 raw 结果。
2. 调用同级目录 `生成题面/main.py` 生成新题面并执行质量迭代。
3. 调用本目录 `verification_runner.py`，再转入同级目录 `生成测试用例和标准解法` 生成并验证测试产物。
4. 在输出目录写入日志、阶段结果和 `workflow_summary.json`。

当 `INPUT_PATH` 是目录时，总流程按题串行执行完整流水线：第 1 题完成抽取、题面生成、质量门槛和验证后，才开始第 2 题。这样中断后更容易续跑，也能从终端直接看清当前卡在哪一道题、哪个阶段；LLM 调用细节统一查看 `logs/llm_calls.jsonl`。

## 目录要求

请确保项目目录结构至少包含：

```text
D:\AutoProblemGen
├─ 总流程
├─ 四元组抽取
├─ 生成题面
└─ 生成测试用例和标准解法
```

`总流程` 中的脚本会按上述相对位置查找其他模块。如果目录名称或层级变化，需要同步修改 `orchestrator.py` 中的模块路径。

## 准备配置文件

本目录提供了三份示例配置：

- `workflow.env.example`：总流程配置，控制输入、输出、质量迭代和本地验证资源。
- `generation_llm.env.example`：生成模型配置，用于四元组抽取、题面生成、质量迭代和验证阶段的 LLM 调用。
- `embedding_llm.env.example`：Embedding 模型配置，用于语义向量计算。

首次运行前，复制示例文件并填写真实配置：

```powershell
Copy-Item workflow.env.example workflow.env
Copy-Item generation_llm.env.example generation_llm.env
Copy-Item embedding_llm.env.example embedding_llm.env
```

然后编辑：

```text
workflow.env
generation_llm.env
embedding_llm.env
```

至少需要确认以下配置：

- `workflow.env` 中的 `INPUT_PATH` 指向待处理题目 JSON 文件或包含多个单题 JSON 的目录。
- `workflow.env` 中的 `OUTPUT_ROOT` 指向总流程输出目录。
- `workflow.env` 中的 `GENERATION_LLM_CONFIG` 指向 `generation_llm.env`。
- `workflow.env` 中的 `EMBEDDING_LLM_CONFIG` 指向 `embedding_llm.env`。
- `generation_llm.env` 和 `embedding_llm.env` 中的 `API_KEY`、`BASE_URL`、`MODEL` 已按实际服务填写。

路径可以写绝对路径，也可以写相对 `workflow.env` 所在目录的路径。

验证阶段的随机/对抗输入生成器依赖 `cyaron==0.7.0`。首次运行前请在执行总流程的同一个 Python 环境中安装：

```powershell
python -m pip install -r D:\AutoProblemGen\生成测试用例和标准解法\requirements.txt
```

## 运行总流程

在本目录执行：

```powershell
python main.py --workflow-config workflow.env
```

如果需要使用指定虚拟环境的 Python，可以在 `workflow.env` 中设置：

```text
PYTHON_EXECUTABLE=D:\path\to\venv\Scripts\python.exe
```

留空时会使用当前启动 `main.py` 的 Python 解释器。

`VERIFICATION_TIMEOUT_SECONDS` 是废弃兼容项；总流程不再用外层总超时杀掉 `verification_runner.py`。验证耗时由 `generation_llm.env` 的 `TIMEOUT_SECONDS`、`MAX_RETRIES` 和 `workflow.env` 中的 `EXECUTION_TEST_INPUT_TIMEOUT_SECONDS`、`EXECUTION_BRUTEFORCE_TIMEOUT_SECONDS`、`EXECUTION_CHECKER_TIMEOUT_SECONDS` 分阶段控制。

验证阶段还会使用 `workflow.env` 中的 LLM 上下文预算配置控制哪些测试用例可以进入模型 prompt。`LLM_CASE_*` 系列配置用于把小型可读用例和大规模压力用例分流：大规模用例继续用于本地执行验证，但不会原样进入 `checker_counterexample_generation` 等 LLM prompt。`MAX_LLM_PROMPT_CHARS` 用于在请求 API 前做本地预算检查，超限会直接失败并给出具体任务名和字符数；`LLM_TRACE_MAX_TEXT_CHARS` 控制 `logs/llm_calls.jsonl` 中大文本字段的记录上限。

## 输入格式

`INPUT_PATH` 支持两种形式：

- 单个 JSON 文件。
- 一个目录，目录中每个 `.json` 文件表示一道题；目录模式会跳过 `manifest.json`，且只处理顶层文件，不递归子目录。

每个输入 JSON 至少需要包含非空的 `problem_id`。如果多个输入文件中出现重复 `problem_id`，流程会直接失败。

## 断点续传

如果 `workflow.env` 中 `RUN_ID` 留空，总流程会基于 `INPUT_PATH` 的规范化绝对路径生成稳定运行标识，例如：

```text
input_sample_400_autoproblemgen_a13f92c8
```

因此重跑同一个输入目录会回到同一个输出目录。启动时程序会读取已有 `workflow_summary.json`，只有同时满足以下条件的题会被跳过：

- 该题上次状态为 `verified`。
- 该题输入文件内容 hash 与上次一致。

未完成或失败的题会重新进入流水线，但四元组抽取阶段默认带 `--resume`：同一输出目录下已存在的 `tuple/raw/<problem_id>_<dimension>.json` 不会再次抽取，后续阶段直接使用已有结果。若 `workflow_summary.json` 显示该题输入文件 hash 已变化，则四元组会重新抽取，避免旧四元组污染新输入。

若需要重新做一次完整实验、保留多次实验结果，或强制重新抽取四元组，请显式填写新的 `RUN_ID`，或删除对应题目的旧 `tuple/raw` 文件后再运行。

## 输出位置

每次运行会在：

```text
OUTPUT_ROOT\RUN_ID
```

下生成结果。如果 `RUN_ID` 留空，程序会使用 `INPUT_PATH` 稳定指纹生成运行标识。

典型输出包括：

- `logs/`：各阶段日志，每题会有独立的抽取、生成和验证日志。
- `logs/llm_calls.jsonl`：所有 LLM 请求的结构化明细，包含 prompt/response 的字符数、短文本原文、超大文本首尾摘要、重试、耗时、usage 和解析结果；不会记录 API Key。
- `tuple/`：四元组抽取结果。
- `generation/source/<problem_id>/`：每题隔离的题面生成输入，包含四元组和 `original_problem` 原题文本，避免目录输入时重复生成已处理题。
- `generation/`：题面生成的 Markdown、artifact 和质量报告。
- `verification/`：验证阶段输出。
- `workflow_summary.json`：本次运行的总览结果、阶段状态和各题状态。

运行时终端会输出：

- 启动摘要：`run_id` 来源、输入模式、题目总数、可跳过数、待处理数、summary 路径和 LLM 详细日志路径。
- 每题进度：题号、`problem_id`、输入文件、每个阶段的开始/完成/跳过原因。
- 验证内部进度：进入测试用例与标准解法阶段后，会输出 `[verification 2/7] Prompt 与 LLM 生成`、`[verification 4/7] 本地验证闭环`、`[verification 5/7] checker 验证`、`[verification 6/7] 错误解池增强` 等关键阶段。
- LLM 修复轮次：暴力解、checker 误拒、checker 误收和标准解触发修复时，会输出当前是第几轮修复以及修复后重新验证的动作。
- LLM 异常信号：重试和最终失败会即时显示，正常调用不逐次打印。

正常调用的模型、prompt、response、usage、耗时、HTTP 状态、JSON 解析状态和结果摘要只写入 `logs/llm_calls.jsonl`。运行结束后，命令行会输出总状态、状态计数、未验证题目列表和 summary 路径，例如：

```text
[workflow] status=completed
[workflow] summary=D:\AutoProblemGen\总流程\output\20260522_120000\workflow_summary.json
```

## 常见失败排查

- `INPUT_PATH 不存在`：检查 `workflow.env` 中的输入路径是否正确。
- `缺少必要配置 API_KEY`：检查 `generation_llm.env` 或 `embedding_llm.env` 是否已填写密钥。
- `QUALITY_ITERATIONS 必须是 1、2 或 3`：质量评价不能关闭，只能配置为 `1`、`2` 或 `3`。
- `四元组抽取子进程失败`、`生成题面子进程失败`：先查看输出目录下 `logs/` 中对应题目的阶段日志。
- `skipped_before_generation`：该题四元组抽取有维度失败，流程会继续处理下一题。
- `quality_gate_failed`：该题生成完成但质量门槛未通过，不会进入验证阶段，流程会继续处理下一题。
- `验证失败` 或 `verification_failed`：查看 `verification/` 下对应题目的验证结果 JSON，以及 `logs/` 中的验证日志。
- 验证阶段长期运行：先看终端最后一条 `[verification x/7]` 或 `[verification repair]` 日志，判断当前卡在 LLM 生成、本地执行、checker 还是错误解池增强。
- LLM 调用卡住、重试或返回非法 JSON：查看 `logs/llm_calls.jsonl` 中对应 `call_id` 的请求和返回摘要；若出现 `LLM prompt 超过本地预算`，请调小进入 LLM 的 case 规模或提高 `MAX_LLM_PROMPT_CHARS`。

## 运行测试

本目录包含总流程编排逻辑的单元测试：

```powershell
python -m unittest discover -s tests
```

测试使用 mock 方式模拟下游模块，不会真实调用模型服务。
