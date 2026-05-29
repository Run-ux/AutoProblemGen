# 题目质量与反换皮评估报告

## 总览
- status: pass
- quality_score: 100.0
- divergence_score: 76.2
- schema_distance: 0.4328
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | Generated problem accurately implements all new_schema components: dimension n, cost_limit K, goodness_lower_bound L are all present in input format; constraints match value ranges; multiple test cases with sum n≤1000; counting unit definition (clubs indistinguishable, individuals distinct) and objective (count modulo 1e9+7) are correctly reflected; median definition and constraints (median≥L, sum≤K) are clearly stated.
- spec_completeness: 5.0 / 5 | All essential information for independent solving is provided: task description, input/output format, constraints (t, n, sum n, L, K, abilities, time/memory limits), median definition, club indistinguishability, individual distinctness, modulo, and edge cases (use 64-bit ints). No missing details that would require guessing.
- cross_section_consistency: 5.0 / 5 | Description, input format, output format, constraints, and samples are fully consistent. n, L, K appear in input format as specified; sample inputs match the constraints; output format expects a single integer per test case, as shown in samples; notes about indistinguishability and distinctness are respected in sample explanations.
- sample_quality: 5.0 / 5 | Three well-chosen samples are provided: a basic case with a valid solution, an L threshold that yields zero, and a larger n=3 case with a detailed combinatorial breakdown. Explanations clearly illustrate the counting logic, indistinguishability, and edge cases, aiding understanding of the problem.
- oj_readability: 5.0 / 5 | The problem is presented in clear Chinese with a typical OJ structure: title, description, input/output format, constraints, samples, and notes. The exposition is direct and free from irrelevant asides or source contamination. The median definition is illustrated with examples, and important caveats (club order, individual identity) are explicitly stated.

## 优点
- Precise definition of counting unit (sets, indistinguishability) avoids ambiguity.
- Detailed sample explanations reinforce the combinatorial counting concept.
- Constraints and notes (64-bit types, sum n limit) set clear expectations for implementation.

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.75
- solution_transfer_risk: 0.15
- surface_retheme_risk: 0.1
- verdict: pass
- rationale: The new problem changes the core semantic from a max-min optimization to a counting problem under given bounds (L and K), with rows now treated as indistinguishable, as specified in the counting constraint. This fundamentally alters the solution from binary search with greedy feasibility check to a DP-based enumeration. The original greedy algorithm cannot be reused directly for counting. The surface theme (club assignment) is completely different from the original matrix rearrangement, with no textual reuse. Hence, semantic difference is high, solution transfer risk is low, and surface retheme risk is minimal.

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
- [PASS] sample_count (major/quality_issue): 样例数量=3。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 回流摘要
- round_index: 4
- overall_status: pass
- generated_status: ok
- quality_score: 100.0
- divergence_score: 76.2
- strengths_to_keep: Precise definition of counting unit (sets, indistinguishability) avoids ambiguity.；Detailed sample explanations reinforce the combinatorial counting concept.；Constraints and notes (64-bit types, sum n limit) set clear expectations for implementation.

## 快照
- original_problem: MEDMAX
- difference_plan_rationale: 通过将目标从最大化改为计数（O 变），新增好度下限 L 作为显式输入约束（C 变），并将核化解法从贪心可行性判定变为 DP 计数（V 变），彻底改变核心求解责任，使原题贪心算法无法直接复用。
