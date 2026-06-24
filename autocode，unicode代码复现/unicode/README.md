# UniCode 题目增强器

基于 UniCode 思路对算法竞赛题目做扰动增强，支持规则模式和 LLM 模式。

## 安装依赖

```bash
pip install openai
```

如需从 `.env` 文件读取配置，可额外安装：

```bash
pip install python-dotenv
```

未安装 `python-dotenv` 时，程序仍会读取系统环境变量。

## successful_output 并行处理

输入目录应为 `successful_output` 本身。每个直接子目录视为一个题目，程序会读取该题目目录下 `original_input/*.json` 中按文件名排序后的第一个 JSON，并输出到 `other_methods/unicode.json`。

```powershell
python .\unicode\batch_augmenter.py `
  --input "D:\AutoProblemGen\autocode，unicode代码复现\input\successful_output" `
  --use-llm `
  --batch-size 5 `
  --processes 5 `
  --max-tokens 16000
```

规则模式不需要 API key：

```powershell
python .\unicode\batch_augmenter.py `
  --input "D:\AutoProblemGen\autocode，unicode代码复现\input\successful_output" `
  --batch-size 5 `
  --processes 5
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--input` | successful_output 题目目录 | 必需 |
| `--use-llm` | 使用 LLM 生成增强题目 | False |
| `--llm-transformation` | LLM 变换类型：`narrative`、`rule`、`efficiency`、`sequential`、`fusion`、`all` | all |
| `--batch-size` | 每个批次处理的题目数量 | 5 |
| `--processes` | 并行进程数上限 | 5 |
| `--max-tokens` | LLM 生成的最大 completion token 数 | `MAX_TOKENS` 或 16000 |
| `--no-narrative` | 不应用叙事扰动 | False |
| `--no-rule` | 不应用规则修改 | False |
| `--no-efficiency` | 不应用效率缩放 | False |
| `--no-sequential` | 不应用顺序组合 | False |
| `--no-fusion` | 不应用概念融合 | False |

每个批次会在输入目录下写出独立的 `unicode_batch_<n>_log.txt` 和 `unicode_batch_<n>_stats.json`，最终汇总到 `unicode_parallel_stats.json`。
