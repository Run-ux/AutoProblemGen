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
