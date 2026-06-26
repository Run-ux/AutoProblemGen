# 生成题质量评测实验

本模块参考 UniCode 的算法题评测思路，让多个 LLM 在只看到完整题面的条件下独立生成一次 Python 解答，并通过冻结的隐藏测试集计算 pass@1、随机/对抗测试差距和经验难度。

第一阶段只评测生成题。Manifest 已预留 `problem_kind`、`pair_id` 和 `algorithm_tags`，后续可以加入母题并计算配对性能下降。

## 评测口径

- 每个模型对每道题只生成一个候选，API 传输重试不产生新候选。
- 模型只能看到题面，不会看到 schema、生成规则、标准解、checker 或测试数据。
- 候选必须定义 `solve(input_str: str) -> str`，当前只支持标准 Python。
- 一道题必须同时通过 `random`、`adversarial`、`small_challenge` 和 `large_scale` 四类测试，才记为 pass@1 成功。
- 有 checker 的题使用已经通过验证闭环的 checker；其他题严格比较输出字符串。
- API、网络和服务端错误记为 `infrastructure_error`，不计入模型失败，下一次运行会自动补跑。
- 模型答题失败包括响应解析错误、语法/接口错误、运行错误、超时、内存超限、错误答案和 checker 错误。

经验难度基于完整模型的通过比例：

- `easy`：通过率大于等于 `2/3`
- `medium`：通过率大于等于 `1/3` 且小于 `2/3`
- `hard`：通过率小于 `1/3`

少于三个完整模型时仍输出逐题通过率，但不形成正式难度分档。

## 1. 冻结题目清单

```powershell
python D:\AutoProblemGen\实验\main.py build-manifest `
  --workflow-output-root D:\AutoProblemGen\总流程\successful_output `
  --output D:\AutoProblemGen\实验\manifests\generated_v1.json
```

清单默认从 `successful_output` 的每题导出目录构建，并冻结其中本地复制的生成 artifact 和验证 artifact。旧版 `总流程\output` 的 `workflow_summary.json` 目录树仍兼容。清单只收录工作流状态为 `verified` 且四类真值完整的题目。大规模真值必须为 `status=ok` 且没有失败项。若使用旧版 workflow output，且同一生成题出现在多个历史 run 中，只选择修改时间最新的有效版本，其他版本记录为 `superseded_duplicate`。

命令同时生成 `generated_v1_excluded.json`，记录未收录题目及原因。Manifest 保存生成 artifact 和验证 artifact 的 SHA-256；运行实验前会重新校验，文件变化时 fail-fast，避免实验样本静默漂移。

## 2. 配置模型

复制 `models.example.json` 为自用配置文件。支持三种密钥来源；直接填写 `api_key` 时优先使用该字段，未填写时保持原有 `api_key_env` 或 `config_file` 读取规则：

- `api_key`：直接在 JSON 中填写密钥，运行时从当前模型配置读取。
- `config_file`：读取现有 dotenv 文件中的 `API_KEY`、`BASE_URL`、`MODEL`、`TIMEOUT_SECONDS` 和 `MAX_RETRIES`。
- `api_key_env`：从指定环境变量读取密钥，其他字段直接写在 JSON 中。

示例：

```json
{
  "concurrency": {
    "problems": 200,
    "models_per_problem": 6
  },
  "models": [
    {
      "id": "qwen-main",
      "model": "qwen3.6-plus",
      "base_url": "https://example.com/v1",
      "api_key": "replace-with-api-key",
      "temperature": 0,
      "input_price_per_million": null,
      "output_price_per_million": null
    }
  ]
}
```

配置指纹不包含 API Key，结果文件也不会保存 API Key。若直接在 JSON 中填写真实密钥，应将自用配置文件保留在本地，避免提交到仓库。只有同时配置输入、输出每百万 token 单价时才计算美元成本。

`concurrency` 默认为 `1`，兼容旧配置，等价于 `problems=1`、`models_per_problem=1`。新版对象配置含义如下：

- `problems`：同时调度的题目 worker 数。
- `models_per_problem`：同一道题内同时调用的模型数。

最大同时模型调用数约为 `problems * models_per_problem`，并会受题目数和模型数自然截断。例如 200 道题、6 个模型、`problems=200`、`models_per_problem=6` 时，最多会同时发起约 1200 个模型调用。若遇到官网限流、连接错误或本机资源吃紧，应先降低这两个值。正式报告会记录请求并发和实际生效并发。

## 3. 运行实验

```powershell
python D:\AutoProblemGen\实验\main.py run `
  --manifest D:\AutoProblemGen\实验\manifests\generated_v1.json `
  --models D:\AutoProblemGen\实验\models.json `
  --output-root D:\AutoProblemGen\实验\output `
  --run-id generated_v1
```

结果写入 `output/<run_id>/results/<model>/<problem>.json`。每条结果记录统一提示词、原始 API 响应、token、延迟、提取代码、逐用例判定和资源消耗。

相同 manifest、模型配置指纹、题目和 attempt 的 `completed` 结果会跳过。`infrastructure_error` 会在重跑时再次调用；模型生成出的错误代码不会自动修复或重新采样。

## 4. 生成报告

```powershell
python D:\AutoProblemGen\实验\main.py report `
  --run-dir D:\AutoProblemGen\实验\output\generated_v1
```

输出包括：

- `problem_model_results.csv`：模型与题目级明细。
- `model_summary.csv`：Pass@1、RandPass、AdvPass、Adv-Rand、SmallChallengePass、LargeScalePass、Wilson 95% 置信区间、平均输出 token 和可选平均成本。
- `problem_difficulty.csv`：逐题模型通过率和经验难度。
- `group_summary.csv`：按生成规则、变更轴、来源平台及可选算法标签分组。
- `summary.json`：机器可读汇总和数据完整性状态。
- `report.md`：实验摘要与模型排名。

只要任一配置模型存在缺失结果或基础设施错误，报告状态就是 `incomplete`；正式排名只纳入完整覆盖全部冻结题目的模型。

## 测试

```powershell
python -m unittest discover -s D:\AutoProblemGen\实验\tests -v
```

测试使用假模型，不会请求真实 API。
