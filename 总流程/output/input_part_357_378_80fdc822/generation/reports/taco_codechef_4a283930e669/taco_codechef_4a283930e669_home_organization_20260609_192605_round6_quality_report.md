# 题目质量与反换皮评估报告

## 总览
- status: pass
- quality_score: 100.0
- divergence_score: 70.4
- schema_distance: 0.3856
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | new_schema 中定义的任务变体（最小化编辑代价达到 beauty ≥ K）、输入结构（多测试用例、每行字符串与代价数组）、目标函数（最小化 total_edit_cost 或输出 -1）、核心约束（元素使用限制、配对结构、允许未使用元素、字母限制、编辑操作定义、beauty 定义、代价范围等）均在 generated_problem 的 description、input_format、output_format、constraints 和 samples 中准确落地，无遗漏或偏离。
- spec_completeness: 5.0 / 5 | 题面提供了独立做题所需的全部关键信息：任务说明清晰，输入输出格式完整，约束覆盖了核心取值范围（T, N, K, 总长度，代价上下界，字母限制等），并给出了编辑操作、配对规则、目标函数的详细定义，无缺失或歧义。细微的不明确（如同一位置是否可多次编辑）不影响整体理解，符合 OJ 常见表述。
- cross_section_consistency: 5.0 / 5 | description、input_format、output_format、constraints 和 samples 之间完全一致。输入格式与样例严格对应，配对与 beauty 定义在描述和样例解释中吻合，约束中的范围与题目要求及样例数据没有矛盾。
- sample_quality: 5.0 / 5 | 共 3 个样例，覆盖了无法达到 K（输出 -1）、无需编辑（代价 0）、简单编辑（代价 1）等典型场景，解释详细且正确，能帮助选手理解匹配度计算与编辑决策，样例数量基本充足。
- oj_readability: 5.0 / 5 | 题面采用清晰的 OJ 风格，分段合理（标题、描述、输入/输出格式、约束、样例、注释），语言流畅，将字符串映射为公交线路的主题自然融入叙事，无原题泄露或无关噪声，便于选手快速理解。

## 优点
- new_schema 的所有核心约束与目标均被准确翻译为题面要求，反转设计落地充分。
- 输入/输出格式、约束、样例之间高度一致，无格式错误或逻辑漏洞。
- 样例覆盖典型情况并附有清晰解释，有助于选手理解。
- 主题替换自然，无原题痕迹，符合 OJ 表达规范。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.8
- solution_transfer_risk: 0.3
- surface_retheme_risk: 0.2
- verdict: pass
- rationale: 新题将目标从最大化 beauty 反转为最小化编辑代价以满足 beauty 阈值，并引入带位置代价的编辑操作，核心约束（C 轴 distance 0.60）和优化目标（O 轴 distance 0.43）发生实质变化。不变量（V 轴 distance 0.49）也完全重写，原题的分治递归解法无法直接迁移，必须设计全新的代价感知算法。表层主题完全不同，无标题或文本复用，surface_retheme_risk 低。因此判定为非换皮题。

## 硬检查
- [PASS] source_problem_resolved (blocker/invalid): 已成功加载原题文本。
- [PASS] generated_problem_present (blocker/invalid): artifact 已包含 generated_problem。
- [PASS] new_schema_present (blocker/invalid): artifact 已包含 new_schema 或兼容字段 new_schema_snapshot。
- [PASS] difference_plan_present (blocker/invalid): artifact 已持久化 difference_plan。
- [PASS] generated_status_ok (blocker/invalid): 生成状态正常。
- [PASS] predicted_schema_distance_present (blocker/invalid): artifact 已包含 predicted_schema_distance。
- [PASS] distance_breakdown_present (blocker/invalid): artifact 已包含 distance_breakdown。
- [PASS] changed_axes_realized_present (blocker/invalid): artifact 已包含 changed_axes_realized。
- [PASS] schema_distance_threshold (blocker/retheme_issue): schema_distance=0.39，达到中等差异阈值。
- [PASS] changed_axes_threshold (blocker/retheme_issue): 已落地核心差异轴：C, O, V。
- [PASS] source_leakage (blocker/retheme_issue): 未发现原题标题或题源泄露。
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=3。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 回流摘要
- round_index: 6
- overall_status: pass
- generated_status: ok
- quality_score: 100.0
- divergence_score: 70.4
- strengths_to_keep: new_schema 的所有核心约束与目标均被准确翻译为题面要求，反转设计落地充分。；输入/输出格式、约束、样例之间高度一致，无格式错误或逻辑漏洞。；样例覆盖典型情况并附有清晰解释，有助于选手理解。；主题替换自然，无原题痕迹，符合 OJ 表达规范。

## 快照
- original_problem: ENGLISH
- difference_plan_rationale: 核心约束新增带代价的编辑操作与目标 beauty 阈值；目标从最大化翻转为最小化代价；不变量从单纯 LCP 分治转为代价感知的 beauty 提升界限与最小性证明。输入结构增加编辑代价和阈值参数，但整体结构仍为多测试用例与字符串序列，因此 I 轴未发生根本改变。
