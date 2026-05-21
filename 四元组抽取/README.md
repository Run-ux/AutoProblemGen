# 四元组抽取

当前目录直接面向 `D:\AutoProblemGen\爬取题目\output\imandra_curated_schema_inputs` 中的单题 schema JSON。

## 输入约定

- 每个输入文件对应 1 道题。
- 顶层字段至少包含 `problem_id`、`title`、`description`、`source`。
- `description` 中包含题面正文以及 `Input`、`Output`、`Constraints`、`Examples` 等分节。
- `reference_solution.code` 为标准解法代码，仅在 invariant 维作为高优先级证据使用。

抽取前会先做统一预处理：

- 保留完整 `description` 作为 prompt 主输入。
- 从 `description` 中切分 `input`、`output`、`constraints`，并在每个 user prompt 中显式展示。
- 从 `limits` 中补充时间与空间限制文本。

## Prompt 约定

- 四个抽取维度的 user prompt 都会给关键 JSON 字段补充简短说明，固定说明字段含义、填写条件、留空条件与常见误填。
- JSON 示例继续保留，但改为中性结构骨架，用于约束层级与字段形状，不再用具体题型词汇暗示语义。
- `input_structure.type` 只描述输入载体形态，既允许 `integer`、`float`、`char`、`boolean`、`tuple` 这类标量或定长记录类型，也允许数组、字符串、图、树等结构类型；`pair` 统一归入 `tuple`，集合语义仍归入 `array` 并通过 `properties` 表达，复合输入写入可选 `components`。
- `input_structure.components` 是正式输出字段。组件项包含 `role`、`role_description`、`type`、`length`、`value_range`、`properties`。模型单轮抽取出的组件结构会原样进入 raw 结果。
- 当 `input_structure.type=composite` 时，`components` 必须为非空数组，且每个组件都必须提供非空 `role` 与 `role_description`。缺失时抽取阶段直接记为失败。
- `core_constraints.name` 是开放抽象标签，应使用稳定的小写英文加下划线格式；具体题目限制写入 `description`、`formal` 与可选 `source_sections`。
- `objective.type` 继续使用目标词表，可选扩展 `target` 与 `requires_solution`。
- `invariant.name` 是开放抽象标签，应使用稳定的小写英文加下划线格式；只保留可由代码或题面支撑的稳定维护性质，不把算法范式直接当作不变量标签；有代码时以代码为主证据，无充分证据时允许返回空数组。
- `label_vocab.py` 保留输入结构类型、输入结构性质键、目标类型和枚举常量说明，用于直接注入 I/O 维 prompt。

## 主流程

主线入口由 `总流程` 统一调用：

```powershell
python D:\AutoProblemGen\总流程\main.py --workflow-config D:\AutoProblemGen\总流程\workflow.env
```

`extract.py` 保留为总流程子进程入口。若单独调试该脚本，必须先提供总流程运行时 JSON 环境变量，不能再依赖本目录 `.env`。

总流程调用时会传入：

```powershell
python extract.py --input D:\AutoProblemGen\爬取题目\output\imandra_curated_schema_inputs --output <run_dir>\tuple
```

`raw\` 目录中的文件就是当前最终可消费结果。文件命名为 `raw\{problem_id}_{dimension}.json`，每题每维一个文件。

## CLI 参数

### `extract.py`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--input` | `str` | 是 | 无 | 输入单题 schema JSON 文件，或包含多个 schema JSON 的目录 |
| `--output` | `str` | 是 | 无 | 输出目录路径，如 `output/pilot/` |
| `--resume` | 开关 | 否 | 关闭 | 断点续传，跳过已存在的文件 |
| `--log-level` | `str` | 否 | `INFO` | 日志级别，可选 `DEBUG`、`INFO`、`WARNING`、`ERROR` |
| `--temperature` | `float` | 否 | `0.4` | LLM 采样温度 |

### `sample.py`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--source-dir` | `str` | 否 | `DEFAULT_SOURCE_DIR` | 源 schema 目录 |
| `--data-dir` | `str` | 否 | `DEFAULT_DATA_DIR` | 输出 data 目录 |
| `--phase1-size` | `int` | 否 | `300` | phase1 样本量，不足时复制全部 |
| `--pilot-size` | `int` | 否 | `50` | pilot 样本量，不足时复制全部 |

## 完整流程

1. 读取题目 schema JSON。
   `extract.py` 接收单个文件或目录，随后调用 `problem_schema.py` 读取并校验题目数据。
2. 执行统一预处理。
   预处理会保留完整 `description`，切分 `input`、`output`、`constraints` 分节，把 `limits` 合并进 `constraints`，并在存在 `reference_solution.code` 时补出 `standard_solution_code`。
3. 进行四维独立抽取。
   抽取阶段固定处理 `input_structure`、`core_constraints`、`objective`、`invariant` 四个维度。四个维度都会看到标题、题面全文、Input 分节、Output 分节、Constraints 分节。`invariant` 维额外把标准解法代码作为高优先级证据。
4. 写出 raw 结果。
   每题每维调用一次模型，结果写入 `output/<run>/raw/{problem_id}_{dimension}.json`。每个文件包含 `problem_id`、`source`、`dimension`、`result`、`status`；失败时附带 `error`。

## 验证

结构验证：

```powershell
python verify_prompts_structure.py
```

该脚本会检查：

- user prompt 是否包含标题、题面全文、`input`、`output`、`constraints` 分节。
- invariant 维在有标准解法代码时是否把代码注入 prompt。
- schema 必填字段与新增可选字段是否齐全。
- `input_structure.type=composite` 时，组件 schema 与模型输出是否包含 `role_description`。
- 样本是否覆盖单数组题、图题、树加查询题、判定题、计数题、无标准解法代码题。

需要实际调用模型时：

```powershell
python test_prompts_qa.py
```

抽取单元测试：

```powershell
python -m unittest test_extract.py
```

## 环境要求

- 本模块不再读取本地 `.env`、`.env.example`、`env_loader.py` 或模块级配置文件。
- 抽取阶段只使用总流程注入的 generation LLM 配置。
- 缺少运行时配置或 `API_KEY` 时会 fail-fast，并提示通过 `总流程/generation_llm.env` 配置。
- 输入文件来自 `D:\AutoProblemGen\爬取题目\output\imandra_curated_schema_inputs`。
