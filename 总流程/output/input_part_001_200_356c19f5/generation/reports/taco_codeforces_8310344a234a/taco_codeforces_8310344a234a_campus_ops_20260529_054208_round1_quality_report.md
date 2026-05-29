# 题目质量与反换皮评估报告

## 总览
- status: reject_as_retheme
- quality_score: 97.0
- divergence_score: 68.0
- schema_distance: 0.3737
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | 题面完全实现了 new_schema 中定义的任务变体、输入对象、约束和目标。所有核心约束（只能选 '.' 格子、全图覆盖、恰好 n 个、集合去重取模）均准确落地，输出格式和可行性条件与 new_schema 一致，无偏差。
- spec_completeness: 5.0 / 5 | 题面提供了独立做题所需的所有关键信息：任务说明（教室检查覆盖、最少次数、计数方案）、输入格式（n 和网格）、输出格式（-1 或 n 与方案数）、约束（n 范围、时空限制）、必要说明（去重、无解条件、取模），读者无需猜测任何规则。
- cross_section_consistency: 5.0 / 5 | 描述、输入格式、输出格式、约束和样例之间完全一致。网格字符定义、最少次数 n、输出值、无解条件、样例输入输出及解释均相互吻合，无任何矛盾。
- sample_quality: 4.0 / 5 | 两个样例分别覆盖了正常矩阵和一行全 E 的退化情况，解释详细且有助于理解计数方法。但缺少无解样例（某行全 E 且某列全 E）和 n=1 等边界样例，对选手测试可能出现疏漏，属于可修复的小瑕疵。
- oj_readability: 5.0 / 5 | 题面结构清晰（标题-描述-输入/输出-约束-样例-注释），校园场景贴近日常，描述通俗易懂。使用恰当的术语和分点说明，无来源污染或无关文本，便于参赛者快速准确理解。

## 优点
- 题面成功地将抽象网格覆盖问题映射为校园教室检查场景，增强了可读性和趣味性。
- 描述准确落实了所有核心约束（选择 '.'、全图覆盖、恰好 n 次、集合去重取模），无逻辑缺失。
- 样例解释详尽，通过具体计算展示了容斥公式的应用，有助于选手理解计数逻辑。
- 输出格式和可行性条件与目标完全一致，无矛盾。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.75
- solution_transfer_risk: 0.3
- surface_retheme_risk: 0.3
- verdict: pass
- rationale: 语义差异显著：新题从构造一个最优净化方案变为计数所有最小方案集合，目标函数、输出要求、核心求解路径均已改变。尽管覆盖规则相同，但必须解决集合去重、容斥计数等新问题，原题贪心构造法无法迁移。表层换皮风险低：故事背景、标题、样例输出均不同，无文本复用迹象。

## 硬检查
- [PASS] source_problem_resolved (blocker/invalid): 已成功加载原题文本。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.37，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=2。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 问题清单
- [minor] quality_issue: 缺少无解和边界样例 | 现有样例未展示无解情况（某行全 E 且某列全 E）和 n=1 的最小边界，可能影响选手对无解条件的理解和边界测试的充分性。
  修复建议: 建议增加一个无解样例，例如 n=2, 'EE
.E' 或类似，输出 -1；再增加一个 n=1 的样例，如 '.' 输出 '1 1'，'E' 输出 -1。

## 建议修改
- 建议增加一个无解样例，例如 n=2, 'EE
.E' 或类似，输出 -1；再增加一个 n=1 的样例，如 '.' 输出 '1 1'，'E' 输出 -1。
- 增添一个无解样例（例如 n=2, 输入 'EE
.E' 或 'EE
EE'）并输出 -1，完善边界覆盖。
- 增添一个 n=1 的样例（如 '.' 输出 '1 1'），确保最小规模情况得到展示。

## 回流摘要
- round_index: 1
- overall_status: reject_as_retheme
- generated_status: ok
- quality_score: 97.0
- divergence_score: 68.0
- strengths_to_keep: 题面成功地将抽象网格覆盖问题映射为校园教室检查场景，增强了可读性和趣味性。；描述准确落实了所有核心约束（选择 '.'、全图覆盖、恰好 n 次、集合去重取模），无逻辑缺失。；样例解释详尽，通过具体计算展示了容斥公式的应用，有助于选手理解计数逻辑。；输出格式和可行性条件与目标完全一致，无矛盾。

## 快照
- original_problem: A
- difference_plan_rationale: 目标从输出具体方案变为计数方案总数，约束中增加去重和模运算要求，不变量从可行性判定变为计数公式与去重逻辑。
