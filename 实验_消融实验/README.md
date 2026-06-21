# 消融实验：TestCase-Eval 外部提交评测

本模块用于评测生成测试用例的正确率与覆盖率。实验从 TestCase-Eval 抽取原题和真实提交；测试输入、标准输出、错误解池和 targeted 补测均由本项目现有方法生成，TestCase-Eval 的真实提交只用于最终外部评测。

## 实验组

- `unicode_style_baseline`：20 条 random、20 条 adversarial、10 条 small_challenge/corner，不含 targeted 输入。
- `ours_pipeline`：baseline 加现有错误解池 targeted 补测，targeted 数量由停止条件决定。
- `size_control`：baseline 加额外非定向 random/adversarial 输入，使每题有效用例数匹配 `ours_pipeline`。

## 指标

- `Correctness`：真实正确提交通过率。
- `Coverage`：真实错误提交被拒绝比例。
- `SemanticCoverage`：排除运行错误、超时、内存超限后的错误答案拦截率。
- `TargetedGain`：`ours_pipeline.coverage - unicode_style_baseline.coverage`。
- `SizeControlledGain`：`ours_pipeline.coverage - size_control.coverage`。
- `CorrectnessDrop`：`unicode_style_baseline.correctness - ours_pipeline.correctness`。

## 运行

先冻结 80 题 manifest：

```powershell
python D:\AutoProblemGen\实验_消融实验\main.py build-manifest `
  --output D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_80.json
```

运行实验。首次建议用 `--limit 1` 冒烟测试，确认 LLM 配置和执行环境正常：

```powershell
python D:\AutoProblemGen\实验_消融实验\main.py run `
  --manifest D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_80.json `
  --output-root D:\AutoProblemGen\实验_消融实验\output `
  --run-id testcase_eval_80 `
  --workflow-config D:\AutoProblemGen\总流程\workflow.env `
  --limit 1
```

同一个 manifest 可以按 1 基闭区间拆分到多个终端并行运行；多个终端使用同一个 `--run-id` 时，最终仍用同一个 `report` 汇总：

```powershell
# 终端 1：第 1-20 题
python D:\AutoProblemGen\实验_消融实验\main.py run `
  --manifest D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_80.json `
  --output-root D:\AutoProblemGen\实验_消融实验\output `
  --run-id testcase_eval_80 `
  --workflow-config D:\AutoProblemGen\总流程\workflow.env `
  --start-index 1 `
  --end-index 20

# 终端 2：第 21-40 题
python D:\AutoProblemGen\实验_消融实验\main.py run `
  --manifest D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_80.json `
  --output-root D:\AutoProblemGen\实验_消融实验\output `
  --run-id testcase_eval_80 `
  --workflow-config D:\AutoProblemGen\总流程\workflow.env `
  --start-index 21 `
  --end-index 40
```

汇总报告：

```powershell
python D:\AutoProblemGen\实验_消融实验\main.py report `
  --run-dir D:\AutoProblemGen\实验_消融实验\output\testcase_eval_80
```

## 说明

- 首版只使用 `Python 3`、`PyPy 3` 和 `PyPy 3-64` 提交，不使用 Python 2。
- manifest 默认每题至少需要 3 个正确提交和 50 个错误提交，并固定选取最多 3 个正确提交、50 个错误提交进入评测。
- TestCase-Eval 正确提交不参与测试输出构造；输出由本项目生成的暴力解、标准解和大规模真值流程产生。
- `size_control` 用于控制“用例数量增加”这一混杂因素，判断 targeted 输入是否带来额外覆盖。
- 并行分片运行时，`run_metadata.json` 和 `run_summary.json` 可能被不同终端覆盖；正式结果以 `report` 扫描到的各题 `result.json` 为准。
