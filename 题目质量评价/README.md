# 题目质量评价

该目录提供“题面质量 + 反换皮”单题评估器。当前版本只支持 `生成题面` 的 v3 artifact 合同，直接消费 `生成题面/artifacts/*.json`，同时读取源 schema，并通过 `--original-problem` 显式加载原题 JSON，输出：

- `reports/json/*_quality_report.json`
- `reports/md/*_quality_report.md`

## 当前合同

评测器当前要求 artifact 至少包含以下字段：

- `new_schema` 或兼容字段 `new_schema_snapshot`
- `difference_plan`
- `predicted_schema_distance`
- `distance_breakdown`
- `changed_axes_realized`
- `generated_problem`

其中：

- `new_schema` 是评审语义层使用的统一名称。若上游仍输出旧字段 `new_schema_snapshot`，评测器会兼容读取
- `difference_plan` 用于记录规划差异轴与规划理由
- `predicted_schema_distance`、`distance_breakdown`、`changed_axes_realized` 由上游直接提供，评测器只做校验和透传，不在本地重算
- `generated_problem` 是唯一题面来源。评测流程不会解析 Markdown，也不会用 Markdown 回填结构化字段

`planning_status`、`planning_error_reason`、`planning_feedback` 会作为失败状态与错误信息的补充来源。若 `generated_problem.status` 缺失，评测器会优先使用 `planning_status`。

Judge 还会额外参考 `review_context`。该上下文由评测器从 artifact 中提取，只包含结构化规划信息：

- `difference_plan.summary`
- `difference_plan.mode`
- `difference_plan.changed_axes`
- `changed_axes_realized`
- `distance_breakdown`
- `applied_rule`
- `applied_helpers`
- `algorithmic_delta_claim`
- `anti_shallow_rationale`

以下字段不会进入 Judge 输入：

- `selection_trace`
- `validation_trace`
- `candidate_attempts`
- `rule_selection_reason`

若缺少 `predicted_schema_distance`、`distance_breakdown` 或 `changed_axes_realized`，artifact 会直接判为无效。

## 核心能力

- 质量评分：`variant_fidelity`、`spec_completeness`、`cross_section_consistency`、`sample_quality`、`oj_readability`
- 反换皮判定：基于 `schema_distance`、`changed_axes`、原题文本对比和 `solution_transfer_risk`
- 状态输出：`pass`、`revise_quality`、`reject_as_retheme`、`reject_invalid`

## 运行

```bash
python main.py ^
  --schema D:\AutoProblemGen\四元组抽取\output\batch\normalized\CF1513D.json ^
  --artifact D:\AutoProblemGen\生成题面\artifacts\CF1513D_v1_campus_ops_20260409_225026.json ^
  --original-problem D:\AutoProblemGen\原题数据\CF1513D.json
```

当前版本强制要求可用的 LLM Judge。若没有可用的 `QWEN_API_KEY`、`DASHSCOPE_API_KEY` 或显式传入的 `judge_client`，评测会直接报错。质量评审与反换皮评审一旦调用失败、超时或返回不合格 JSON，也会直接报错，不再回退到启发式评分。

`--original-problem` 是必选参数。调用方需要显式提供原题 `dict` 或原题 JSON 路径，评测器不再按 `source` 和 `problem_id` 从题库自动查找原题。

默认情况下，报告会保存到当前项目目录下的 `reports/json` 和 `reports/md`。如需覆盖该行为，可显式传入 `--output-json` 或 `--output-md`。`--markdown` 参数会保留到报告快照中，但不会参与题面解析。报告快照中的 schema 路径统一使用 `snapshots.new_schema`。

## 测试

```bash
python -m unittest discover -s D:\AutoProblemGen\题目质量评价\tests -v
```

测试基线当前覆盖：

- v3 artifact 成功评测与差异字段透传
- `--original-problem` 必选参数校验与解析
- 原题 JSON 路径加载回归
- `planning_status` 到 `generated_status` 的映射
- 只提供 `new_schema` 的成功评测
- 只提供 `new_schema_snapshot` 的兼容读取
- 同时缺少 `new_schema` 与 `new_schema_snapshot` 的无效 artifact
- 缺少差异字段时的无效 artifact
- LLM 评审失败或返回非法结果时的报错路径
