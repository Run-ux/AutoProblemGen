# 生题质量消融实验

本目录用于复现“只到生成题面阶段”的组件消融实验。实验种子来自
`D:\AutoProblemGen\总流程\successful_output` 中已经成功生成并验证的题。

## 实验组

| 组别                | 来源                               | 四元组 | planning_rules.json | 质量循环 |
| ------------------- | ---------------------------------- | -----: | ------------------: | -------: |
| `full`            | 复用`successful_output` 最终题面 |     开 |                  开 |       开 |
| `no_tuple`        | 重新生成                           |     关 |                  开 |       开 |
| `no_rules`        | 重新生成                           |     开 |                  关 |       开 |
| `no_quality_loop` | 重新生成                           |     开 |                  开 |       关 |

- `full` 不调用生成模块，只记录已有最终 artifact/Markdown/质量报告路径。
- `no_tuple` 不向 planner/generator 提供 `input_structure/core_constraints/objective/invariant` 或 `tuple_raw`，只给原题文本、元信息和规则摘要。
- `no_rules` 保留四元组和原题文本，但不读取 `D:\AutoProblemGen\生成题面\planning_rules.json`，也不使用规则 handler/helper。
- `no_quality_loop` 使用原生成链路和规则库，`quality_iterations=0`，保留 JSON/题面结构合同 retry。

`full` 组仍只复用 `successful_output` 产物；`no_tuple`、`no_rules`、`no_quality_loop` 和 `judge` 的 LLM 调用均使用本目录 `.env`。

## CLI

所有命令从本目录或项目任意目录运行均可：

```powershell
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py build-manifest
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py run
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py judge
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py report
```

首次运行 `run` 或 `judge` 前，需要复制本目录模板并填写真实 LLM 配置：

```powershell
Copy-Item D:\AutoProblemGen\实验_消融实验_生题质量\.env.example D:\AutoProblemGen\实验_消融实验_生题质量\.env
```

`.env` 使用本实验独立的双端点配置，不再读取 `D:\AutoProblemGen\总流程\workflow.env`：

```dotenv
GENERATION_API_KEY=your_generation_key
GENERATION_BASE_URL=https://api.deepseek.com
GENERATION_MODEL=deepseek-v4-pro
GENERATION_TIMEOUT_SECONDS=1200
GENERATION_MAX_RETRIES=3
GENERATION_TEMPERATURE=0.3

EMBEDDING_API_KEY=your_embedding_key
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_TIMEOUT_SECONDS=1200
EMBEDDING_MAX_RETRIES=3
```

如需临时使用其它配置文件，可在 `run` 或 `judge` 中传入 `--env-file <path>`。旧参数 `--workflow-config` 已废弃；一旦传入会直接报错，避免误读总流程配置。

`run` 和 `judge` 支持按题目分片并行：

- `--shard-count N`：总分片数，默认 `1`。
- `--shard-index K`：当前分片编号，默认 `0`，范围为 `0 <= K < N`。
- 分片规则为 manifest 顺序下的 `problem_index % shard_count == shard_index`。
- 若同时传入 `--limit`，会先截取前 N 题，再做分片。

4 个终端并行运行生成阶段示例：

```powershell
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py run --run-id quality_ablation --shard-count 4 --shard-index 0
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py run --run-id quality_ablation --shard-count 4 --shard-index 1
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py run --run-id quality_ablation --shard-count 4 --shard-index 2
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py run --run-id quality_ablation --shard-count 4 --shard-index 3
```

盲评阶段同理：

```powershell
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py judge --run-id quality_ablation --shard-count 4 --shard-index 0
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py judge --run-id quality_ablation --shard-count 4 --shard-index 1
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py judge --run-id quality_ablation --shard-count 4 --shard-index 2
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py judge --run-id quality_ablation --shard-count 4 --shard-index 3
```

所有分片完成后，单独运行一次报告汇总：

```powershell
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py report --run-id quality_ablation
```

常用冒烟测试：

```powershell
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py build-manifest --limit 1
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py run --limit 1 --conditions no_quality_loop
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py judge --limit 1 --conditions full,no_quality_loop
python D:\AutoProblemGen\实验_消融实验_生题质量\main.py report
```

## 输出

- `manifests/quality_ablation_manifest.json`
- `output/<run_id>/generations/<condition>/<problem_id>/...`
- `output/<run_id>/judging/blind_items.jsonl`
- `output/<run_id>/scores.jsonl`
- `output/<run_id>/summary.csv`
- `output/<run_id>/report.md`

分片模式下，为避免多个终端覆盖同一文件，会改写为：

- `output/<run_id>/run_metadata_shard_<K>_of_<N>.json`
- `output/<run_id>/run_summary_shard_<K>_of_<N>.json`
- `output/<run_id>/judging/blind_items_shard_<K>_of_<N>.jsonl`
- `output/<run_id>/scores_shard_<K>_of_<N>.jsonl`
- `output/<run_id>/judging/judge_summary_shard_<K>_of_<N>.jsonl`

`report` 会优先合并 `scores_shard_*_of_*.jsonl`；若不存在分片分数文件，则读取旧的 `scores.jsonl`。

## 计分与失败处理

LLM judge 只接收 seed problem 和新题题面，不接收 condition、路径、轮次或内部质量报告。
评分维度为 `solvability`、`clarity`、`novelty`、`difficulty`，`overall_score` 为四项均值。

- `schema_insufficient`、`difference_insufficient` 等声明性失败按 0 分进入主指标。
- API、超时、文件缺失等基础设施失败记为 missing，并在报告中单独统计。
- 报告主比较为 `full - no_tuple`、`full - no_rules`、`full - no_quality_loop`，包含均值差、median 差和 bootstrap 95% CI。

## 解释边界

本实验只评价题面文本质量，不进入测试用例、标准解法或验证阶段。种子集合限定为已成功生成并验证的题，因此结论针对该成功样本集合，不代表全部候选题的无偏估计。
