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

先冻结候选题 manifest。若目标是最终拿到 80 个成功完成的题，建议使用大于 80 的候选池，失败或中断过的题默认不会重跑：

```powershell
python D:\AutoProblemGen\实验_消融实验\main.py build-manifest `
  --output D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_pool_148.json `
  --sample-size 148
```

若需要在原 148 题之外补充 C++14/C++17 真实提交评测题，可单独生成新增题 manifest：

```powershell
python D:\AutoProblemGen\实验_消融实验\main.py build-manifest `
  --output D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_cpp14_17_extra_min_right_1_min_wrong_40.json `
  --sample-size 144 `
  --min-right 1 `
  --min-wrong 40 `
  --language-regex 'C\+\+14|C\+\+17' `
  --exclude-manifest D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_pool_148.json
```

运行实验。首次建议用 `--limit 1` 冒烟测试，确认 LLM 配置和执行环境正常：

```powershell
python D:\AutoProblemGen\实验_消融实验\main.py run `
  --manifest D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_pool_148.json `
  --output-root D:\AutoProblemGen\实验_消融实验\output `
  --run-id testcase_eval_80 `
  --workflow-config D:\AutoProblemGen\总流程\workflow.env `
  --limit 1
```

同一个 manifest 可以按 1 基闭区间拆分到多个终端并行运行；多个终端使用同一个 `--run-id` 时，最终仍用同一个 `report` 汇总：

```powershell
# 终端 1：第 1-37 题
python D:\AutoProblemGen\实验_消融实验\main.py run `
  --manifest D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_pool_148.json `
  --output-root D:\AutoProblemGen\实验_消融实验\output `
  --run-id testcase_eval_80 `
  --workflow-config D:\AutoProblemGen\总流程\workflow.env `
  --start-index 1 `
  --end-index 37

# 终端 2：第 38-74 题
python D:\AutoProblemGen\实验_消融实验\main.py run `
  --manifest D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_pool_148.json `
  --output-root D:\AutoProblemGen\实验_消融实验\output `
  --run-id testcase_eval_80 `
  --workflow-config D:\AutoProblemGen\总流程\workflow.env `
  --start-index 38 `
  --end-index 74

# 终端 3：第 75-111 题
python D:\AutoProblemGen\实验_消融实验\main.py run `
  --manifest D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_pool_148.json `
  --output-root D:\AutoProblemGen\实验_消融实验\output `
  --run-id testcase_eval_80 `
  --workflow-config D:\AutoProblemGen\总流程\workflow.env `
  --start-index 75 `
  --end-index 111

# 终端 4：第 112-148 题
python D:\AutoProblemGen\实验_消融实验\main.py run `
  --manifest D:\AutoProblemGen\实验_消融实验\manifests\testcase_eval_pool_148.json `
  --output-root D:\AutoProblemGen\实验_消融实验\output `
  --run-id testcase_eval_80 `
  --workflow-config D:\AutoProblemGen\总流程\workflow.env `
  --start-index 112 `
  --end-index 148
```

汇总报告：

```powershell
python D:\AutoProblemGen\实验_消融实验\main.py report `
  --run-dir D:\AutoProblemGen\实验_消融实验\output\testcase_eval_80
```

若本地执行器修复后需要只回填已完成题目的错误解池增强结果，先做只读预检：

```powershell
python D:\AutoProblemGen\实验_消融实验\main.py backfill-wrong-pool `
  --dry-run `
  --run-dir D:\AutoProblemGen\实验_消融实验\output\testcase_eval_cpp14_17_extra_min_right_1_min_wrong_40 `
  --run-dir D:\AutoProblemGen\实验_消融实验\output\testcase_eval_80
```

确认没有对应实验进程仍在写同一目录后，再执行就地回填。该命令只处理 `completed` 题，复用已有生成产物，重算错误解池、重建三组套件、重新评测真实提交，并重新生成报告：

```powershell
python D:\AutoProblemGen\实验_消融实验\main.py backfill-wrong-pool `
  --run-dir D:\AutoProblemGen\实验_消融实验\output\testcase_eval_cpp14_17_extra_min_right_1_min_wrong_40 `
  --run-dir D:\AutoProblemGen\实验_消融实验\output\testcase_eval_80
```

若把回填任务拆到多个终端并行运行，每个分片命令应加 `--skip-report`，避免多个进程同时覆盖报告文件；全部分片结束后再对每个 run 目录单独执行一次 `report`。

## 说明

- 首版只使用 `Python 3`、`PyPy 3` 和 `PyPy 3-64` 提交，不使用 Python 2。
- C++ 真实提交评测需要本机 `g++` 在 `PATH` 中；当前只承诺 `C++14` 和 `C++17`，不默认纳入 `C++20`、`C++23`。
- C++17 提交会先用 `gnu++17` 编译；若本机 MinGW 头文件导致编译失败，会降级尝试 `gnu++14`，仍失败则记录为编译错误。
- manifest 默认每题至少需要 3 个正确提交和 50 个错误提交，并固定选取最多 3 个正确提交、50 个错误提交进入评测。
- 在默认筛选条件下，当前 TestCase-Eval 数据源最多可用 148 题；若需要更多候选题，必须显式放宽筛选条件。
- 默认断点续跑按题目目录判断是否已尝试：`completed`、`failed`、已有目录但无 `result.json`、损坏 `result.json` 都会跳过；只有完全没有题目目录的新题会继续运行。
- 只有确实需要重跑已尝试题时才使用 `--no-resume`，否则不要添加该参数。
- TestCase-Eval 正确提交不参与测试输出构造；输出由本项目生成的暴力解、标准解和大规模真值流程产生。
- 测试用例输入和期望输出与真实提交语言无关；C++ 支持只影响最终外部评测阶段的编译与运行。
- `size_control` 用于控制“用例数量增加”这一混杂因素，判断 targeted 输入是否带来额外覆盖。
- 并行分片运行时，`run_metadata.json` 和 `run_summary.json` 可能被不同终端覆盖；正式结果以 `report` 扫描到的各题 `result.json` 为准。
