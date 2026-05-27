# 题目质量与反换皮评估报告

## 总览
- status: reject_as_retheme
- quality_score: 100.0
- divergence_score: 58.9
- schema_distance: 0.4917
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中的所有关键元素，包括输入结构（n 和偶数坐标点）、目标 T、约束（坐标偶数、互异、无三点共线）、编辑操作和最小编辑次数要求，均在题面中得到准确体现。
- spec_completeness: 5.0 / 5 | 题面包含了独立做题所需的所有信息：任务说明（通勤区域、有趣条件、编辑操作、目标）、输入输出格式、数据范围约束、三个样例及解释，且额外提供了指导性注释。无缺失信息。
- cross_section_consistency: 5.0 / 5 | 各部分之间一致：描述与输入输出格式无冲突，样例与约束匹配，坐标偶数等约束在样例中得到体现，注释中的公式与前述模4类别说明连贯。
- sample_quality: 5.0 / 5 | 三个样例覆盖了 0 步、不可能、1 步三种情况，解释清晰且与题面规则相符，有助于理解题意和解题思路。
- oj_readability: 5.0 / 5 | 题面结构清晰，分节描述，语言准确无歧义，无来源污染，便于参赛者快速理解。

## 优点
- 题面准确落地了反向设计框架，将目标绑定与最小编辑操作无缝融入叙述。
- 样例覆盖多种情况，解释有助于快速理解规则。
- 清晰的输入输出格式和约束说明，便于选手开始编码。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.4
- solution_transfer_risk: 0.6
- surface_retheme_risk: 0.8
- verdict: reject_as_retheme
- rationale: 新题将原题的正向计数反转为带目标约束的最小编辑问题，但核心定义（偶数坐标、无三点共线、内部整点数奇数且面积为整数）和关键不变式（模4类别计数公式）完全保留。语义差异主要体现在目标函数从‘计数’变为‘最小化编辑次数’，但求解框架强依赖原题的模4分类与计数公式。熟悉原题的选手可以立即将编辑操作映射为类别转移，只需在原有计数子程序上增加最小距离计算，解法迁移风险中等。表层换皮风险很高：原题‘栅栏-奶牛’被直接替换为‘站点-乘客’，且描述结构高度对应，仅做实体映射。因此判定为换皮，拒绝通过。

## 硬检查
- [PASS] source_problem_resolved (blocker/invalid): 已成功加载原题文本。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.49，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=3。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 问题清单
- [minor] quality_issue: 注释可能过度提示核心性质 | 生成题面在 notes 中直接给出了模4类别决定有趣性的结论和公式，这可能大幅降低题目难度，削弱了选手自主发现关键性质的考察。但作为审稿人，这属于题目呈现策略选择，不属于错误。
  修复建议: 如果希望保持 hard 难度，可以考虑隐去公式，只给出模4类别的启发，或者完全去掉 notes，让选手自行推导。
- [blocker] retheme_issue: solution transfer risk too high | 新题将原题的正向计数反转为带目标约束的最小编辑问题，但核心定义（偶数坐标、无三点共线、内部整点数奇数且面积为整数）和关键不变式（模4类别计数公式）完全保留。语义差异主要体现在目标函数从‘计数’变为‘最小化编辑次数’，但求解框架强依赖原题的模4分类与计数公式。熟悉原题的选手可以立即将编辑操作映射为类别转移，只需在原有计数子程序上增加最小距离计算，解法迁移风险中等。表层换皮风险很高：原题‘栅栏-奶牛’被直接替换为‘站点-乘客’，且描述结构高度对应，仅做实体映射。因此判定为换皮，拒绝通过。
  修复建议: 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。

## 建议修改
- 如果希望保持 hard 难度，可以考虑隐去公式，只给出模4类别的启发，或者完全去掉 notes，让选手自行推导。
- 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。
- 可考虑在输入格式中明确编辑后的新坐标是否仍需落在 [0,10^7] 范围内（尽管当前不限制亦可）。
- 优先改写核心任务定义，而不是继续替换故事背景。

## 回流摘要
- round_index: 1
- overall_status: reject_as_retheme
- generated_status: ok
- quality_score: 100.0
- divergence_score: 58.9
- strengths_to_keep: 题面准确落地了反向设计框架，将目标绑定与最小编辑操作无缝融入叙述。；样例覆盖多种情况，解释有助于快速理解规则。；清晰的输入输出格式和约束说明，便于选手开始编码。

## 快照
- original_problem: D1
- difference_plan_rationale: C：增加目标有趣三角形个数T约束和修改操作定义；O：从输出计数改为输出最小修改次数；V：不变量从单纯的模4分类计数扩展到基于类别分布变化与三角形数量函数的关系，以及对修改操作合法性的保证。
