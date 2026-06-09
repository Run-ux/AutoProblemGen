# 题目质量与反换皮评估报告

## 总览
- status: pass
- quality_score: 100.0
- divergence_score: 78.6
- schema_distance: 0.4419
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | 题面准确实现了 new_schema 的所有要求：输入包含物品数量、物品属性列表和目标 K；约束涵盖了覆盖条件、允许修改及代价、目标最小支付条件；目标为最小化修改代价并输出方案，若不可能输出 -1。描述与 new_schema 高度一致。
- spec_completeness: 5.0 / 5 | 题面包含了独立做题所需的全部信息：任务说明、输入输出格式、约束（数据范围、修改后值域）、样例及解释、注意事项（使用 64 位整数、输出任意方案）。无关键规则或边界条件遗漏。
- cross_section_consistency: 5.0 / 5 | description、input_format、output_format、constraints、samples 之间完全一致：物品数量、属性描述、目标 K 位置、修改代价计算、输出格式无矛盾。样例与约束相符，解释正确。
- sample_quality: 5.0 / 5 | 提供了 3 个样例，覆盖 n=1 无需修改、n=2 修改两个物品、n=3 修改单个物品的情况，每个样例均有详细解释，帮助理解题意。数量足够，解释清晰。
- oj_readability: 5.0 / 5 | 题面结构清晰，措辞明确，无冗余或无关信息。输入输出格式规范，约束单独列出，样例解释有助于理解。符合 OJ 常规表达习惯。

## 优点
- 完全忠实地将 new_schema 转化为可做题面，无遗漏或偏离。
- 约束和目标定义严谨，修改代价及最优方案要求清楚。
- 样例覆盖了多种情况，解释详尽，帮助选手理解。
- 题面本土化自然，无原题泄露。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.85
- solution_transfer_risk: 0.2
- surface_retheme_risk: 0.2
- verdict: pass
- rationale: 新题将任务从‘给定输入求最小支付’逆转为‘设计输入使最小支付等于目标K，且总修改代价最小’，语义发生实质性变化。原题DP仅能作为验证子模块，无法直接迁移为主算法；需要设计新的多维DP搜索修改空间。题面叙事完全不同，无文本或结构复用，表面换皮风险低。

## 硬检查
- [PASS] source_problem_resolved (blocker/invalid): 已成功加载原题文本。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.44，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=3。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 回流摘要
- round_index: 7
- overall_status: pass
- generated_status: ok
- quality_score: 100.0
- divergence_score: 78.6
- strengths_to_keep: 完全忠实地将 new_schema 转化为可做题面，无遗漏或偏离。；约束和目标定义严谨，修改代价及最优方案要求清楚。；样例覆盖了多种情况，解释详尽，帮助选手理解。；题面本土化自然，无原题泄露。

## 快照
- original_problem: B
- difference_plan_rationale: 必须改变核心约束以引入修改操作和目标支付条件；目标从最小化支付转为最小化修改代价并输出方案；不变量从原 DP 最优子结构更新为逆向设计最优性的证明结构。
