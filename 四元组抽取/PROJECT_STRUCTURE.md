# 四元组抽取 项目结构分析

本文总结 `四元组抽取` 目录当前的输入假设、核心模块和处理流程。

## 1. 项目定位

- 目标：对单题 schema JSON 进行四维独立抽取。
- 语言：Python 3。
- 主输入：`D:\AutoProblemGen\爬取题目\output\imandra_curated_schema_inputs\*.json`
- 主流程：读取单题 schema → 题面分节切分 → 抽取 I/C/O/V → 写出 raw 结果。

## 2. 输入结构

每个输入文件对应 1 道题，核心字段包括：

- `problem_id`
- `title`
- `description`
- `source.source_name`
- `limits`
- `reference_solution.code`

当前预处理行为：

- `description` 会完整保留，并作为 prompt 的基础文本。
- `problem_schema.py` 会从 `description` 中切分 `Input`、`Output`、`Constraints`。
- `limits` 会被并入 `constraints` 文本。
- `reference_solution.code` 会在 invariant 维作为额外证据输入模型。

## 3. 词表与 schema

- `label_vocab.py`：维护输入结构类型、输入结构性质键、目标类型以及 source/evidence 枚举常量。`input_structure.type` 只保留输入载体类型，覆盖标量、数组、字符串、矩阵、图、树与复合输入；语义性质下沉到 `properties`。
- `prompt_input_structure.py`：顶层保留 `type`、`length`、`value_range`、`properties`，新增可选 `components`。组件项包含 `role`、`role_description`、`type`、`length`、`value_range`、`properties`；当顶层为 `composite` 时，组件角色名与角色说明都必须存在。
- `prompt_constraints.py`：顶层保留 `constraints[]`，单项新增可选 `source_sections`。`name` 使用开放抽象标签，不再绑定预设词表。
- `prompt_objective.py`：顶层保留 `type` 与 `description`，新增可选 `target`、`requires_solution`。`type` 继续使用目标词表。
- `prompt_invariant.py`：顶层保留 `invariants[]`，单项新增可选 `evidence_source`。`name` 使用开放抽象标签，不再绑定预设词表。

## 4. 核心模块

```text
四元组抽取/
├── prompts/
│   ├── prompt_input_structure.py
│   ├── prompt_constraints.py
│   ├── prompt_objective.py
│   ├── prompt_invariant.py
│   └── prompt_sections.py
├── label_vocab.py               # I/O 词表与枚举常量
├── problem_schema.py            # schema 读取、校验、分节切分
├── extract.py                   # 抽取入口，接受单文件或目录
├── prompt_test_cases.py         # 验证脚本用的题型选样工具
├── verify_prompts_structure.py  # Prompt 结构验证
├── test_prompts_qa.py           # Prompt QA 测试
├── test_extract.py              # 抽取单元测试
├── qwen_client.py               # generation LLM 调用，由总流程显式注入配置
├── README.md
└── PROJECT_STRUCTURE.md
```

## 5. 数据流

```text
imandra_curated_schema_inputs/*.json
  → problem_schema.py
  → extract.py
  → output/<run>/raw/
```

## 6. 主要输出

- `output/<run>/raw/`：每题每维单轮抽取结果，也是当前最终可消费结果。
- 文件命名：`{problem_id}_{dimension}.json`。
- 文件结构：`problem_id`、`source`、`dimension`、`result`、`status`；失败时附带 `error`。

## 7. 配置来源

- 本模块不再维护模块级 `.env.example`，也不再通过 `env_loader.py` 读取本地 `.env`。
- 主线只支持由 `总流程/main.py --workflow-config 总流程/workflow.env` 调用。
- generation LLM 配置来自 `总流程/generation_llm.env`，由总流程解析后以运行时 JSON 环境变量注入子进程。
- `QwenClient` 必须由调用方显式传入 generation LLM 配置；缺失时直接 fail-fast。
