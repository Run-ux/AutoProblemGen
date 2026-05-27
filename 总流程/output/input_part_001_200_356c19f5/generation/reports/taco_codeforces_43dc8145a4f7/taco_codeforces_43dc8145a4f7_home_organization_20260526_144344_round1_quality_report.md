# 题目质量与反换皮评估报告

## 总览
- status: pass
- quality_score: 97.0
- divergence_score: 82.7
- schema_distance: 0.4055
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中定义的输入结构（parameters 为 n,m，item_counts 为 m 个整数）、核心约束（placement_rule 要求组件内同种，counting_object_definition 按格子类型区分方案，row_decomposability 行独立可分解）、目标（计数模 10^9+7）均准确落地到 generated_problem 的 description、input_format、output_format 和 constraints 中，样例也与规则一致，无缺失或偏离。
- spec_completeness: 5.0 / 5 | 题面提供了完成任务所需的完整信息：任务说明清晰（计数所有合法放置，模 10^9+7），输入输出格式明确，约束完整（包含 n,m,a_i 范围及总和限制，时间/空间限制），关键规则（组件内同种、同类物品不可区分、方案区分方式）在描述和 notes 中反复说明，无重要信息遗漏。
- cross_section_consistency: 5.0 / 5 | description 中描述的柜子结构、物品数量、规则与 input_format、output_format、constraints 完全一致；两个样例的输入输出格式符合声明，解释中的推导与题意吻合，且未与任何部分产生矛盾。
- sample_quality: 4.0 / 5 | 样例数量为 2，覆盖了多物品恰好填满和单物品未满的典型场景，解释详细，有助于理解规则和计数思路。但题目难度为 hard，仅有两个样例略显不足，可能难以覆盖边界或复杂组合情况，增加一个样例会更利于调试。
- oj_readability: 5.0 / 5 | 题面采用标准 OJ 格式，标题、描述、输入输出格式、约束、样例、注释划分清晰；描述语言符合中文习惯且无来源污染，虽引入分配向量等数学概念，但作为 hard 题的解释可接受，措辞明确，易于快速理解。

## 优点
- 规则描述准确：组件划分与同种约束无歧义，计数对象定义清晰（同类物品不可区分，按格子类型区分方案）。
- 数学结构交代清楚：明确引入行独立性和分配向量分解，为高维 DP 提供直接切入点。
- 样例解释详尽：两个样例的解析详细展示了 g(d) 的计算逻辑，有助于理解核心子问题。
- 格式规范：输入输出格式、约束、注释均符合 OJ 标准，易于机器判题和选手阅读。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.95
- solution_transfer_risk: 0.05
- surface_retheme_risk: 0.2
- verdict: pass
- rationale: 任务语义发生根本改变：从存在性判定（feasibility）变为计数（counting），要求输出方案总数模 10^9+7。原题核心约束（邻接组件内同组）虽保留，但新增了计数对象定义、行分解约束和 DP 状态不变量，导致求解目标彻底重构。原题贪心度量算法无法迁移，必须设计全新的高维 DP 或组合计数方法。叙事背景和文本表述完全不同，未发现表层复用痕迹。因此不是换皮。

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
- [minor] quality_issue: 样例数量偏少 | 当前仅有 2 个样例，且均基于 n=1 的简单情况。对于 hard 难度的计数题，选手可能需要更多样例来验证复杂组合或空位情况的正确性。
  修复建议: 增加一个 n>1 且物品未完全占满所有格子的样例，展示多柜子分解的计数过程。

## 建议修改
- 增加一个 n>1 且物品未完全占满所有格子的样例，展示多柜子分解的计数过程。
- 增加第三个样例：例如 n=2、m=2，物品数量分别为 3 和 5，总格子 16 个，部分空格，展示多柜子组合计数。
- 在样例解释中可补充一句“所有样例中的 g(d) 可通过简单枚举得到，实际算法需要高效处理任意 d”，降低选手对 g(d) 简单性的误解。

## 回流摘要
- round_index: 1
- overall_status: pass
- generated_status: ok
- quality_score: 97.0
- divergence_score: 82.7
- strengths_to_keep: 规则描述准确：组件划分与同种约束无歧义，计数对象定义清晰（同类物品不可区分，按格子类型区分方案）。；数学结构交代清楚：明确引入行独立性和分配向量分解，为高维 DP 提供直接切入点。；样例解释详尽：两个样例的解析详细展示了 g(d) 的计算逻辑，有助于理解核心子问题。；格式规范：输入输出格式、约束、注释均符合 OJ 标准，易于机器判题和选手阅读。

## 快照
- original_problem: B
- difference_plan_rationale: 目标轴 O 从 feasibility 变为 counting；核心约束 C 从仅描述邻接规则变为同时定义计数对象、等价关系与按行分解的计数单元；不变量 V 从基于贪婪度量的可行性条件转变为支持行独立分解的 DP 状态汇总逻辑。
