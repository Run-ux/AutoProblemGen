# 题目质量与反换皮评估报告

## 总览
- status: pass
- quality_score: 100.0
- divergence_score: 77.8
- schema_distance: 0.3979
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中的所有核心约束（adjacency_definition, adjacent_cell_same_group, one_item_per_cell, counting_unit_definition, deduplication_rule）均精确体现在 generated_problem 的 description、samples 和 notes 中；输入结构、目标函数（计数取模）也完全落定。无遗漏或偏差。
- spec_completeness: 5.0 / 5 | 题面完整包含任务说明（柜子格子布局、相邻规则、放置限制、去重规则）、输入输出格式、数据范围与限制、三个样例及详细解释、额外实现提示。所有做题所需信息齐备，无模糊之处。
- cross_section_consistency: 5.0 / 5 | description 中定义的相邻关系、区域容量与样例计算完全吻合，输入输出格式与样例数据一致，约束范围与样例 n=1 等情况无矛盾，notes 中关于模数和无解输出 0 的说明与 output_format 一致。整体无冲突。
- sample_quality: 5.0 / 5 | 三个样例覆盖了单物品种、多物品种、同种多数量等典型场景，且每个样例都附有详细解释，直接展示了去重规则的应用，能有效帮助理解题意。
- oj_readability: 5.0 / 5 | 题面使用清晰的故事引入、结构化描述，术语定义明确，无无关噪音或来源泄露，符合 OJ 题面规范，易于参赛者阅读和理解。

## 优点
- 去重规则表述极为清楚，通过块级表示和样例解释消除了任何计数歧义。
- 三个样例从易到难，逐步揭示方案的计数方式，教学效果好。
- 模数及数据类型提示直接，避免常见实现错误。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.85
- solution_transfer_risk: 0.1
- surface_retheme_risk: 0.1
- verdict: pass
- rationale: 新题将原题的存在性决策转变为计数问题（模998244353），并引入块级分配与去重规则，彻底改变了任务目标和求解关注点。原题使用的贪心归约算法无法直接迁移到计数场景，需要设计全新的动态规划或组合计数算法。尽管底层相邻约束和块结构相同，但问题语义已发生实质性变化。此外，新题背景从飞机士兵替换为柜子收纳，叙述语言、样例和标题均未复用原题文本，表层换皮痕迹极少。

## 硬检查
- [PASS] source_problem_resolved (blocker/invalid): 已成功加载原题文本。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.40，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=3。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 回流摘要
- round_index: 1
- overall_status: pass
- generated_status: ok
- quality_score: 100.0
- divergence_score: 77.8
- strengths_to_keep: 去重规则表述极为清楚，通过块级表示和样例解释消除了任何计数歧义。；三个样例从易到难，逐步揭示方案的计数方式，教学效果好。；模数及数据类型提示直接，避免常见实现错误。

## 快照
- original_problem: B
- difference_plan_rationale: 目标从判定变为计数；约束中新增计数对象定义和去重规则；不变量从保持判定归约性质转变为强调块分配的一一对应和汇总特性。
