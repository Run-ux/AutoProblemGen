from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class LabelSpec:
    name: str
    description: str


def _to_label_pairs(specs: Sequence[LabelSpec]) -> List[Tuple[str, str]]:
    return [(spec.name, spec.description) for spec in specs]


def build_label_reference(specs: Iterable[LabelSpec]) -> str:
    return "\n".join(f"- {spec.name}: {spec.description}" for spec in specs)


INPUT_STRUCTURE_TYPE_SPECS = [
    LabelSpec("integer", "主输入载体是单个整数或离散数值标量，题目围绕这一个数值展开；整数数组、多组数值记录或坐标对不归入此标签。"),
    LabelSpec("float", "主输入载体是单个浮点数或实数标量，精度与连续取值本身有意义；浮点数组、点集或固定字段记录不归入此标签。"),
    LabelSpec("char", "主输入载体是单个字符，题目读取并处理的是一个独立字符；字符序列、字符串、模式串与文本串统一归入 string。"),
    LabelSpec("boolean", "题面明确给出真值标记、开关状态或等价逻辑输入时使用；用 0 和 1 表示的普通数值输入仍按 integer 处理。"),
    LabelSpec("tuple", "主输入是定长元组、pair 或固定字段记录，位置和字段角色稳定；可变长度序列、普通数组与多行同构条目不归入此标签。"),
    LabelSpec("array", "主输入以线性序列、列表、查询流或同构条目集合给出，按下标或顺序访问是主组织方式；固定字段记录、矩阵、图和树不归入此标签。"),
    LabelSpec("string", "主输入是字符串、字符序列、模式串或文本串，顺序和字符内容共同承载语义；单个字符归入 char，二维字符网格归入 matrix。"),
    LabelSpec("matrix", "主输入是二维矩阵、棋盘、网格或表格，行列坐标共同决定语义；一维序列不归入此标签，显式边集合描述的图也不归入此标签。"),
    LabelSpec("graph", "主输入核心是一般图结构，节点和边关系承载语义，可带方向、权重或多种图性质；树结构优先归入 tree。"),
    LabelSpec("tree", "主输入核心是树结构，父子层级或无环连通关系是题目基础；一般图不归入此标签，树上附属查询可通过 components 补充。"),
    LabelSpec("composite", "多个关键输入载体并列出现且不存在单一主载体时使用，并需要在 components 中展开；能明确归结为某个主载体时不使用此标签。"),
    LabelSpec("other", "现有主类型都无法准确覆盖时才使用；常见标量、数组、字符串、矩阵、图、树与复合输入都不应落到此标签。"),
]

INPUT_STRUCTURE_TYPE_LABELS = _to_label_pairs(INPUT_STRUCTURE_TYPE_SPECS)


INPUT_STRUCTURE_PROPERTY_SPECS = [
    LabelSpec("directed", "题面明确说明边、关系或操作具有方向性时写 true；无向关系或未说明方向时不填写。"),
    LabelSpec("weighted", "题面明确给出边权、点权、代价、长度或其他附带数值属性时写 true；只有编号而没有语义权值时不填写。"),
    LabelSpec("connected", "题面明确保证整体连通时写 true；只要求局部可达、可能不连通或没有明确保证时不填写。"),
    LabelSpec("rooted", "题面明确指定根节点、根状态或父子朝向时写 true；普通无根树或一般图不填写。"),
    LabelSpec("simple", "题面明确说明无重边、无自环或 simple graph 时写 true；若未给出该保证，不根据常识补写。"),
    LabelSpec("acyclic", "题面明确说明结构无环时写 true；树通常可写 true，一般图若未说明无环则不填写。"),
    LabelSpec("ordered", "输入成员的顺序本身携带语义时写 true，题面明确是无序集合语义时写 false；没有明确证据时不填写。"),
    LabelSpec("sorted", "题面明确给出已排序、非降序、单调序列等保证时写 true；需要算法自行排序时不填写。"),
    LabelSpec("distinct", "题面明确保证元素互异时写 true，明确允许重复时写 false；没有直接证据时不填写。"),
    LabelSpec("permutation", "题面明确说明输入是排列或与 1..n 的双射时写 true；普通互异数组不自动视为排列。"),
    LabelSpec("multiple_test_cases", "输入首部存在测试组数并且后续结构按组重复时写 true；单题单实例输入不填写。"),
    LabelSpec("online_queries", "题目要求按顺序处理查询且后续查询依赖前面结果时写 true；离线查询列表或普通批量询问不自动填写。"),
]

INPUT_STRUCTURE_PROPERTY_KEYS = [
    spec.name for spec in INPUT_STRUCTURE_PROPERTY_SPECS
]


CORE_CONSTRAINT_SPECS = [
    LabelSpec("connectivity", "约束要求图、状态空间或构造对象保持连通或满足可达性时使用；普通输入保证连通而不影响解语义时不单列。"),
    LabelSpec("acyclicity", "约束要求结构无环或禁止形成环时使用；树的输入类型信息本身不必重复写成约束。"),
    LabelSpec("bipartiteness", "约束要求图或关系可二染色、分属两侧或满足二部性质时使用；普通奇偶分类不归入此标签。"),
    LabelSpec("degree_bound", "约束直接限制节点、元素或位置的度数、入度、出度或连接数量时使用；一般计数上界若不对应度语义则不使用。"),
    LabelSpec("path_constraint", "约束围绕路径合法性、简单路径、长度限制、经过关系或路径形态展开时使用；单纯最短路目标不自动归入此标签。"),
    LabelSpec("matching_constraint", "约束要求一对一配对、匹配合法性或匹配规模条件时使用；普通互异分配若没有匹配语义则不优先使用。"),
    LabelSpec("flow_constraint", "约束涉及流量、容量、供需守恒或边通过量限制时使用；普通总和上界但没有流网络语义时不使用。"),
    LabelSpec("coloring_constraint", "约束要求颜色分配合法、相邻颜色不同或颜色数量受限时使用；普通类别编号限制不自动归入此标签。"),
    LabelSpec("spanning_constraint", "约束要求结果覆盖全部节点并形成生成树、生成森林或等价的全覆盖连通骨架时使用；普通连通要求不单独升格为此标签。"),
    LabelSpec("order_constraint", "约束要求顺序、相对位置、拓扑先后、单调排列或先后依赖关系时使用；算法扫描顺序不属于此标签。"),
    LabelSpec("distinctness", "约束要求元素、值、位置或选择结果互异时使用；排列特有的一一对应约束优先归入 permutation_constraint。"),
    LabelSpec("adjacency_relation", "约束依赖相邻、邻接、相连或局部接触关系时使用；一般图边存在本身若只是输入结构不单列。"),
    LabelSpec("frequency_bound", "约束限制某值、字符、颜色或事件出现次数的上下界或精确次数时使用；单纯数组长度上界不使用。"),
    LabelSpec("subsequence_constraint", "约束要求对象是子序列、子串、连续片段或满足特定片段结构时使用；普通顺序关系但没有片段语义时不使用。"),
    LabelSpec("permutation_constraint", "约束要求结果或输入形成排列、置换、双射或完整重排时使用；仅仅互异但不要求覆盖全部元素时不使用。"),
    LabelSpec("range_bound", "约束中的取值范围本身参与语义，例如容量、允许步长、颜色编号区间或答案候选区间时使用；普通 n、m、q 或 a_i 读入范围不使用。"),
    LabelSpec("sum_constraint", "约束直接限定总和、前缀和、区间和或资源总量时使用；目标函数要求最小化或最大化总和不属于该标签。"),
    LabelSpec("balance_constraint", "约束要求前缀不欠账、左右平衡、括号合法、净差受控或类似守恒平衡时使用；普通总量上界不优先归入此标签。"),
    LabelSpec("divisibility", "约束围绕整除、同余、模类或余数条件时使用；偶奇性条件更适合归入 parity。"),
    LabelSpec("parity", "约束只关心奇偶性或 parity class 时使用；更一般的模 k 关系优先归入 divisibility。"),
    LabelSpec("linear_relation", "约束可以稳定表述为线性等式、不等式或线性组合关系时使用；非线性、图结构或纯顺序约束不归入此标签。"),
    LabelSpec("convexity", "约束依赖凸性、凹性、凸包次序或斜率单调一类几何或数值结构时使用；目标函数凸不自动构成约束标签。"),
    LabelSpec("distance_bound", "约束直接限制点对距离、树上距离、编辑距离或步数距离时使用；若距离只是优化目标而非合法性条件，不使用。"),
    LabelSpec("overlap_constraint", "约束禁止、限制或要求区间、集合、路径、图形之间的交叠和交叉时使用；普通相邻关系不归入此标签。"),
    LabelSpec("orientation_constraint", "约束依赖方向、朝向、左右、顺逆时针或相对方位时使用；有向图输入类型本身不必重复写成约束。"),
    LabelSpec("subset_constraint", "约束要求从候选集合中选择满足条件的子集时使用；若重点是完整划分则优先归入 partition。"),
    LabelSpec("partition", "约束要求把元素分成若干互不重叠部分且整体被完全划分时使用；只选其中一部分不归入此标签。"),
    LabelSpec("coverage", "约束要求选出的对象覆盖全部元素、位置、点或需求时使用；普通生成树覆盖优先归入 spanning_constraint。"),
    LabelSpec("exclusion", "约束明确禁止同时出现、禁止选择、禁止经过或要求互不相容时使用；一般 distinctness 不自动归入此标签。"),
    LabelSpec("inclusion", "约束要求必须包含、必须选择、必须经过或必须满足某些必要元素时使用；可选偏好不归入此标签。"),
    LabelSpec("operation_limit", "约束限制操作次数、修改预算、回合数或资源配额时使用；时间复杂度和机器资源限制不使用。"),
    LabelSpec("operation_type", "约束规定允许执行哪些操作、禁止哪些操作或每次操作的合法形式时使用；算法内部步骤不归入此标签。"),
    LabelSpec("state_transition", "约束定义状态之间什么转移合法、什么转移非法时使用；普通 DP 转移思路若未成为题面约束，不使用。"),
    LabelSpec("rewrite_rule", "约束要求按照替换、改写、映射、合并或文法式规则演化对象时使用；普通单步操作若没有改写语义，不优先使用。"),
    LabelSpec("palindrome", "约束要求字符串、序列或构造结果满足回文性质时使用；只涉及对称但不要求回文时不使用。"),
    LabelSpec("pattern_matching", "约束要求匹配模板、通配模式、正则式样或固定模式结构时使用；普通子串存在性若无模式语义，不优先使用。"),
    LabelSpec("alphabet_constraint", "约束限制可用字符集、符号表、字母类别或字符合法范围时使用；普通字符输入但没有额外限制时不使用。"),
    LabelSpec("periodicity", "约束要求周期重复、循环节一致或按周期模式出现时使用；普通循环算法过程不归入此标签。"),
    LabelSpec("optimal_play", "约束来自双方轮流行动且都按最优策略选择的对抗过程时使用；单人贪心或普通最优化不归入此标签。"),
    LabelSpec("probability_distribution", "约束明确给出随机过程、分布、独立性或概率质量定义时使用；期望目标但没有概率模型约束时不使用。"),
]

CORE_CONSTRAINT_LABELS = _to_label_pairs(CORE_CONSTRAINT_SPECS)


OBJECTIVE_SPECS = [
    LabelSpec("value_computation", "题目要求计算某个已经定义好的结果值，没有显式最优性比较；若需要在多种方案间选最优，不归入此标签。"),
    LabelSpec("maximize_value", "题目要求在合法方案中让某个数值目标尽可能大，例如总和、收益、长度、数量或期望；若要求最小化则不使用。"),
    LabelSpec("minimize_value", "题目要求在合法方案中让某个数值目标尽可能小，例如代价、距离、步数或损失；若要求最大化则不使用。"),
    LabelSpec("lexicographic_optimize", "结果优劣由字典序直接决定时使用，例如最小字典序字符串或最大字典序排列；普通数值最优不归入此标签。"),
    LabelSpec("decision", "题目主要求是判断某条件、性质或可行性是否成立，通常输出 Yes 或 No、true 或 false；若还要构造方案则不优先使用。"),
    LabelSpec("construction", "题目要求输出满足条件的对象、路径、数组、图或操作方案本身时使用；若只需输出该方案对应的最优值，不归入此标签。"),
    LabelSpec("counting", "题目要求统计合法对象、方案、事件或路径数量，常伴随取模输出；若只是求最大数量或最小次数，分别归入 maximize_value 或 minimize_value。"),
    LabelSpec("game_outcome", "题目要求给出最优博弈下的胜负、平局或赢家身份时使用；普通 decision 不处理双方最优行动。"),
    LabelSpec("other", "现有目标类型都无法准确覆盖时才使用；常见计算、优化、判定、构造、计数和博弈结果都不应落到此标签。"),
]

OBJECTIVE_LABELS = _to_label_pairs(OBJECTIVE_SPECS)


INVARIANT_SPECS = [
    LabelSpec("monotonicity", "算法持续维护单调边界、单调指针、单调队列顺序或答案可行区间的单向推进时使用；仅有排序结果而没有维护过程不归入此标签。"),
    LabelSpec("state_transition", "正确性依赖稳定的状态定义与转移关系，状态含义在全过程中保持一致时使用；泛泛提到 DP、搜索或递推而没有明确状态语义时不使用。"),
    LabelSpec("additivity", "整体答案、代价或摘要可以拆成若干部分求和或独立累加时使用；只是把多个步骤顺次执行但不能分解贡献时不归入此标签。"),
    LabelSpec("mergeability", "局部摘要、区间结果或子树信息可以通过固定规则稳定合并时使用；若只能重新扫描原数据才能得到全局结果，不使用。"),
    LabelSpec("dependency_order", "节点、状态或子问题必须按稳定的依赖顺序处理，例如拓扑序、树的后序或按长度递增时使用；普通循环次序不归入此标签。"),
    LabelSpec("conservation", "算法维护总量守恒、净变化平衡、流量守恒或等价的质量不变关系时使用；普通计数累计但没有守恒约束时不使用。"),
    LabelSpec("dominance", "某些候选、状态或决策一旦被更优项稳定支配就可以永久删除时使用；暂时比较大小但不能安全删去时不归入此标签。"),
    LabelSpec("exchange_argument", "替换局部选择后仍保持可行性或最优性，正确性建立在可交换、可替换关系上时使用；普通贪心直觉但没有交换依据时不使用。"),
    LabelSpec("potential_function", "算法通过势函数、摊还记账或单调下降的代价函数证明过程有界时使用；只有复杂度结论但没有势能维护对象时不使用。"),
    LabelSpec("convexity", "正确性依赖凸性、凹性、斜率顺序或包络结构稳定性时使用；题目含几何元素但算法不维护这类结构时不使用。"),
    LabelSpec("symmetry", "算法利用对称性、镜像等价或交换变量后结果不变来减少情况时使用；普通相似写法但没有对称归约关系时不归入此标签。"),
    LabelSpec("idempotency", "某类操作重复执行不会继续改变状态或结果，算法依赖这种重复作用稳定性时使用；仅仅因为最后一次赋值覆盖前值不构成此标签。"),
    LabelSpec("equivalence_class", "算法稳定维护同余类、奇偶类、异或类、连通块代表或其他等价类划分时使用；一般分组但没有等价关系支撑时不使用。"),
]

INVARIANT_LABELS = _to_label_pairs(INVARIANT_SPECS)



CONSTRAINT_SOURCE_SECTIONS = [
    "description",
    "input",
    "output",
    "constraints",
]


INVARIANT_EVIDENCE_SOURCES = [
    "statement",
    "solution_code",
    "both",
]
