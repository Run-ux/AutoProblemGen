# 题目质量与反换皮评估报告

## 总览
- status: reject_invalid
- quality_score: 100.0
- divergence_score: 26.5
- schema_distance: 0.3534
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中定义的所有核心要素均已准确落地：输入结构（n, k, a_i）、相邻座位约束、组人数约束、字典序输出目标在 description、input_format、output_format 和 constraints 中均得到清晰表达，无遗漏或偏离。
- spec_completeness: 5.0 / 5 | 题面提供了独立解题所需的所有关键信息：任务描述清晰，输入/输出格式完整，约束明确，字典序定义清楚，且提供了样例解释。唯一小瑕疵是 notes 中关于“总人数必须等于 8n 否则输出 -1”的提示与 input_format 中“保证总和等于 8n”存在冗余，但不影响理解。
- cross_section_consistency: 5.0 / 5 | description、input_format、output_format、constraints 和 samples 之间无矛盾：座位相邻规则一致，总人数与座位数匹配，字典序定义统一，样例输入输出与规则相符，解释准确。
- sample_quality: 5.0 / 5 | 样例数量充足（3 个），覆盖了有解字典序最小、有解全大块分配、无解三种典型情况，每个样例均有详细解释，有助于选手验证理解和调试。
- oj_readability: 5.0 / 5 | 题面结构规整、语言流畅、无无关信息，符合标准 OJ 题面的表达习惯，易于快速准确理解。

## 优点
- 题面完整且准确地落地了 new_schema 中的所有约束和目标，包括字典序最小这一高优先级要求。
- 样例设计质量高：覆盖有解字典序最小、有解简单分配、无解三种情况，解释详尽，有助于选手理解。
- 语言清晰、结构标准，符合 OJ 题面习惯，可读性强。

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
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.35，达到中等差异阈值。
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
- [minor] quality_issue: 冗余的总和检查提示 | input_format 中已明确“保证总和等于 8n”，但 notes 中又写“总人数必须恰好等于 8n。如果输入不满足该条件，同样应输出 -1”，两者功能重复，可能让选手对是否需要主动校验产生疑惑。
  修复建议: 移除 notes 中关于总和检查的说明，或将其改为“输入数据保证总和等于 8n，无需额外判断”。
- [blocker] retheme_issue: solution transfer risk too high | 缺少原题文本，无法完成反换皮判定。
  修复建议: 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。

## 建议修改
- 显式提供可读取的原题 JSON，确保评测阶段能够加载原题文本。
- 移除 notes 中关于总和检查的说明，或将其改为“输入数据保证总和等于 8n，无需额外判断”。
- 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。
- 建议统一 notes 与 input_format 中关于总人数的描述，消除可能引起的混淆。
- 如希望进一步降低选手负担，可在 description 中明确“输入数据保证总和为 8n”，避免冗余提示。
- 优先改写核心任务定义，而不是继续替换故事背景。

## 回流摘要
- round_index: 1
- overall_status: reject_invalid
- generated_status: ok
- quality_score: 100.0
- divergence_score: 26.5
- strengths_to_keep: 题面完整且准确地落地了 new_schema 中的所有约束和目标，包括字典序最小这一高优先级要求。；样例设计质量高：覆盖有解字典序最小、有解简单分配、无解三种情况，解释详尽，有助于选手理解。；语言清晰、结构标准，符合 OJ 题面习惯，可读性强。

## 快照
- original_problem: 
- difference_plan_rationale: 核心约束增加字典序最小要求，目标从判断变为构造并输出最优解，不变量从单纯可行性转为贪心构造的合法性保持。
