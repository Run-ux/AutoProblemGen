# 题目质量与反换皮评估报告

## 总览
- status: reject_as_retheme
- quality_score: 100.0
- divergence_score: 57.8
- schema_distance: 0.5075
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中定义的任务变体、输入结构、目标函数、核心约束等均准确落地到 generated_problem 的 description、input_format、output_format 和 constraints 中，包括中位数定义、好度与成本定义、支配关系以及输出帕累托前沿并升序排列等要求。
- spec_completeness: 5.0 / 5 | 题面提供了独立做题所需的全部关键信息：任务背景与目标、中位数/好度/成本/支配的定义、输入输出格式、约束条件、样例及解释、数据类型提醒等，选手无需猜测任何规则或边界条件。
- cross_section_consistency: 5.0 / 5 | description、input_format、output_format、constraints、samples 之间无任何矛盾。定义一致，样例输入输出严格符合格式要求，解释与数学描述匹配，输出规则（连续无空行）在样例中正确体现。
- sample_quality: 5.0 / 5 | 两个样例分别覆盖了 n=2 和 n=3 的情况，且第二个样例包含多个测试用例，展示了连续输出的要求。样例解释详细，逐步说明了非支配点的推导，有助于理解支配关系和前沿输出。
- oj_readability: 5.0 / 5 | 题面标题、描述、输入输出格式、约束、样例、注释的结构标准清晰，措辞准确无歧义，无原题泄露或无关文本，易于快速理解。

## 优点
- 题面定义清晰，完整包含了中位数、好度、成本、支配关系以及非支配前沿的所有必要定义。
- 样例解释详细，逐步说明了非支配点的选择过程，有助于理解题目。
- 输入输出格式描述准确，特别注意了多测试用例输出无空行的细节。
- 约束和数据类型提醒（使用64位整数）对选手友好。
- 题面结构与标准OJ题面完全一致，无噪声或干扰信息。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.45
- solution_transfer_risk: 0.75
- surface_retheme_risk: 0.15
- verdict: reject_as_retheme
- rationale: 虽然目标函数从单值最大化变为输出帕累托前沿（axis O 的变化），且约束结构中移除了成本上限 k（axis C 的变化），但核心建模完全一致：给定全局排序的元素，通过贪心分配每行左侧元素和选择中位数，使得最小中位数不低于阈值的同时总成本最小。原题的判定子程序（计算给定 goodnes 的最小成本）可以直接复用于新题计算 f(G)，外层逻辑从二分搜索变为扫描候选值并筛选非支配点，调整量很小。熟悉原题的选手几乎可以原样迁移贪心算法和单调性分析，新题没有实质性的算法创新，仅增加了效率优化的要求。叙事和样例完全重写，表面换皮风险低，但语义差异不足以支撑新题的独立性，解法迁移风险仍高。

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
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=2。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 问题清单
- [blocker] retheme_issue: solution transfer risk too high | 虽然目标函数从单值最大化变为输出帕累托前沿（axis O 的变化），且约束结构中移除了成本上限 k（axis C 的变化），但核心建模完全一致：给定全局排序的元素，通过贪心分配每行左侧元素和选择中位数，使得最小中位数不低于阈值的同时总成本最小。原题的判定子程序（计算给定 goodnes 的最小成本）可以直接复用于新题计算 f(G)，外层逻辑从二分搜索变为扫描候选值并筛选非支配点，调整量很小。熟悉原题的选手几乎可以原样迁移贪心算法和单调性分析，新题没有实质性的算法创新，仅增加了效率优化的要求。叙事和样例完全重写，表面换皮风险低，但语义差异不足以支撑新题的独立性，解法迁移风险仍高。
  修复建议: 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。

## 建议修改
- 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。
- 可考虑增加一个 n=1 的测试样例，以验证边界情况（如只有一行一列时的行为），进一步丰富样例覆盖度。
- 优先改写核心任务定义，而不是继续替换故事背景。

## 回流摘要
- round_index: 2
- overall_status: reject_as_retheme
- generated_status: ok
- quality_score: 100.0
- divergence_score: 57.8
- strengths_to_keep: 题面定义清晰，完整包含了中位数、好度、成本、支配关系以及非支配前沿的所有必要定义。；样例解释详细，逐步说明了非支配点的选择过程，有助于理解题目。；输入输出格式描述准确，特别注意了多测试用例输出无空行的细节。；约束和数据类型提醒（使用64位整数）对选手友好。；题面结构与标准OJ题面完全一致，无噪声或干扰信息。

## 快照
- original_problem: MEDMAX
- difference_plan_rationale: 引入第二指标成本，定义支配关系，将目标改为输出前沿点集，不变量相应调整为函数单调性与前沿性质。
