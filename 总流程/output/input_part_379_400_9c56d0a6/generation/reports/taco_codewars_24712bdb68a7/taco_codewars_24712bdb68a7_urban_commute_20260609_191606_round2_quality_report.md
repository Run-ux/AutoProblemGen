# 题目质量与反换皮评估报告

## 总览
- status: revise_quality
- quality_score: 59.0
- divergence_score: 72.4
- schema_distance: 0.3783
- generated_status: ok

## 质量维度
- variant_fidelity: 4.0 / 5 | new_schema 的核心输入字段（formula, target_digit）、编辑操作合同、修改后约束、目标函数与存在性处理均在题面中落地。但编辑证书以输出完整等式替代详细位置列表，与规范略有偏差；且未提及表达式可包含多个运算符，可能影响实现复杂度。
- spec_completeness: 3.0 / 5 | 题面提供了任务说明、输入输出格式、主要约束和样例，但缺少负号与减号区分规则、多运算符表达式可能性说明，对解题必备的表达式解析规则界定不清，选手需自行猜测负号边界，可能影响独立做题。
- cross_section_consistency: 2.0 / 5 | 样例4输入 '-1+?=?' 输出 '0+1=1' 长度不匹配，违反‘不能增删字符’约束；且负号删除未解释，与约束矛盾，严重不一致。其他部分大体一致，但这一错误直接影响理解。
- sample_quality: 2.0 / 5 | 样例数量尚可，覆盖常见情况，但样例4存在输出长度不一致的错误，会严重误导选手对操作规则的理解，且未覆盖多运算符情形，整体质量下降。
- oj_readability: 3.0 / 5 | 题面结构清晰、语言流畅，符合OJ习惯。但样例4的明显错误破坏了规则的可信度，且负号规则不明确会增加阅读障碍，需修正后提升可读性。

## 优点
- 问题翻转设计新颖，从正向求解转为反向输入设计，富有挑战性。
- 背景故事（公交班次修正）贴合日常生活，易于理解。
- 约束描述详细，涵盖了数值范围、前导零、数字互斥等关键点。
- 样例覆盖了无解、零次修改和多次修改的基本场景。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.8
- solution_transfer_risk: 0.2
- surface_retheme_risk: 0.1
- verdict: pass
- rationale: 原题要求找出使等式成立的最小未知数字（正向求解），新题则给定目标数字，要求计算最小编辑次数以修改表达式使其成立（逆向设计）。核心任务从“枚举答案”翻转为“搜索编辑空间”，约束中新增编辑操作合同、目标数字绑定及最小性证书，必迫使解题者重新建模（如 BFS/DP），原题仅枚举 10 个数字的解法几乎无法直接迁移。背景故事由考古完全换成公交调度，标题与描述无复用痕迹，表层换皮风险极低。尽管输入格式相似且表达式求值等子程序可部分复用，但整体语义差异显著，解法迁移风险很低，故可通过。

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
- [PASS] sample_count (major/quality_issue): 样例数量=4。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 问题清单
- [major] quality_issue: 样例4输出长度与输入不一致 | 样例4输入为 '-1+?=?' 长度6，输出为 '0+1=1' 长度5，违反了约束“不能增删字符”。同时负号被无故删除，与编辑操作合同矛盾。
  修复建议: 修改样例4输出为 '-0+1=1'，或调整输入/解释，确保长度不变且负号处理合理。
- [major] quality_issue: 负号与减号区分规则缺失 | 题面未明确如何区分前缀负号与运算符减号，选手无法确定哪些 '-' 是不可修改的负号，影响解析与操作实现。
  修复建议: 在输入格式或约束中增加说明，例如‘负号紧邻数字前且后无空格，且不作为独立运算符’，或直接规定负号只允许出现在数字的最前端。
- [minor] quality_issue: 表达式运算符数量未明确说明 | 描述仅以‘A+B=C’举例，可能让选手误认为只有两个操作数，而实际约束只限制了总长度，允许多运算符。
  修复建议: 在约束或描述中补充‘表达式中可包含多个运算符（加、减、乘）’，并给出一个简单多运算符样例。

## 建议修改
- 修改样例4输出为 '-0+1=1'，或调整输入/解释，确保长度不变且负号处理合理。
- 在输入格式或约束中增加说明，例如‘负号紧邻数字前且后无空格，且不作为独立运算符’，或直接规定负号只允许出现在数字的最前端。
- 在约束或描述中补充‘表达式中可包含多个运算符（加、减、乘）’，并给出一个简单多运算符样例。
- 修正样例4的输出字符串为 '-0+1=1' 或等效形式，并重新梳理解释文本。
- 在输入格式部分明确负号的判定规则，或将负号与数字视为整体Token，消除歧义。
- 在约束或描述中指明表达式可包含任意数量的运算符，不受限于两个操作数。
- 考虑增加一个至少包含两个运算符的样例，以展示更复杂的表达式结构。

## 回流摘要
- round_index: 2
- overall_status: revise_quality
- generated_status: ok
- quality_score: 59.0
- divergence_score: 72.4
- strengths_to_keep: 问题翻转设计新颖，从正向求解转为反向输入设计，富有挑战性。；背景故事（公交班次修正）贴合日常生活，易于理解。；约束描述详细，涵盖了数值范围、前导零、数字互斥等关键点。；样例覆盖了无解、零次修改和多次修改的基本场景。

## 快照
- original_problem: 546d15cebed2e10334000ed9
- difference_plan_rationale: 核心约束从“找出满足所有条件的未知数字”变为“通过修改已知数字使给定 d 成为解并证明最小性”，引入了编辑操作空间和一套操作合法性条件；目标从最小化 d 变为最小化修改次数，并要求输出具体修改方案作为证书；不变量从升序枚举 d 变为按编辑距离递增的广度优先状态探索。
