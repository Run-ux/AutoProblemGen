# 题目质量与反换皮评估报告

## 总览
- status: pass
- quality_score: 100.0
- divergence_score: 86.7
- schema_distance: 0.4819
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中定义的所有结构、约束、目标均准确落地到 generated_problem 的 description、input_format、output_format、constraints、samples。输入输出格式匹配，约束（区间有效性、可见性规则、目标覆盖约束、修改操作）均在题面中明确表述。
- spec_completeness: 5.0 / 5 | 题面提供了任务说明、输入格式、输出格式、约束条件、必要说明和注释，无需读者自行猜测规则或边界条件。所有核心信息齐全。
- cross_section_consistency: 5.0 / 5 | description、input_format、output_format、constraints、samples 之间字段数量、目标定义、样例格式、符号含义均一致，无冲突。
- sample_quality: 5.0 / 5 | 共有 5 个样例，覆盖了不需要修改、修改一个、修改两个、无解等典型情况，每个样例均有解释，有助于理解。
- oj_readability: 5.0 / 5 | 题面结构清晰，有标题、描述、输入输出格式、约束、样例和注释，措辞明确，无来源污染或无关文本，便于快速理解。

## 优点
- 题面完全忠实地实现了 new_schema 中的结构和约束，无遗漏或偏差。
- 描述清晰，使用收纳主题（小明整理柜子）使问题直观易理解。
- 提供了丰富的样例，包括无解情况，解释到位。
- 输入输出格式明确，约束完整，可直接用于在线评测。
- 修改操作的描述明确（每个物品至多修改一次，新区间合法），避免歧义。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.92
- solution_transfer_risk: 0.08
- surface_retheme_risk: 0.05
- verdict: pass
- rationale: 新题将正向区间覆盖计数彻底翻转为带目标约束的最小修改设计问题：输入增加每个查询的目标可见物品数（C 轴变化 0.73），目标从统计数量变为最小化修改次数（O 轴变化 0.54），核心求解逻辑从线性扫描 + BIT 转为组合优化与可行性下界证明（V 轴变化 0.60）。原题的事件排序 + BIT 方案只能被动计算覆盖，无法主动决定物品保留或修改，更无法解决最小性证明，因此解法几乎无法迁移。表层主题从外星人下载视频变为家庭物品整理，叙事、标题、样例均无重合。综上，该题具有实质语义差异和低解法迁移风险，不属于换皮。

## 硬检查
- [PASS] source_problem_resolved (blocker/invalid): 已成功加载原题文本。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.48，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=5。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 建议修改
- 可考虑在约束部分显式声明无多测试用例，强调仅单个测试案例。
- 样例解释可以更加突出显示物品修改前后的区间变化，但当前解释已足够。

## 回流摘要
- round_index: 2
- overall_status: pass
- generated_status: ok
- quality_score: 100.0
- divergence_score: 86.7
- strengths_to_keep: 题面完全忠实地实现了 new_schema 中的结构和约束，无遗漏或偏差。；描述清晰，使用收纳主题（小明整理柜子）使问题直观易理解。；提供了丰富的样例，包括无解情况，解释到位。；输入输出格式明确，约束完整，可直接用于在线评测。；修改操作的描述明确（每个物品至多修改一次，新区间合法），避免歧义。

## 快照
- original_problem: DOWNLOAD
- difference_plan_rationale: C轴：引入目标覆盖数约束和修改操作定义；O轴：从计数变为最小化修改次数；V轴：从BIT维护覆盖统计变为基于需求差分的可行性下界证明。
