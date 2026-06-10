# 题目质量与反换皮评估报告

## 总览
- status: revise_quality
- quality_score: 60.0
- divergence_score: 83.5
- schema_distance: 0.5125
- generated_status: ok

## 质量维度
- variant_fidelity: 3.0 / 5 | new_schema 中的输入结构、目标函数、核心约束等已在 description、input/output format 和 constraints 中正确落地，但 samples 部分未能准确实现支配前沿规则（第二个查询的输出错误地包含了被支配的对），导致目标函数的落地不完全。
- spec_completeness: 5.0 / 5 | 题面提供了独立求解所需的全部关键信息：任务说明、清晰的支配定义、输入输出格式、各变量约束以及样例解释，读者无需自行猜测核心规则。
- cross_section_consistency: 1.0 / 5 | 第一个样例中第二个查询的输出 '0:0 1:2 2:2' 与 description 中的支配定义及样例解释文字 '前沿为 0:0, 1:2' 存在直接矛盾，(2,2) 应被 (1,2) 支配而不该出现，这一冲突严重破坏题面一致性。
- sample_quality: 1.0 / 5 | 虽然有两个样例，但第一个样例的第二个查询存在输出内容与支配规则相悖的严重错误，会严重误导解题者，样例质量不可接受。
- oj_readability: 5.0 / 5 | 题面结构清晰，措辞明确，采用了温和的社区服务主题，无来源污染或无关文本，符合正常 OJ 题面表达习惯。

## 优点
- 语义映射自然，将原问题巧妙转化为社区服务场景；
- 支配关系与非支配前沿的定义描述精准，易于理解；
- 输入输出格式说明详细，样例解释周到（除矛盾部分外）；
- 约束条件完整，范围明确。

## 与原题差异分析
- changed_axes_planned: I, C, O, V
- changed_axes_realized: I, C, O, V
- semantic_difference: 0.82
- solution_transfer_risk: 0.18
- surface_retheme_risk: 0.2
- verdict: pass
- rationale: 原题是给定所有访问时间点，统计覆盖的不同区间数；新题改为从候选时间点中选择至多B个，最大化覆盖数，并输出非支配前沿。(费用,覆盖)对。任务从计数变为带预算的子集优化与多目标输出，语义差异显著。原题解法依赖所有点顺序累加并去重，无法直接处理子集选择和帕累托前沿；新题需离线预处理both(p,q)并设计DP，解法迁移风险低。表层主题、标题、样例均独立设计，无文本复用痕迹。

## 硬检查
- [PASS] source_problem_resolved (blocker/invalid): 已成功加载原题文本。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.51，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：I, C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=2。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 问题清单
- [major] quality_issue: 样例输出与支配规则矛盾 | 第一个样例的第二个查询输出包含 '2:2'，但根据 description 中的支配定义，(2,2) 被 (1,2) 支配，不应出现在非支配前沿中；同时样例解释文字称前沿为 '0:0, 1:2'，与输出不符。
  修复建议: 修正第二个查询的输出为 '0:0 1:2'，或调整解释以匹配输出，但必须保证输出严格符合支配与非支配前沿的定义。

## 建议修改
- 修正第二个查询的输出为 '0:0 1:2'，或调整解释以匹配输出，但必须保证输出严格符合支配与非支配前沿的定义。
- 修正样例错误，确保所有样例输出与支配规则一致；
- 可在样例解释中增加对支配剔除的显式计算步骤，帮助读者验证。

## 回流摘要
- round_index: 1
- overall_status: revise_quality
- generated_status: ok
- quality_score: 60.0
- divergence_score: 83.5
- strengths_to_keep: 语义映射自然，将原问题巧妙转化为社区服务场景；；支配关系与非支配前沿的定义描述精准，易于理解；；输入输出格式说明详细，样例解释周到（除矛盾部分外）；；约束条件完整，范围明确。

## 快照
- original_problem: DOWNLOAD
- difference_plan_rationale: 输入结构增加了预算 B 和子集选择机制（I），需要增加费用约束和选择性输入（C），将目标从单值计数改为前沿输出（O），并构造 DP 状态与二维查询不变量（V）以保证正确性。
