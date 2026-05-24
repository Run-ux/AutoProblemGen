# 题目质量与反换皮评估报告

## 总览
- status: reject_invalid
- quality_score: 100.0
- divergence_score: 37.6
- schema_distance: 0.502
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中定义的任务变体（图恰有一个简单环、N 范围、输出字典序最小环序列）准确体现在 generated_problem 的 description, input_format, output_format, constraints, samples 中。仅有小瑕疵如无自环未在输入格式中显式提及，但约束中已涵盖。
- spec_completeness: 5.0 / 5 | 题面提供了清晰的任务说明、输入输出格式、约束、样例和字典序比较解释，足以独立做题。边数通过输入行列数隐含，图的性质明确。
- cross_section_consistency: 5.0 / 5 | 描述、输入输出格式、约束、样例之间一致。样例输出满足第一个与最后一个元素相邻的要求，环序列符合字典序最小。Notes 关于唯一性的说明与题目不矛盾。
- sample_quality: 5.0 / 5 | 三个样例覆盖了全环、四元环以及含树杈的环，并解释字典序最小性，能帮助理解题意。数量适中。
- oj_readability: 5.0 / 5 | 题面结构清晰，校园主题映射自然，用词易懂，无来源污染噪声。

## 优点
- 主题映射贴近校园生活，有趣且易懂
- 样例设计合理，覆盖了简单和带树杈的环，解释充分
- 题面各部分格式规范、一致

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
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.50，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 无原题文本，跳过泄露检查。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=3。
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
- divergence_score: 37.6
- strengths_to_keep: 主题映射贴近校园生活，有趣且易懂；样例设计合理，覆盖了简单和带树杈的环，解释充分；题面各部分格式规范、一致

## 快照
- original_problem: 
- difference_plan_rationale: 按照规则要求，必须改变核心约束、目标和不变式，通过引入规范解输出，将距离计算替换为环序列的构造与证明。
