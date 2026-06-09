# 题目质量与反换皮评估报告

## 总览
- status: pass
- quality_score: 100.0
- divergence_score: 73.9
- schema_distance: 0.3783
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | 题面准确实现了 new_schema 中定义的任务变体、输入结构、目标函数和所有核心约束。输入格式匹配 formula 和 target_digit；输出格式包括最小修改次数与可验证的修改后等式；编辑操作和约束在题面中有清晰逐条对应。
- spec_completeness: 5.0 / 5 | 题面包含完整的任务描述、输入输出格式、约束列表、样例和注意说明，所有独立做题所需信息均已提供，无需读者猜测。
- cross_section_consistency: 5.0 / 5 | description、输入输出格式、约束和样例之间高度一致，无矛盾。例如修改规则、d 的禁止出现、数值约束在样例中得到体现。
- sample_quality: 5.0 / 5 | 包含 5 个样例，覆盖直接解、最小修改、无已知数字、负号处理和无解情况，每个样例都附带清晰的解释，便于理解。
- oj_readability: 5.0 / 5 | 题面结构清晰，分部分叙述，语言通顺，场景日常而不干扰技术理解，符合 OJ 题面风格。无来源污染。

## 优点
- 理解题意的关键在于修改操作和禁止 d 出现的说明非常细致
- 样例设计典型且解释充分，覆盖多种边界情况
- 输出格式能够作为修改方案的证书，直接对比即可验证
- 约束和说明完整，便于评测与实现

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.85
- solution_transfer_risk: 0.2
- surface_retheme_risk: 0.3
- verdict: pass
- rationale: 新题将求解方向从“给定含未知数字的表达式，求最小可能的未知数字”逆转为“给定目标数字，求使表达式成立的最小编辑次数”。这引入了编辑操作空间、广度优先搜索、最优性证明和证书输出等全新核心责任，与原始问题仅需枚举10个候选数字并求值有本质差异。即便原题解析器、前导零检查等子程序可复用，整体算法框架无法直接迁移，需重新建模。表层叙事从考古转为公交班次，有明显换主题，但题目结构差异足以构成不同问题。

## 硬检查
- [PASS] source_problem_resolved (blocker/invalid): 已成功加载原题文本。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.38，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=5。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 回流摘要
- round_index: 4
- overall_status: pass
- generated_status: ok
- quality_score: 100.0
- divergence_score: 73.9
- strengths_to_keep: 理解题意的关键在于修改操作和禁止 d 出现的说明非常细致；样例设计典型且解释充分，覆盖多种边界情况；输出格式能够作为修改方案的证书，直接对比即可验证；约束和说明完整，便于评测与实现

## 快照
- original_problem: 546d15cebed2e10334000ed9
- difference_plan_rationale: 核心约束从“找出满足所有条件的未知数字”变为“通过修改已知数字使给定 d 成为解并证明最小性”，引入了编辑操作空间和一套操作合法性条件；目标从最小化 d 变为最小化修改次数，并要求输出具体修改方案作为证书；不变量从升序枚举 d 变为按编辑距离递增的广度优先状态探索。
