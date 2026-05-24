# 题目质量与反换皮评估报告

## 总览
- status: reject_invalid
- quality_score: 100.0
- divergence_score: 39.5
- schema_distance: 0.5267
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中的所有关键要素（输入结构、核心约束、目标函数、不变量的位段分解）均准确落地到 generated_problem 的 description、input_format、output_format、constraints 和 samples 中，无遗漏或偏差。
- spec_completeness: 5.0 / 5 | 题面包含了独立做题所需的所有关键信息：任务说明（服务礼包、最小点数、计数规则）、输入输出格式、约束条件、样例及解释，并且通过 notes 补充了 C=0 的边界情况，无关键信息缺失。
- cross_section_consistency: 5.0 / 5 | description、constraints、samples 和 notes 之间完全一致，服务量定义、异或条件、最小点数要求、计数顺序、模数等在各处均无矛盾，位段分解性质也与其他部分协调。
- sample_quality: 5.0 / 5 | 提供了两个样例，覆盖了 C=1（最小点数=1）和 C=2（最小点数=2）的典型情景，解释清晰，能够帮助理解题意；notes 中对 C=0 的说明弥补了未直接给出对应样例的不足。
- oj_readability: 5.0 / 5 | 题面结构规范（标题、描述、输入/输出格式、约束、样例、注释），用词温和且准确，无来源污染或无关文本，便于参赛者快速理解。

## 优点
- 准确实现了 new_schema 中所有变体元素
- 题面信息完整、一致
- 样例解释清晰，覆盖典型情况
- 提供了位段分解性质和 C=0 的特殊情况说明，有助于选手理解

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
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.53，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 无原题文本，跳过泄露检查。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=2。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 问题清单
- [blocker] invalid: source problem resolved | 无法加载原题文本，不能进行反换皮判定。
  修复建议: 显式提供可读取的原题 JSON，确保评测阶段能够加载原题文本。
- [blocker] retheme_issue: solution transfer risk too high | 缺少原题文本，无法完成反换皮判定。
  修复建议: 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。

## 建议修改
- 显式提供可读取的原题 JSON，确保评测阶段能够加载原题文本。
- 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。
- 优先改写核心任务定义，而不是继续替换故事背景。

## 回流摘要
- round_index: 1
- overall_status: reject_invalid
- generated_status: ok
- quality_score: 100.0
- divergence_score: 39.5
- strengths_to_keep: 准确实现了 new_schema 中所有变体元素；题面信息完整、一致；样例解释清晰，覆盖典型情况；提供了位段分解性质和 C=0 的特殊情况说明，有助于选手理解

## 快照
- original_problem: 
- difference_plan_rationale: 改变目标从最优化到计数，增加计数对象定义和去重规则，并引入新的不变量支撑计数分解。
