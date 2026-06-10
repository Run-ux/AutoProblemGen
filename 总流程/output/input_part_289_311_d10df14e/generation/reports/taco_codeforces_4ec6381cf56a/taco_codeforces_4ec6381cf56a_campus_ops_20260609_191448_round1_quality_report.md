# 题目质量与反换皮评估报告

## 总览
- status: pass
- quality_score: 100.0
- divergence_score: 74.8
- schema_distance: 0.4079
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中的所有关键要素（输入字段、目标函数、核心约束、结构选项）都准确落地到 generated_problem 的描述、输入/输出格式、约束和样例中，未发现遗漏或扭曲。
- spec_completeness: 5.0 / 5 | 题面提供了独立解题所需的全部关键信息：任务说明、输入格式、输出格式、约束条件、模数、容量范围以及无解处理，且额外说明了排序可行性。缺失信息（如不可达性样例）不影响基本理解。
- cross_section_consistency: 5.0 / 5 | description、input_format、output_format、constraints、samples 之间相互一致，字段数量、目标定义、解释与样例对应，无矛盾。
- sample_quality: 5.0 / 5 | 两个样例覆盖了基本操作和最小次数推理，解释详细，有助于理解任务。hard_checks 中 sample_count 通过，未发现格式或逻辑错误。
- oj_readability: 5.0 / 5 | 题面结构清晰，语言直白，无来源污染，符合 OJ 题面习惯。主题接地气，易于理解。

## 优点
- 题意转换自然，将抽象算法条件包装为贴近生活的校园场景。
- 样例解释清晰，逐步展示修改策略和最少性论证。
- 关键约束（模数、值域、排序无关性）在描述和注释中明确强调。
- 输入/输出格式简洁，便于选手解析。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.85
- solution_transfer_risk: 0.25
- surface_retheme_risk: 0.15
- verdict: pass
- rationale: 原题是正向计算所有子序列的 beauty 之和，新题将问题反转为给定目标和求最小修改次数，目标从 value_computation 变为 minimization 并引入 edit 约束，核心求解必须设计外层搜索与验证逻辑，原 DP 仅为内部可复用子程序，无法直接迁移整体解法。叙事、样例、标题均无复用，表层换皮风险极低。虽然核心 DP 仍可复用，但问题建模与求解方向发生本质变化，语义差异明显。

## 硬检查
- [PASS] source_problem_resolved (blocker/invalid): 已成功加载原题文本。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.41，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=2。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 问题清单
- [minor] quality_issue: 缺少无解情况的样例 | 输出格式说明若无法达成则输出 -1，但样例没有展示此情况。初学者可能对 -1 的输出时机缺乏直观感受。
  修复建议: 增加一个样例，如 n=2, k=2, S=0, a=[1,2]，显示无论如何调整都无法使公平度之和为 0，输出 -1。

## 建议修改
- 增加一个样例，如 n=2, k=2, S=0, a=[1,2]，显示无论如何调整都无法使公平度之和为 0，输出 -1。
- 补充一个输出 -1 的样例，提升覆盖度。
- 在描述或注释中简要说明公平度之和可能很大，但只需关注模 998244353 后的值，进一步强化模运算意识。

## 回流摘要
- round_index: 1
- overall_status: pass
- generated_status: ok
- quality_score: 100.0
- divergence_score: 74.8
- strengths_to_keep: 题意转换自然，将抽象算法条件包装为贴近生活的校园场景。；样例解释清晰，逐步展示修改策略和最少性论证。；关键约束（模数、值域、排序无关性）在描述和注释中明确强调。；输入/输出格式简洁，便于选手解析。

## 快照
- original_problem: F
- difference_plan_rationale: 引入目标结果约束（C），将目标从计算改为最小修改（O），同时引入编辑操作与单调性等新不变量（V）。
