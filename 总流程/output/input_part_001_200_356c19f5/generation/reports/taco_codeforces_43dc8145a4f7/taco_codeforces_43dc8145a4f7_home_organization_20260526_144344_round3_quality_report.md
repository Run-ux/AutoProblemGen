# 题目质量与反换皮评估报告

## 总览
- status: pass
- quality_score: 100.0
- divergence_score: 74.4
- schema_distance: 0.4055
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | The new_schema's objective (counting modulo 1e9+7), core constraints (placement rule, counting object definition, row decomposability), input structure, and theme are all accurately realised in the generated problem's description, input_format, output_format, constraints, and samples. No deviation or omission is present.
- spec_completeness: 5.0 / 5 | The problem statement provides a complete and unambiguous description of the task, input/output formats, constraints (n, m, a_i bounds, total items ≤ 8n, time/space limits), and necessary definitions. A solver can implement a solution without guessing any rule or boundary condition.
- cross_section_consistency: 5.0 / 5 | All sections are mutually consistent: the description's rules match the input format, constraints, and sample explanations. The sample inputs/outputs align with the described computation, and no field or definition contradicts another.
- sample_quality: 5.0 / 5 | Four samples are provided, covering single-cabinet multiple items, single item, multiple cabinets, and a simple edge case. Explanations are clear, demonstrate the counting logic, and help understanding without being misleading.
- oj_readability: 5.0 / 5 | The problem statement follows standard OJ conventions with a clear title, narrative description, well-structured input/output format sections, constraints block, samples with explanations, and notes. The language is precise and free of source contamination or confusing jargon.

## 优点
- Accurately translates the complex counting objective and constraints into a clear natural-language problem.
- Provides a thorough mathematical decomposition that clarifies the independence of cabinets and the notion of configuration vectors.
- Samples are well-chosen, covering different scenarios, and include detailed explanations that validate the rules.
- Consistent across all sections, with no contradictions or missing information.

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.8
- solution_transfer_risk: 0.2
- surface_retheme_risk: 0.2
- verdict: pass
- rationale: 新题将原题的存在性判定改为方案计数，并显式定义了计数对象（按格子上的物品类型区分方案）和去重规则，任务语义发生实质变化。原题基于组大小度量的贪心判定算法无法迁移，新题需构造组合计数或高维 DP，解法核心完全重构。底层组合结构（行内邻接组件规则、行间独立）虽可复用作为建模基础，但整体求解义务截然不同，原解迁移风险很低。表层面，背景故事、标题、样例及输出格式均独立撰写，无文本复用迹象。因此，语义差异真实成立，解法迁移风险低，非表层换皮，予以通过。

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
- [PASS] sample_count (major/quality_issue): 样例数量=4。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 回流摘要
- round_index: 3
- overall_status: pass
- generated_status: ok
- quality_score: 100.0
- divergence_score: 74.4
- strengths_to_keep: Accurately translates the complex counting objective and constraints into a clear natural-language problem.；Provides a thorough mathematical decomposition that clarifies the independence of cabinets and the notion of configuration vectors.；Samples are well-chosen, covering different scenarios, and include detailed explanations that validate the rules.；Consistent across all sections, with no contradictions or missing information.

## 快照
- original_problem: B
- difference_plan_rationale: 目标轴 O 从 feasibility 变为 counting；核心约束 C 从仅描述邻接规则变为同时定义计数对象、等价关系与按行分解的计数单元；不变量 V 从基于贪婪度量的可行性条件转变为支持行独立分解的 DP 状态汇总逻辑。
