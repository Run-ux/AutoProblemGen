# 题目质量与反换皮评估报告

## 总览
- status: reject_as_retheme
- quality_score: 100.0
- divergence_score: 68.1
- schema_distance: 0.4615
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中的核心约束（元素多重集不变、代价限制、goodness最大化、代价最小化、字典序最小化）和 objective（构造输出或 -1）在 description、output_format 和 samples 中准确落地；输入结构的多测试用例形式、n 和 k 在每个测试用例一行给出与 new_schema 一致；约束范围（n 之和≤1000，k≤10^14 等）均已体现。
- spec_completeness: 5.0 / 5 | 题面包含了任务说明、输入输出格式、约束、必要的中位数定义、字典序定义、-1 输出注意等辅助说明，选手可据此独立解题。
- cross_section_consistency: 5.0 / 5 | 各部分之间一致：description 中的多目标要求与 output_format 匹配；输入格式与样例对应；样例解释与规则一致；notes 补充的定义无明显矛盾。
- sample_quality: 5.0 / 5 | 提供 3 个样例，覆盖有解与无解情况，样例解释详细，能帮助理解优先级和构造规则，数量足够。
- oj_readability: 5.0 / 5 | 结构清晰，语言通俗，无来源污染，符合 OJ 题面常规表达。

## 优点
- 多级目标描述清晰，样例解释充分，约束完整，字典序定义明确。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.7
- solution_transfer_risk: 0.5
- surface_retheme_risk: 0.3
- verdict: pass
- rationale: 新题将原本的单目标最值查询（最大化最小行中位数）变为多目标规范解构造（最大 goodness → 最小代价 → 字典序最小），输出从整数变为完整矩阵，核心约束与证明义务发生本质变化，语义差异明显。原题的核心二分+贪心构造仍可复用，但必须额外设计最小代价精确分配与字典序构造算法，整体方案不能直接迁移，需显著扩展。题目背景与叙述虽不同，但矩阵元素重排的行中位数概念仍清晰对应，不过新题扩展了优化层级与输出形式，表层文本未直接复用原题表述。

## 硬检查
- [PASS] source_problem_resolved (blocker/invalid): 已成功加载原题文本。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.46，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=3。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 建议修改
- 可考虑增加一个包含多个测试用例的样例，以展示多测试用例输入输出的格式。

## 回流摘要
- round_index: 1
- overall_status: reject_as_retheme
- generated_status: ok
- quality_score: 100.0
- divergence_score: 68.1
- strengths_to_keep: 多级目标描述清晰，样例解释充分，约束完整，字典序定义明确。

## 快照
- original_problem: MEDMAX
- difference_plan_rationale: 必须改变核心约束以引入多目标优先层级（goodness > 代价 > 字典序），改变目标为构造式输出，并更新不变量以支撑新的贪心构造与最小性证明。
