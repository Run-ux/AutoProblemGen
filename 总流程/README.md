# AutoProblemGen 总流程运行说明

本目录是 AutoProblemGen 的端到端编排入口，负责串联以下阶段：

1. 调用同级目录 `四元组抽取/extract.py` 抽取题目四元组。
2. 调用同级目录 `生成题面/main.py` 生成新题面并执行质量迭代。
3. 调用本目录 `verification_runner.py`，再转入同级目录 `生成测试用例和标准解法` 生成并验证测试产物。
4. 在输出目录写入日志、阶段结果和 `workflow_summary.json`。

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

## 输入格式

`INPUT_PATH` 支持两种形式：

- 单个 JSON 文件。
- 一个目录，目录中每个 `.json` 文件表示一道题；目录模式会跳过 `manifest.json`。

每个输入 JSON 至少需要包含非空的 `problem_id`。如果多个输入文件中出现重复 `problem_id`，流程会直接失败。

## 输出位置

每次运行会在：

```text
OUTPUT_ROOT\RUN_ID
```

下生成结果。如果 `RUN_ID` 留空，程序会自动使用当前时间生成运行标识。

典型输出包括：

- `logs/`：各阶段日志。
- `tuple/`：四元组抽取结果。
- `generation/`：题面生成的输入、Markdown、artifact 和质量报告。
- `verification/`：验证阶段输出。
- `workflow_summary.json`：本次运行的总览结果、阶段状态和各题状态。

运行结束后，命令行会输出总状态和 summary 路径，例如：

```text
[workflow] status=completed
[workflow] summary=D:\AutoProblemGen\总流程\output\20260522_120000\workflow_summary.json
```

## 常见失败排查

- `INPUT_PATH 不存在`：检查 `workflow.env` 中的输入路径是否正确。
- `缺少必要配置 API_KEY`：检查 `generation_llm.env` 或 `embedding_llm.env` 是否已填写密钥。
- `QUALITY_ITERATIONS 必须是 1、2 或 3`：质量评价不能关闭，只能配置为 `1`、`2` 或 `3`。
- `四元组抽取阶段失败`、`生成题面阶段失败`：先查看输出目录下 `logs/` 中对应阶段日志。
- `验证失败` 或 `verification_failed`：查看 `verification/` 下对应题目的验证结果 JSON，以及 `logs/` 中的验证日志。

## 运行测试

本目录包含总流程编排逻辑的单元测试：

```powershell
python -m unittest discover -s tests
```

测试使用 mock 方式模拟下游模块，不会真实调用模型服务。
