# 题目质量与反换皮评估报告

## 总览
- status: reject_as_retheme
- quality_score: 100.0
- divergence_score: 58.3
- schema_distance: 0.3709
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中定义的输入结构（多测试用例、维度 n、成本上限 k、n×n 矩阵）准确落地到 input_format；核心约束（成本上限、字典序最小性）在 description 和 output_format 中得到完整体现；输出目标（最大好度及字典序最小排列）与 objective 定义一致。hard_checks 显示 objective_alignment 和 structural_option_alignment 均已通过。
- spec_completeness: 5.0 / 5 | 题面提供了完整的任务说明（重排评分、定义好度、成本、字典序要求），输入/输出格式具体，约束给出了所有参数范围（n、k、评分、t、总和限制、时空限制），并在 notes 中明确定义了中位数和字典序比较规则。选手无需猜测任何核心规则或边界条件。
- cross_section_consistency: 5.0 / 5 | description 中定义的好度、成本、字典序要求与 output_format 中的输出规范完全一致；input_format 的字段顺序与样例输入吻合；样例输出满足约束，且解释中验证了成本与字典序性质。无任何字段数量、目标定义或符号含义的冲突。
- sample_quality: 5.0 / 5 | 包含两个样例，分别覆盖存在可行方案和不存在可行方案的情况；样例1的解释详细说明了最大好度的确定过程、成本的验证，并举例说明字典序最小的性质，对理解题目要求很有帮助。
- oj_readability: 5.0 / 5 | 题面采用常见的城市通勤场景，术语定义清晰；结构按描述、输入格式、输出格式、约束、样例、说明的顺序组织，符合 OJ 规范；无来源泄露或无关文本，便于快速理解任务。

## 优点
- 约束落地准确：成本上限和字典序最小性在题面中均有明确、一致的表述。
- 定义完备：中位数和字典序比较在正文和 notes 中详细解释，消除了歧义。
- 样例有代表性：覆盖可行解和不可行解，解释帮助理解核心难点（好度的二分性质与字典序构造）。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.6
- solution_transfer_risk: 0.5
- surface_retheme_risk: 0.2
- verdict: pass
- rationale: 新题在约束层（新增字典序最小要求）和目标层（输出具体矩阵且需满足字典序最小）发生了实质改变，迫使求解者从原题的存在性验证转向构造特定最优排列，这需要重新设计构造算法和可行性判别逻辑，语义差异明显。原题的二分框架和排序预处理可部分复用，但可行性检查与构造部分无法直接迁移，需额外处理字典序极值性质，故解法迁移风险中等。文本、样例和叙事背景均未出现明显复用，表面换皮风险低。综上，认定为实质性变化，非简单换皮。

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

## 建议修改
- 可考虑增加一个包含多测试用例（t≥2）的样例，以明确展示多组输出之间不需要额外分隔的格式。
- 在样例1的解释中，可补充一个简要的字典序比较步骤（例如逐元素比较展示为什么给定排列最小），进一步强化选手对字典序约束的理解。

## 回流摘要
- round_index: 1
- overall_status: reject_as_retheme
- generated_status: ok
- quality_score: 100.0
- divergence_score: 58.3
- strengths_to_keep: 约束落地准确：成本上限和字典序最小性在题面中均有明确、一致的表述。；定义完备：中位数和字典序比较在正文和 notes 中详细解释，消除了歧义。；样例有代表性：覆盖可行解和不可行解，解释帮助理解核心难点（好度的二分性质与字典序构造）。

## 快照
- original_problem: MEDMAX
- difference_plan_rationale: 核心约束新增规范顺序要求，目标从仅仅最大化goodness改为输出最优goodness及规范排列，不变量引入规范构造正确性证明，这三轴变化推动算法从纯可行性检查变为带顺序优化的构造。
