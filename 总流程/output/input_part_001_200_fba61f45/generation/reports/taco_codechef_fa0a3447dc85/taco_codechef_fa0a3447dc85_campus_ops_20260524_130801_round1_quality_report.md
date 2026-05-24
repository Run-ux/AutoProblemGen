# 题目质量与反换皮评估报告

## 总览
- status: reject_invalid
- quality_score: 20.0
- divergence_score: 36.4
- schema_distance: 0.4855
- generated_status: schema_insufficient

## 质量维度
- variant_fidelity: 1.0 / 5 | generated_problem 的所有字段（description, input_format, output_format, constraints, samples）均为空，new_schema 中要求的任务变体、输入结构、约束和目标完全没有落地。
- spec_completeness: 1.0 / 5 | 题面完全缺失任务说明、输入格式、输出格式、约束和样例等独立做题所需的关键信息，读者无法开始做题。
- cross_section_consistency: 1.0 / 5 | 由于各部分内容均为空，不存在明显矛盾，但也完全没有提供有效信息，无法评估一致性，本质上是内容缺失导致的不一致状态。
- sample_quality: 1.0 / 5 | 样例数量为0，缺失样例解释，无法帮助理解题目。
- oj_readability: 1.0 / 5 | 题面没有任何结构化文本，完全不符合 OJ 题面的表达习惯，参赛者无法阅读。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.0
- solution_transfer_risk: 1.0
- surface_retheme_risk: 1.0
- verdict: reject_as_retheme
- rationale: 缺少原题文本，无法完成反换皮判定。

## 硬检查
- [FAIL] source_problem_resolved (blocker/invalid): 无法加载原题文本，不能进行反换皮判定。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [FAIL] generated_status_ok (blocker/invalid): 生成产物状态为 schema_insufficient：new_schema中core_constraints的canonical_ordering强制输出每行升序排列，与valid_permuted_rows结合导致每一行的升序排列唯一且中位数固定，无法实现objective中的最大化最小中位数和字典序选择，算法自由于此丧失，无法构造合理题目。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.49，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 无原题文本，跳过泄露检查。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [FAIL] sample_count (major/quality_issue): 样例数量=0。 少于 2 组。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 问题清单
- [blocker] invalid: source problem resolved | 无法加载原题文本，不能进行反换皮判定。
  修复建议: 显式提供可读取的原题 JSON，确保评测阶段能够加载原题文本。
- [blocker] invalid: generated status ok | 生成产物状态为 schema_insufficient：new_schema中core_constraints的canonical_ordering强制输出每行升序排列，与valid_permuted_rows结合导致每一行的升序排列唯一且中位数固定，无法实现objective中的最大化最小中位数和字典序选择，算法自由于此丧失，无法构造合理题目。
  修复建议: 先修复生成阶段的 schema 或 difference 问题，再重新生成题面。
- [major] quality_issue: sample count | 样例数量=0。 少于 2 组。
  修复建议: 至少补齐两组可验证样例。
- [major] quality_issue: 题面生成失败，内容完全缺失 | generated_problem 状态为 'schema_insufficient'，所有题面字段为空。错误原因为 new_schema 中的 canonical_ordering 与 valid_permuted_rows 结合导致每一行的升序排列唯一且中位数固定，无法实现最大化最小中位数和字典序选择，题目逻辑自洽性丧失。
  修复建议: 需重新设计 new_schema，解决 canonical_ordering 与目标之间的冲突，例如调整排列约束或目标定义，确保题目逻辑合理。
- [major] quality_issue: 样例缺失 | generated_problem 中 samples 字段为空，缺少任何样例数据或解释。
  修复建议: 在题目逻辑修复后，补充至少2组样例，并添加解释说明输出如何达成最优和字典序最小。
- [blocker] retheme_issue: solution transfer risk too high | 缺少原题文本，无法完成反换皮判定。
  修复建议: 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。

## 建议修改
- 显式提供可读取的原题 JSON，确保评测阶段能够加载原题文本。
- 先修复生成阶段的 schema 或 difference 问题，再重新生成题面。
- 至少补齐两组可验证样例。
- 需重新设计 new_schema，解决 canonical_ordering 与目标之间的冲突，例如调整排列约束或目标定义，确保题目逻辑合理。
- 在题目逻辑修复后，补充至少2组样例，并添加解释说明输出如何达成最优和字典序最小。
- 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。
- 重新审视 new_schema 中 canonical_ordering 的定义，使其不影响行内元素的选择自由度，例如允许任意排列但仅要求输出时按升序打印，或修改目标层次以消除逻辑矛盾。
- 修复生成逻辑后，确保 description, input_format, output_format, constraints, samples 齐全，并满足 spec_completeness 要求。
- 增加至少两组样例，覆盖基本情况和边界情况，并附上详细解释。
- 优先改写核心任务定义，而不是继续替换故事背景。

## 回流摘要
- round_index: 1
- overall_status: reject_invalid
- generated_status: schema_insufficient
- quality_score: 20.0
- divergence_score: 36.4

## 快照
- original_problem: 
- difference_plan_rationale: 必须改变核心约束以引入规范顺序与字典序最小的定义，改变目标从求值到输出具体方案，改变不变量以支撑逐行贪心构造字典序解的正确性。这些改动相互关联，共同实现从答案输出到规范解输出的升级。
