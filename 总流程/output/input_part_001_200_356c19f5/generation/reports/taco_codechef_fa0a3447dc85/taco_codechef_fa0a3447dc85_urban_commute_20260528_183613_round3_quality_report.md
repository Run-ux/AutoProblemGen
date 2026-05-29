# 题目质量与反换皮评估报告

## 总览
- status: pass
- quality_score: 97.0
- divergence_score: 76.5
- schema_distance: 0.4328
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中的输入结构（多测试用例、n、L、K、矩阵）、核心约束（中位数下限、总和中位数上限、计数单元定义）、目标函数（计数模 1e9+7）均准确且完整地落地在题面的 description、input_format、output_format、constraints 和 samples 中。主题映射也得到体现。
- spec_completeness: 5.0 / 5 | 题面提供了独立做题所需的所有关键信息：任务描述清晰、中位数定义、分配方案不同的判定、社团无区别、输入输出格式、约束（范围、时间、空间）、模数、注意事项（64位整数）均明确给出，无信息缺口。
- cross_section_consistency: 5.0 / 5 | description、input_format、output_format、constraints、samples 各部分高度一致：n 的定义、L 和 K 的含义、矩阵大小、输出格式、模数在样例中均得到印证，无矛盾。
- sample_quality: 4.0 / 5 | 样例数量为 2，覆盖了有解和无解情况，解释详细，有助于理解题意和关键定义。但数量偏少，缺少稍大一点的示例来验证更复杂的计数逻辑，可能影响选手对规则的理解。
- oj_readability: 5.0 / 5 | 题面结构符合 OJ 标准，包含标题、描述、输入格式、输出格式、样例、约束和注释。语言清晰，无来源污染，数学符号使用恰当，便于快速理解。

## 优点
- 题目背景映射自然，将抽象约束融入校园社团场景，可读性强。
- 分配方案不同的定义和社团无区别规则阐述清晰，避免了常见的计数混淆。
- 约束条件完整（时间、空间、数据范围、总和限制），便于选手估计算法复杂度。
- 注释明确指出模数、64位整数要求和输出0的情况，减少低级错误。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.8
- solution_transfer_risk: 0.2
- surface_retheme_risk: 0.1
- verdict: pass
- rationale: The new problem shifts from maximizing the minimum median to counting the number of valid partitions, altering the objective, input (adding L), and core algorithmic requirements. The original greedy feasibility check cannot be reused for enumeration, necessitating a new DP-based solution. Despite shared definitions (median, cost), the combinatorial counting problem is semantically distinct, and the surface narrative shows no significant overlap.

## 硬检查
- [PASS] source_problem_resolved (blocker/invalid): 已成功加载原题文本。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.43，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=2。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 问题清单
- [minor] quality_issue: 样例数量偏少 | 目前仅提供了两个样例（n=2 的有解和无解），对于计数问题的理解可能不够充分，建议增加一个 n≥3 的样例，以展示更多中位数计算和计数细节。
  修复建议: 增加一个样例，例如 n=3，能力值各不相同，以演示中位数定义和计数过程，并给出解释。

## 建议修改
- 增加一个样例，例如 n=3，能力值各不相同，以演示中位数定义和计数过程，并给出解释。
- 增加一个 n≥3 的样例，并附上解释，帮助验证中位数计算和计数规则。
- 在 description 中可补充一句对中位数定义的口语化说明，如“若 n=3 则取第 2 小，n=4 也取第 2 小”，当前已隐含但可更显式。
- 检查 constraints 中“所有测试用例的 n 之和不超过 1000”是否需要在 input_format 中提及（通常放在 constraints 即可）。

## 回流摘要
- round_index: 3
- overall_status: pass
- generated_status: ok
- quality_score: 97.0
- divergence_score: 76.5
- strengths_to_keep: 题目背景映射自然，将抽象约束融入校园社团场景，可读性强。；分配方案不同的定义和社团无区别规则阐述清晰，避免了常见的计数混淆。；约束条件完整（时间、空间、数据范围、总和限制），便于选手估计算法复杂度。；注释明确指出模数、64位整数要求和输出0的情况，减少低级错误。

## 快照
- original_problem: MEDMAX
- difference_plan_rationale: 通过将目标从最大化改为计数（O 变），新增好度下限 L 作为显式输入约束（C 变），并将核化解法从贪心可行性判定变为 DP 计数（V 变），彻底改变核心求解责任，使原题贪心算法无法直接复用。
