# 题目质量与反换皮评估报告

## 总览
- status: reject_as_retheme
- quality_score: 97.0
- divergence_score: 59.5
- schema_distance: 0.5128
- generated_status: ok

## 质量维度
- variant_fidelity: 5.0 / 5 | 题面完全实现了 new_schema 中定义的任务变体：输入结构为两个社区的点集，目标要求输出分离圆或冲突证书，证书结构与不可分离条件、局部可验证性均得到准确描述。输入格式、输出格式、约束和样例均与 schema 一致。
- spec_completeness: 5.0 / 5 | 题面包含独立做题所需的所有关键信息：任务说明清晰定义了两种输出分支，输入格式、输出格式、约束条件和样例齐全，证书验证条件被完整描述，未遗漏任何必要细节。
- cross_section_consistency: 5.0 / 5 | description、input_format、output_format、constraints 和 samples 之间严格一致，点集大小、坐标范围、输出格式、证书条件均无矛盾，样例输入输出与题意完全匹配。
- sample_quality: 4.0 / 5 | 仅有两个样例，分别覆盖 YES 和 NO 分支，解释清晰；但样例较少，且 NO 样例仅展示了将全部点作为证书的平凡情况，未展示抽取真子集作为证书的更复杂情形，对理解证书构造的多样化帮助有限。
- oj_readability: 5.0 / 5 | 题面结构清楚、措辞明确，符合 OJ 题面表达习惯；尽管 hard_check 提示存在疑似原题标识泄露，但题面中未见明显污染或无关文本，不影响正常阅读与理解。

## 优点
- 成功将问题从判定型转化为构造/证据型，分支语义清晰且对等。
- 证书条件描述详细，局部可验证性在题面中明确强调，符合 new_schema 的创新意图。
- 样例解释充分，直接说明了不可分离的几何原因与分离圆的构造逻辑。

## 与原题差异分析
- changed_axes_planned: C, O, V
- changed_axes_realized: C, O, V
- semantic_difference: 0.45
- solution_transfer_risk: 0.7
- surface_retheme_risk: 0.45
- verdict: reject_as_retheme
- rationale: 核心几何问题完全相同：判断是否存在一个圆严格分离两个点集，求解依赖凸包计算与相交/包含检测。新题将判定输出扩展为构造分离圆（YES 时）或提交冲突证书（NO 时），这一变化虽增加了实现细节，但并未改变问题的本质建模与核心算法。原题的标准解（凸包判定）几乎可以直接复用，仅需在输出环节追加圆参数计算或子集提取，这些扩展是自然的构造补充，没有产生新的算法层面挑战。输入结构未变，表层叙事仅换了社区服务背景，样例思路也有明显延续。因此，原题解法迁移风险较高，语义实质性差异不足。

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
- [FAIL] source_leakage (blocker/retheme_issue): 检测到原题标识或标题片段泄露：e
- [PASS] title_overlap (major/retheme_issue): 标题重合度=0.00。
- [PASS] sample_count (major/quality_issue): 样例数量=2。
- [PASS] sample_line_alignment (major/quality_issue): 输入结构不是固定小数组，跳过样例行数检查。
- [PASS] input_count_alignment (blocker/quality_issue): 输入结构不是固定小数组，跳过输入项数量声明检查。
- [PASS] objective_alignment (blocker/quality_issue): 目标函数已经在题面中落地。
- [PASS] structural_option_alignment (blocker/quality_issue): 结构选项已在题面中落地。

## 问题清单
- [blocker] retheme_issue: source leakage | 检测到原题标识或标题片段泄露：e
  修复建议: 删除原题编号、题源、标题和明显句式复用。
- [minor] quality_issue: 疑似原题标识泄露 | hard_check source_leakage 检测到原题标识或标题片段泄露：“e”，但题面中未发现明显包含原题信息的字符串，可能为误报或微量字符匹配。
  修复建议: 检查题面文本，去除可能存在的原题题号、特殊标识等残留字符；若为误报，可忽略。
- [minor] quality_issue: 样例数量偏少且覆盖度不足 | 仅有 2 组样例，且 NO 样例的证书为全集本身，未展示更典型的真子集证书示例，可能影响用户对复杂证书构造的理解。
  修复建议: 建议增加一个包含真子集证书的 NO 样例（例如凸包相交仅需少数顶点），使样例更全面。
- [blocker] retheme_issue: solution transfer risk too high | 核心几何问题完全相同：判断是否存在一个圆严格分离两个点集，求解依赖凸包计算与相交/包含检测。新题将判定输出扩展为构造分离圆（YES 时）或提交冲突证书（NO 时），这一变化虽增加了实现细节，但并未改变问题的本质建模与核心算法。原题的标准解（凸包判定）几乎可以直接复用，仅需在输出环节追加圆参数计算或子集提取，这些扩展是自然的构造补充，没有产生新的算法层面挑战。输入结构未变，表层叙事仅换了社区服务背景，样例思路也有明显延续。因此，原题解法迁移风险较高，语义实质性差异不足。
  修复建议: 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。

## 建议修改
- 删除原题编号、题源、标题和明显句式复用。
- 检查题面文本，去除可能存在的原题题号、特殊标识等残留字符；若为误报，可忽略。
- 建议增加一个包含真子集证书的 NO 样例（例如凸包相交仅需少数顶点），使样例更全面。
- 增加输入、约束与目标的实质变化，降低原题解法的直接迁移性。
- 增加一个 NO 样例，展示取真子集作为冲突证书的情形（如凸包相交只需部分顶点）。
- 在 notes 中可补充说明：当输出 NO 时，即使将全部点作为证书也是允许的，但更小的证书可能存在，选手可自行选择。
- 优先改写核心任务定义，而不是继续替换故事背景。

## 回流摘要
- round_index: 1
- overall_status: reject_as_retheme
- generated_status: ok
- quality_score: 97.0
- divergence_score: 59.5
- strengths_to_keep: 成功将问题从判定型转化为构造/证据型，分支语义清晰且对等。；证书条件描述详细，局部可验证性在题面中明确强调，符合 new_schema 的创新意图。；样例解释充分，直接说明了不可分离的几何原因与分离圆的构造逻辑。

## 快照
- original_problem: E
- difference_plan_rationale: 核心约束 C 新增冲突证据的结构定义与可验证条件；目标 O 从布尔决策变为双向构造（圆 / 证书）；不变式 V 引入输出合同的两支正确性保证。
