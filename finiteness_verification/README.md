# finiteness_verification

`finiteness_verification` 用于验证编程竞赛题目四维标签集合是否有限且可列。主流程是：

```text
采样 -> Pilot 小样本验证 -> Phase 1 开放抽取与饱和曲线分析 -> Phase 2 封闭分类与覆盖率报告
```

四个核心维度为：

- `input_structure`：输入结构。
- `core_constraints`：核心约束。
- `objective`：目标函数。
- `invariant`：算法不变量。

## 环境配置

从仓库根目录运行命令：

```powershell
cd D:\AutoProblemGen
```

本项目通过 OpenAI-compatible API 调用聊天模型和 embedding 模型。两类服务需要分别配置 base URL、API key 和模型名。推荐复制示例文件：

```powershell
Copy-Item finiteness_verification\.env.example finiteness_verification\.env
```

`.env` 格式：

```env
LLM_BASE_URL=https://your-chat-endpoint/v1
LLM_API_KEY=your-chat-api-key
LLM_MODEL=your-chat-model

EMBEDDING_BASE_URL=https://your-embedding-endpoint/v1
EMBEDDING_API_KEY=your-embedding-api-key
EMBEDDING_MODEL=your-embedding-model

LLM_TIMEOUT_S=300
```

也可以用系统环境变量覆盖 `.env` 中的同名配置。若要指定其它配置文件路径，可设置 `LLM_ENV_FILE`。

验证配置：

```powershell
python -c "from finiteness_verification.llm_client import LLMClient; c = LLMClient(); print(c.model, c.embedding_model)"
```

分析阶段需要 `numpy`、`scipy`、`matplotlib`。

## 项目结构

```text
finiteness_verification/
├── data/
│   ├── sample_pilot.json
│   └── sample_phase1.json
├── prompts/
│   ├── prompt_input_structure.py
│   ├── prompt_constraints.py
│   ├── prompt_objective.py
│   ├── prompt_invariant.py
│   └── prompt_normalize.py
├── output/
│   ├── pilot/
│   ├── phase1/
│   └── phase2/
├── llm_client.py
├── sample.py
├── extract.py
├── normalize.py
├── vote.py
├── analyze.py
├── classify.py
├── report.py
└── transform.py
```

核心模块：

- `sample.py`：从三平台题库生成样本；Phase 1 当前配置为每平台 1000 题，共 3000 题，Pilot 为 50 题。
- `extract.py`：对样本题目进行多轮四维开放抽取，输出到 `raw/`。
- `normalize.py`：使用 embedding 相似度和 LLM 兜底归一化标签，维护 `label_registry/`。
- `vote.py`：对多轮结果投票，输出稳定结果到 `voted/`。
- `analyze.py`：生成 Phase 1 标签集合、饱和曲线和有限性判定。
- `classify.py`：使用 Phase 1 标签集合对全量题目做封闭分类。
- `report.py`：统计 Phase 2 覆盖率和 OTHER 收敛曲线。
- `transform.py`：可选，为投票后的 schema 补全 `transform_space`。

## 采样

如需重新生成样本：

```powershell
python -m finiteness_verification.sample
```

输出：

- `finiteness_verification/data/sample_phase1.json`：Phase 1 样本，当前为 3000 题。
- `finiteness_verification/data/sample_pilot.json`：Pilot 样本，当前为 50 题。

## Pilot 流程

Pilot 用于在 50 题上验证抽取、归一化、投票链路。

### 1. 抽取

```powershell
python -m finiteness_verification.extract `
  --input finiteness_verification/data/sample_pilot.json `
  --output finiteness_verification/output/pilot/ `
  --rounds 3 `
  --resume
```

输出：

- `finiteness_verification/output/pilot/raw/`
- `finiteness_verification/output/pilot/logs/extract.log`

### 2. 归一化

```powershell
python -m finiteness_verification.normalize `
  --input finiteness_verification/output/pilot/raw/ `
  --output finiteness_verification/output/pilot/normalized/ `
  --embedding-threshold 0.85
```

输出：

- `finiteness_verification/output/pilot/normalized/`
- `finiteness_verification/output/pilot/label_registry/`

### 3. 投票

```powershell
python -m finiteness_verification.vote `
  --input finiteness_verification/output/pilot/normalized/ `
  --output finiteness_verification/output/pilot/voted/
```

输出：

- `finiteness_verification/output/pilot/voted/`

检查结果数量：

```powershell
python -c "import os; files = os.listdir(r'finiteness_verification/output/pilot/voted'); print(len(files)); assert len(files) == 50"
```

## Phase 1：开放抽取与有限性分析

Phase 1 对 3000 题样本执行同一管线，并基于投票结果生成标签集合与饱和曲线。

### 1. 抽取

```powershell
python -m finiteness_verification.extract `
  --input finiteness_verification/data/sample_phase1.json `
  --output finiteness_verification/output/phase1/ `
  --rounds 3 `
  --resume
```

说明：

- 任务量为 `3000 题 × 4 维 × rounds`。
- `--resume` 会跳过已存在的 `raw/*.json`。
- `--temperature` 可调整抽取阶段采样温度，默认 `0.4`。

### 2. 归一化

```powershell
python -m finiteness_verification.normalize `
  --input finiteness_verification/output/phase1/raw/ `
  --output finiteness_verification/output/phase1/normalized/ `
  --embedding-threshold 0.85
```

归一化策略：

- 先用 `EMBEDDING_MODEL` 计算标签相似度。
- 未命中的标签再由 `LLM_MODEL` 做归一化兜底。
- 已存在的 `normalized/{problem_id}.json` 会自动跳过。

### 3. 投票

```powershell
python -m finiteness_verification.vote `
  --input finiteness_verification/output/phase1/normalized/ `
  --output finiteness_verification/output/phase1/voted/
```

### 4. 饱和曲线分析

```powershell
python -m finiteness_verification.analyze `
  --input finiteness_verification/output/phase1/voted/ `
  --output finiteness_verification/output/phase1/saturation_curves/
```

输出：

- `finiteness_verification/output/phase1/labels_per_dimension.json`
- `finiteness_verification/output/phase1/saturation_curves/saturation_input_structure.png`
- `finiteness_verification/output/phase1/saturation_curves/saturation_core_constraints.png`
- `finiteness_verification/output/phase1/saturation_curves/saturation_objective.png`
- `finiteness_verification/output/phase1/saturation_curves/saturation_invariant.png`
- `finiteness_verification/output/phase1/saturation_curves/metrics.json`
- `finiteness_verification/output/phase1/saturation_curves/finiteness_judgment.json`

有限性判定阈值：

| 指标 | FINITE | LIKELY_FINITE | UNCERTAIN |
| --- | --- | --- | --- |
| R² | > 0.95 | > 0.90 | > 0.80 |
| 尾部新增率 | < 2% | < 5% | < 10% |

查看指标：

```powershell
python -c "import json; m=json.load(open(r'finiteness_verification/output/phase1/saturation_curves/metrics.json', encoding='utf-8')); print(json.dumps(m, ensure_ascii=False, indent=2))"
```

## Phase 2：封闭分类与覆盖率报告

Phase 2 使用 Phase 1 生成的 `labels_per_dimension.json` 作为封闭标签集合，对全量题目分类。

### 1. 封闭分类

```powershell
python -m finiteness_verification.classify `
  --labels finiteness_verification/output/phase1/labels_per_dimension.json `
  --input 爬取题目/output/luogu/index.json `
  --output finiteness_verification/output/phase2/classified_luogu/ `
  --platform luogu `
  --resume

python -m finiteness_verification.classify `
  --labels finiteness_verification/output/phase1/labels_per_dimension.json `
  --input 爬取题目/output/codeforces/index.json `
  --output finiteness_verification/output/phase2/classified_codeforces/ `
  --platform codeforces `
  --resume

python -m finiteness_verification.classify `
  --labels finiteness_verification/output/phase1/labels_per_dimension.json `
  --input 爬取题目/output/icpc/index.json `
  --output finiteness_verification/output/phase2/classified_icpc/ `
  --platform icpc `
  --resume
```

说明：

- I/C/O 维度输出单个 `category`。
- V 维度支持多标签，输出 `categories` 数组。
- 无合适标签时分类为 `OTHER`。

### 2. 覆盖率报告

```powershell
python -m finiteness_verification.report `
  --input finiteness_verification/output/phase2/ `
  --output finiteness_verification/output/phase2/coverage_report.json
```

输出：

- `finiteness_verification/output/phase2/coverage_report.json`
- `finiteness_verification/output/phase2/other_convergence/other_input_structure.png`
- `finiteness_verification/output/phase2/other_convergence/other_core_constraints.png`
- `finiteness_verification/output/phase2/other_convergence/other_objective.png`
- `finiteness_verification/output/phase2/other_convergence/other_invariant.png`

查看覆盖率：

```powershell
python -c "import json; r=json.load(open(r'finiteness_verification/output/phase2/coverage_report.json', encoding='utf-8')); print(json.dumps(r['overall']['per_dimension'], ensure_ascii=False, indent=2))"
```

## 可选：补全 transform_space

对 `voted/` 中的四维 schema 补全可变参数空间：

```powershell
python -m finiteness_verification.transform `
  --input finiteness_verification/output/phase1/voted/ `
  --output finiteness_verification/output/phase1/voted_with_transform/ `
  --index-root 爬取题目/output `
  --overwrite
```

失败记录会写入输出目录下的 `_failures/`。

## 输出目录总览

```text
finiteness_verification/output/
├── pilot/
│   ├── raw/
│   ├── normalized/
│   ├── label_registry/
│   ├── voted/
│   └── logs/
├── phase1/
│   ├── raw/
│   ├── normalized/
│   ├── label_registry/
│   ├── voted/
│   ├── labels_per_dimension.json
│   └── saturation_curves/
└── phase2/
    ├── classified_luogu/
    ├── classified_codeforces/
    ├── classified_icpc/
    ├── coverage_report.json
    └── other_convergence/
```

## 故障排查

### `ModuleNotFoundError: No module named 'finiteness_verification'`

需要从仓库根目录运行模块命令：

```powershell
cd D:\AutoProblemGen
python -m finiteness_verification.extract --help
```

### `缺少 LLM 配置`

检查 `.env` 或系统环境变量是否包含以下 6 个必要配置：

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL`

### API 调用超时或失败

处理方式：

- 检查网络和 API 服务状态。
- 使用 `--resume` 继续中断的抽取或分类任务。
- 查看对应阶段的 `logs/` 或命令行错误输出。

### 饱和曲线未生成

确认已安装 `matplotlib`，并检查 `voted/` 目录中是否有足够结果文件。`analyze.py` 已使用非交互式后端生成图片。
