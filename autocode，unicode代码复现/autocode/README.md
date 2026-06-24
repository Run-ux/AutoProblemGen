# AutoCode 问题生成器

基于AutoCode论文实现的算法竞赛题目自动生成系统，支持规则变换和LLM生成两种模式。

## 安装依赖

```bash
pip install openai
```

## 使用方法

### 1. 基本使用（规则变换模式）

```bash
python -m autocode.generator --input autocode/examples/seed_problem.json --output autocode/examples/new_problem.json --transformations 2 --seed 42
```

### 2. 使用LLM生成

有三种方式配置API密钥：

#### 方式1：命令行参数（推荐用于测试）

```bash
python -m autocode.generator \
  --input autocode/examples/seed_problem.json \
  --output autocode/examples/new_problem.json \
  --use-llm \
  --api-key "your-api-key-here" \
  --base-url "https://api.openai.com/v1" \
  --model "gpt-4o"
```

#### 方式2：环境变量（推荐用于生产环境）

```bash
# Windows PowerShell
$env:OPENAI_API_KEY="your-api-key-here"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"

# Linux/Mac
export OPENAI_API_KEY="your-api-key-here"
export OPENAI_BASE_URL="https://api.openai.com/v1"

# 然后运行
python -m autocode.generator \
  --input autocode/examples/seed_problem.json \
  --output autocode/examples/new_problem.json \
  --use-llm
```

#### 方式3：配置文件（推荐）

在 `autocode` 目录下编辑 `.env` 文件：

```
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
```

然后使用：

```bash
python -m autocode.generator \
  --input autocode/examples/seed_problem.json \
  --output autocode/examples/new_problem.json \
  --use-llm
```

### 3. 批量生成模式

批量处理输入目录下的所有JSON文件：

```bash
python -m autocode.generator \
  --input autocode/input/test_batch \
  --batch \
  --transformations 2 \
  --use-llm
```

#### 输出目录结构

```
autocode/output/test_batch_generated_20240101_120000/
├── batch_log.txt           # 运行日志
├── batch_stats.json        # 统计信息
├── generated_problem1.json # 生成的题目
├── generated_problem2.json
└── ...
```

### 4. successful_output 并行处理模式

处理 `successful_output` 下的题目文件夹。每个直接子目录视为一个题目，程序会读取该题目目录下 `original_input/*.json` 中按文件名排序后的第一个 JSON，并输出到 `other_methods/autocode.json`。

```powershell
python -m autocode.parallel_generator `
  --input "D:\AutoProblemGen\autocode，unicode代码复现\input\successful_output" `
  --use-llm `
  --batch-size 5 `
  --processes 5 `
  --max-tokens 16000
```

说明：
- `--batch-size` 控制每个批次处理多少个题目，默认 5。
- `--processes` 控制最多同时运行多少个批次，默认 5。
- 每个批次会在输入目录下写出独立的 `autocode_batch_<n>_log.txt` 和 `autocode_batch_<n>_stats.json`，最终汇总到 `autocode_parallel_stats.json`。

## 命令行参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--input` | `-i` | 输入种子题JSON文件路径或目录 | 必需 |
| `--output` | `-o` | 输出新题目JSON文件路径或目录（批量模式可选） | 必需（单文件模式） |
| `--transformations` | `-t` | 变换次数 | 1 |
| `--seed` | `-s` | 随机种子 | 无 |
| `--use-llm` | | 使用LLM生成 | False |
| `--api-key` | | OpenAI API密钥 | 从环境变量读取 |
| `--base-url` | | OpenAI API基础URL | 从环境变量读取 |
| `--model` | | LLM模型名称 | gpt-4o |
| `--max-tokens` | | LLM生成的最大 completion token 数 | `MAX_TOKENS` 或 16000 |
| `--batch` | | 启用批量模式处理多个JSON文件 | False |
| `--process-folders` | | 处理 successful_output 题目目录结构 | False |

`autocode.parallel_generator` 额外支持：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--batch-size` | 每个批次处理的题目数量 | 5 |
| `--processes` | 并行进程数上限 | 5 |

## 输入输出格式

### 输入格式（种子题）

```json
{
  "title": "题目标题",
  "description": "题目描述",
  "constraints": {
    "time_limit": "2 seconds",
    "memory_limit": "256 megabytes",
    "input_format": "",
    "output_format": ""
  },
  "input_description": "输入格式说明",
  "output_description": "输出格式说明",
  "examples": [
    {
      "input": "示例输入",
      "output": "示例输出"
    }
  ],
  "difficulty": 1200,
  "tags": ["array", "dynamic programming"]
}
```

### 输出格式（生成的新题目）

```json
{
  "title": "新题目标题",
  "description": "新题目描述",
  "constraints": {...},
  "input_description": "输入格式说明",
  "output_description": "输出格式说明",
  "examples": [...],
  "difficulty": 1500,
  "tags": ["array", "dynamic programming"],
  "original_seed": "原始题目标题",
  "transformation_type": "变换类型"
}
```

## 变换类型

### 规则变换模式
- `add_constraint` - 添加约束条件
- `remove_constraint` - 删除约束条件
- `modify_constraint` - 修改约束条件
- `add_condition` - 添加条件
- `modify_condition` - 修改条件
- `change_domain` - 改变问题领域
- `change_objective` - 改变目标函数
- `increase_dimension` - 增加维度
- `add_operation` - 添加操作
- `modify_output_format` - 修改输出格式

### LLM变换模式
- `ADD_CONSTRAINT` - 添加约束条件
- `REMOVE_CONSTRAINT` - 删除约束条件
- `MODIFY_CONDITION` - 修改条件
- `CHANGE_DOMAIN` - 改变问题领域
- `ADD_OPERATION` - 添加操作
- `INCREASE_DIMENSION` - 增加维度
- `CHANGE_OBJECTIVE` - 改变目标函数
- `MODIFY_OUTPUT_FORMAT` - 修改输出格式

## 示例

### 使用规则变换生成

```bash
python -m autocode.generator \
  --input autocode/examples/seed_problem.json \
  --output autocode/examples/rule_generated.json \
  --transformations 3 \
  --seed 42
```

### 使用LLM生成

```bash
python -m autocode.generator \
  --input autocode/examples/seed_problem.json \
  --output autocode/examples/llm_generated.json \
  --use-llm \
  --transformations 2 \
  --model "gpt-4o"
```

## 项目结构

```
autocode/
├── __init__.py
├── schema.py              # 问题数据结构定义
├── transformations.py     # 规则变换引擎
├── llm.py                 # LLM调用模块
├── llm_transformations.py # LLM变换引擎
├── generator.py           # 主程序入口
├── parallel_generator.py  # successful_output 并行处理入口
├── .env                   # API配置文件
├── README.md              # 使用文档
├── autocode.pdf           # 原始论文
└── examples/
    ├── seed_problem.json  # 示例种子题
    └── new_problem.json   # 生成的新题目
```

## 注意事项

1. 使用LLM模式需要有效的OpenAI API密钥
2. 如果使用国内API服务，请设置正确的 `--base-url`
3. LLM生成可能需要较长时间，请耐心等待
4. 建议先使用规则变换模式测试系统功能
5. API密钥请妥善保管，不要提交到代码仓库
