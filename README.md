# AutoProblemGen

## 当前仓库结构

| 目录                        | 定位                                                                                           | 当前状态               |
| --------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------- |
| `论文`                    | 研究资料、论文阅读、Problem Schema 设计与改编思路                                              | 研究设计层             |
| `爬取题目`                | 从 Codeforces、AtCoder、Luogu、ICPC 等来源采集题目并落盘                                       | 数据入口               |
| `四元组抽取`              | 从单题 schema JSON 抽取 `input_structure / core_constraints / objective / invariant` | 当前生成链路的默认上游 |
| `finiteness_verification` | 通过 Pilot、Phase 1、Phase 2 验证四维标签集合是否有限、稳定、可覆盖                            | 标签体系验证           |
| `生成题面`                | 基于四元组、规则文件和两阶段 LLM 规划生成结构化题面                                            | 当前生成器             |
| `题目质量评价`            | 对生成 artifact 做题面质量评分、反换皮判定、硬约束检查，并输出 `revision_brief`              | 当前质量闭环           |
| `生成测试用例和标准解法`  | 基于上游 artifact 生成标准解、暴力解、测试输入生成器、checker 和错误解池，并执行本地验证闭环   | 交付验证能力建设       |
| `总流程`                  | 将四元组抽取、题面生成、质量评价、测试用例与标准解法验证串成一条端到端 CLI                    | 一键编排入口           |
| `实验`                    | 冻结已验证生成题，让多个 LLM 独立解题并统计 pass@1、对抗鲁棒性和经验难度                      | 实验评测层             |

## 端到端总流程

`总流程` 提供从原始单题 schema JSON 到最终验证产物的一键编排入口，固定串联：

```text
原始 schema -> 四元组抽取 -> 组装四维 schema -> 生成题面 -> 题目质量评价 -> 生成测试用例和标准解法
```

运行示例：

```powershell
python D:\AutoProblemGen\总流程\main.py ^
  --workflow-config D:\AutoProblemGen\总流程\workflow.env
```

总流程 v1 只支持 `single_seed_extension`，不包含爬取阶段，也不串 `same_family_fusion`。输入可以是单个原始 schema JSON，或包含多个 schema JSON 的目录；目录输入会按题串行跑完整流水线，即一题完成四元组抽取、题面生成、质量门槛和验证后，再开始下一题。流程参数全部从 `workflow.env` 读取，`QUALITY_ITERATIONS` 必须为 `1`、`2` 或 `3`，不能关闭质量评价；只有最终质量报告满足 `generated_status=ok`、`overall.status=pass`，且迭代摘要 `stop_reason=pass` 的题目才会进入测试用例与标准解法验证阶段。

`RUN_ID` 留空时，总流程会基于 `INPUT_PATH` 的规范化绝对路径生成稳定运行标识，用于断点续传。重跑同一个输入目录会读取已有 `workflow_summary.json`，跳过已 `verified` 且输入文件 hash 未变化的题；默认会重跑未完成、失败或输入变化的题。若命令带 `--skip-previous-failures`，历史已跑过但未 `verified` 且输入 hash 未变化的题会在本次运行中保留原状态并跳过，流程优先处理未跑过的题。如需保留多次完整实验，请手动设置新的 `RUN_ID`。

默认输出位于：

```text
总流程/output/<run_id>/
├── tuple/raw/
├── generation/source/
├── generation/output/
├── generation/artifacts/
├── generation/reports/
├── verification/<problem_id>/
├── logs/
│   └── llm_calls.jsonl
└── workflow_summary.json
```

`workflow_summary.json` 会按题记录输入 hash、抽取、生成、质量门槛和验证状态。若某题抽取四维中任一维失败，该题会标记为 `skipped_before_generation`，不会进入题面生成；若质量门槛未通过，则不会生成下游测试与标准解法产物。终端会输出每题阶段进度和 LLM 重试/失败等异常信号；正常 LLM 调用的模型、prompt、response、usage、耗时和解析结果写入 `logs/llm_calls.jsonl`，且不会记录 API Key。

## 生成题质量评测实验

`实验` 模块会从 `总流程/output` 冻结同时具备随机、对抗、小规模难例和大规模真值的生成题，让多个 OpenAI 兼容模型在只看到题面的条件下各生成一次 Python 解答，并输出总体 pass@1、分类通过率、随机/对抗差距、经验难度和分组统计。实验运行前会校验 artifact hash，API 基础设施错误可补跑，模型答题失败不会自动重新采样。

```powershell
python D:\AutoProblemGen\实验\main.py build-manifest --workflow-output-root D:\AutoProblemGen\总流程\output --output D:\AutoProblemGen\实验\manifests\generated_v1.json
python D:\AutoProblemGen\实验\main.py run --manifest D:\AutoProblemGen\实验\manifests\generated_v1.json --models D:\AutoProblemGen\实验\models.json --output-root D:\AutoProblemGen\实验\output --run-id generated_v1
python D:\AutoProblemGen\实验\main.py report --run-dir D:\AutoProblemGen\实验\output\generated_v1
```

完整配置、指标口径和输出合同见 [`实验/README.md`](实验/README.md)。

## 主线流程

### 1. 数据采集

`爬取题目` 负责从多个平台抓取题目，并以统一格式保存到 `output/<platform>/`。当前已有题库规模包括：

- `codeforces`：2201 道
- `icpc`：3149 道
- `luogu`：7903 道

这些数据既服务于有限性验证，也为后续 curated schema 输入提供原始题目来源。

### 2. 四元组抽取

`四元组抽取` 是当前生成链路的直接上游，默认输入来自：

```text
爬取题目/output/imandra_curated_schema_inputs/*.json
```

它把单题题面与可选标准解法抽取成四个稳定维度。主线入口只支持通过 `总流程` 调用，LLM 配置由总流程注入：

- `input_structure`：输入载体、组件、长度、取值范围与结构性质
- `core_constraints`：题目必须满足的核心约束
- `objective`：求解目标、目标类型与目标对象
- `invariant`：题面或代码可支撑的稳定维护性质

总流程会将 `tuple/raw/*.json` 直接组装为 `generation/source/*.json`，后续生成器消费该目录。

详细字段约定见 [`四元组抽取/README.md`](四元组抽取/README.md)。

### 3. 有限性验证

`finiteness_verification` 不是当前生成器的默认输入目录，而是用于验证 `I/C/O/V` 标签体系是否足够稳定：

- `Pilot`：小样本多轮抽取、归一化、投票
- `Phase 1`：3000 题样本抽取并绘制饱和曲线
- `Phase 2`：使用 Phase 1 标签集对全量题库做封闭分类与覆盖率报告

这个模块回答的是“Schema 四维能否形成可控中间表示”，而不是直接生成题面。详细流程见：

- [`finiteness_verification/README_PHASE1.md`](finiteness_verification/README_PHASE1.md)
- [`finiteness_verification/README_PHASE2.md`](finiteness_verification/README_PHASE2.md)

### 4. `生成题面`

`生成题面` 是当前正式生成器。它读取总流程组装出的四维 schema，结合 `planning_rules.json` 和规则 handler 完成规则资格审查、规划校验、题面生成、题面审查与产物落盘。

当前支持的运行模式：

- `single_seed_extension`：CLI 中对应 `--mode single`
- `same_family_fusion`：CLI 中对应 `--mode same_family`

`single_seed_extension` 的规则集合按竞赛题型谱系扩展，覆盖规范构造、冲突证书、计数与分布计数、阈值优化、鲁棒保底、在线查询、多目标权衡、反向设计、全局耦合、博弈化和全局覆盖等方向。每次仍只选择一条主规则，并记录完整的资格、排序、规划和题面审查轨迹。

`cross_family_fusion` 仅保留规则文件占位，当前不宣称支持运行。

`生成题面/main.py` 保留为总流程子进程入口，不再作为独立用户入口承诺本地配置能力。生成参数由 `总流程/workflow.env` 统一提供。

质量闭环只在 `single_seed_extension` 中启用。正常阶段最多执行 `--quality-iterations` 指定的 1 到 3 轮；`revise_quality` 和 `reject_as_retheme` 会把结构化 `revision_brief` 回流给下一轮规划与题面生成。若某轮 `overall.status` 为 `pass`，生成器还会检查五个质量维度 `variant_fidelity`、`spec_completeness`、`cross_section_consistency`、`sample_quality`、`oj_readability` 是否全部为 5 分。

当 `pass` 但五维未满分时，流程进入满分打磨阶段：复用上一轮 `VariantPlan` 和同一个 `new_schema`，不再调用 planner，也不重新生成 schema，只允许重写题面内容并继续评测。追加轮数由 `--quality-full-score-max-iterations` 控制，默认 10 轮；仍未满分时以 `full_score_iteration_limit_reached` 停止。

主要输出：

- `生成题面/output/<problem_id>/*.md`：最终 Markdown 题面
- `生成题面/artifacts/<problem_id>/*.json`：规则决策、实例化四元组、模型返回与迭代摘要
- `生成题面/reports/<problem_id>/*.md`：人工排查报告
- `生成题面/artifacts/batch_*.json`：批量生成汇总

artifact 会记录 `mode`、`source_problem_ids`、`applied_rule`、`rule_selection_reason`、`rejected_candidates`、`algorithmic_delta_claim`、`applied_helpers`、`selection_trace`、`validation_trace`、`candidate_attempts` 与 `distance_breakdown`。启用质量闭环后还会增加 `iteration` 元信息和 `*_iteration_summary.json`，其中包含每轮质量报告路径、质量维度分数、迭代阶段、最终采用轮次与停止原因。

详细 CLI、规则合同和 artifact 字段见 [`生成题面/README.md`](生成题面/README.md)。

### 5. `题目质量评价`

`题目质量评价` 直接消费 `生成题面` 的 artifact，并结合源 schema 与原题做综合评估。

它会输出两类结论：

- 题面质量：`variant_fidelity`、`spec_completeness`、`cross_section_consistency`、`sample_quality`、`oj_readability`
- 反换皮判断：`schema_distance`、`semantic_difference`、`solution_transfer_risk`、`surface_retheme_risk`

最终状态包括：

- `pass`
- `revise_quality`
- `reject_as_retheme`
- `reject_invalid`

评估器还会输出结构化 `revision_brief`。当 `生成题面` 启用 `--quality-iterations` 时，该摘要会回流给下一轮规划和题面生成；默认单轮生成不会强制进入闭环。

`题目质量评价/main.py` 保留为总流程子进程/内部调试入口，必须由总流程注入 LLM Judge 配置，不再读取模块级 `.env`。

详细合同见 [`题目质量评价/README.md`](题目质量评价/README.md)。

### 6. `生成测试用例和标准解法`

`生成测试用例和标准解法` 是当前链路的后续交付验证能力模块。它接收 `生成题面` 的结构化 artifact，在库函数入口中通过 OpenAI 兼容 Chat Completions API 生成并验证：

- 标准解
- 暴力解
- 随机测试输入生成器
- 对抗测试输入生成器
- 小规模挑战测试输入
- checker
- 固定类别错误解
- 基于 schema 错误策略分析的错误解

当前已实现 artifact 字段抽取、prompt 组织、LLM JSON 调用、严格 JSON 解析、输出合同校验、合同型 LLM 自动重试、测试输入生成器定向修复、生成后本地验证闭环、错误解池增强验证和单元测试。暂未实现独立 CLI、题包流水线和落盘式输出目录。

总流程会在质量门槛通过后调用 `generate_verified_artifacts`，并显式传入 generation LLM 配置与执行限制。该模块不再读取本地 `.env`。

验证入口会在受限子进程中执行生成代码，并把修复后的标准解、暴力解法与 checker 写回返回结果；它不自动修改上游题面，也不承担题面歧义修订。验证阶段不再设置外层总超时，而是分别使用 LLM 调用超时/重试、本地测试输入生成、暴力解和 checker 的执行超时；标准解 debug 另由 `STANDARD_SOLUTION_MAX_REPAIR_ITERATIONS` 控制最大修复轮数。终端会输出 `[verification 2/7]`、`[verification 4/7]`、`[verification 5/7]`、`[verification 6/7]` 等关键阶段，以及 LLM 修复循环的当前轮次。详细说明见 [`生成测试用例和标准解法/README.md`](生成测试用例和标准解法/README.md)。

## 环境配置

主线模块只从 `总流程` 读取配置。复制以下三个模板并填写真实值：

- `总流程/workflow.env.example` -> `总流程/workflow.env`
- `总流程/generation_llm.env.example` -> `总流程/generation_llm.env`
- `总流程/embedding_llm.env.example` -> `总流程/embedding_llm.env`

验证模块生成的随机/对抗输入代码要求当前 Python 环境安装 `cyaron==0.7.0`，推荐使用：

```powershell
python -m pip install -r D:\AutoProblemGen\生成测试用例和标准解法\requirements.txt
```

总流程在进入验证阶段前会检查 `PYTHON_EXECUTABLE` 是否能导入 `cyaron`；若检查失败，会在 summary 中记录失败原因并停止后续验证。

`workflow.env` 负责流程参数和两个 LLM 配置文件路径：

```dotenv
INPUT_PATH=D:\AutoProblemGen\爬取题目\output\imandra_curated_schema_inputs
OUTPUT_ROOT=D:\AutoProblemGen\总流程\output
RUN_ID=
QUALITY_ITERATIONS=3
QUALITY_FULL_SCORE_MAX_ITERATIONS=10
GENERATION_LLM_CONFIG=D:\AutoProblemGen\总流程\generation_llm.env
EMBEDDING_LLM_CONFIG=D:\AutoProblemGen\总流程\embedding_llm.env
```

`VERIFICATION_TIMEOUT_SECONDS` 是废弃兼容项；即使旧配置文件保留该项，也不再控制验证子进程生命周期。验证耗时由 `generation_llm.env` 的 `TIMEOUT_SECONDS`/`MAX_RETRIES` 和 `EXECUTION_*_TIMEOUT_SECONDS` 分阶段控制。

`RUN_ID=` 留空表示按 `INPUT_PATH` 稳定续传；同一输入目录会复用同一输出目录。需要重新完整运行时，请填写新的 `RUN_ID`。

`generation_llm.env` 负责抽取、题面生成、质量评价和验证产物生成：

```dotenv
API_KEY=your_key
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL=qwen3.6-plus
TIMEOUT_SECONDS=360
MAX_RETRIES=3
TEMPERATURE=0.2
```

`embedding_llm.env` 只负责 schema 距离等 embedding 调用：

```dotenv
API_KEY=your_key
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL=text-embedding-v4
TIMEOUT_SECONDS=360
MAX_RETRIES=3
```

## 测试

当前仓库按模块维护测试。常用命令：

```powershell
python -m unittest discover -s D:\AutoProblemGen\生成题面\tests -v

python -m unittest discover -s D:\AutoProblemGen\题目质量评价\tests -v

python -m unittest discover -s D:\AutoProblemGen\生成测试用例和标准解法\tests -v

python -m unittest discover -s D:\AutoProblemGen\总流程\tests -v
```

`四元组抽取` 可运行：

```powershell
cd D:\AutoProblemGen\四元组抽取

python verify_prompts_structure.py
python -m unittest test_extract.py
```
