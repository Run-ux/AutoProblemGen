# 基于 Problem Schema 的自动编程竞赛题目生成框架

本项目的目标是构建一个可扩展、可去重、可自动生成的编程竞赛题目生成系统。核心思路不是直接用自然语言“从零写题”，而是先从高质量竞赛题中抽象出 **Problem Schema**，再基于 Schema 完成去重、变形与生成。

可以将 Schema 理解为算法竞赛题目的中间表示（IR）：它连接题面文本、算法结构、工程规则与自动生成流程。

---

## 1. 从具体题目到母题 Schema

系统从已有高质量竞赛题出发，而非空白生成。候选题目主要来自：

- ICPC World Finals / Regional
- Codeforces（Div.2 D/E，Div.1 C/D）
- AtCoder（ABC F，ARC，AGC）
- NOI / 省选公开题目

输入必须是结构完整的题面文本，至少包含：

- 问题描述
- 输入输出格式
- 数据范围与约束

对每道候选题，使用大语言模型抽取统一的 **Schema 五元组**，关注题目语义和算法结构，而不是具体代码实现：

```text
题目文本 -> Problem Schema 五元组
```

由于不同题目可能对应同一算法原型，系统不在题目文本层面去重，而在 Schema 层面进行相似性判断：

- 高相似 Schema 合并为同一个母题
- 显著不同的 Schema 作为新母题加入母题库

最终得到一个规模可控、结构多样的母题 Schema 库。

---

## 2. 基于 Schema 的自动出题流程

母题 Schema 库建立后，自动出题流程如下：

```text
选择母题 Schema
  ↓
选择变形参数（约束 / 目标 / 数据规模）
  ↓
生成 Schema Instance
  ↓
生成新题面
  ↓
生成测试数据
  ↓
生成或验证标准解法
```

其中：

- 母题 Schema 决定算法骨架与不变量
- 变形参数决定难度、考点组合与题目风格
- 新题在 Schema 层面可证明“非重复”

Schema 在系统中的作用包括：

- 作为母题去重与分类的基本单位
- 作为自动出题的最小生成单元
- 作为题目多样性与覆盖度的度量基础
- 作为 AI 理解能力与工程规则之间的中介表示

---

## 3. Problem Schema 五元组的正式定义

为支持可扩展、可去重、可生成的系统设计，项目将每道题抽象为：

```text
S = (I, C, O, V, T)
```

其中：

- `I`：Input Structure，输入结构
- `C`：Core Constraints，核心约束集合
- `O`：Objective，目标函数
- `V`：Invariant，算法不变量
- `T`：Transform Space，可变参数空间

该五元组描述的是一类题目的**算法本质**，而不是某一道具体题目。

### 3.1 输入结构（I）

输入结构描述数据组织形式，如数组、图、树、字符串、矩阵等。它通常是算法选择的第一决定因素，也有助于快速分类母题并约束解法生成范围。

```python
@dataclass
class InputStructure:
    type: str
    length: Dict[str, int]
    value_range: Dict[str, int]
    properties: Dict[str, Any]
```

### 3.2 核心约束集合（C）

核心约束表示题目必须满足的限制条件，例如：

- 区间内不同元素个数 <= K
- 最大值 - 最小值 <= D
- 路径长度限制
- 状态转移合法性条件

约束以集合形式建模，因为竞赛题难度往往来自多约束组合。

```python
@dataclass
class Constraint:
    name: str
    description: str
    check: Callable[[Dict[str, Any]], bool]
```

```python
core_constraints: List[Constraint]
```

示例：

```python
def distinct_leq_k(ctx):
    return ctx["distinct"] <= ctx["K"]

constraint_distinct = Constraint(
    name="distinct_leq_k",
    description="区间内不同元素数量不超过 K",
    check=distinct_leq_k
)
```

### 3.3 目标函数（O）

目标函数描述题目的求解目标，如最大值、最小值、计数、判定等。同一算法结构在不同目标下可以形成不同题型，因此需要单独建模。

```python
@dataclass
class Objective:
    type: str
    description: str
```

### 3.4 算法不变量（V）

算法不变量描述解法始终成立的结构性条件，例如：

- 双指针左右端点单调前进
- 前缀和可叠加
- DP 状态只依赖子状态

不变量是最核心的部分，因为它决定解法范式，也是 Schema 去重与距离计算中权重最高的维度。

```python
@dataclass
class Invariant:
    name: str
    description: str
    properties: Dict[str, Any]
```

示例：

```python
invariant = Invariant(
    name="two_pointer",
    description="左右指针单调前进，区间合法性可单调维护",
    properties={
        "left_monotonic": True,
        "right_monotonic": True,
        "window_shrinkable": True
    }
)
```

### 3.5 可变参数空间（T）

可变参数空间定义在不破坏不变量前提下，题目可被变形的维度，例如：

- 参数 `K`、`D` 的取值范围
- 是否允许多约束叠加
- 目标函数是否可切换
- 数据规模等级

它本质上是自动出题系统的“调节旋钮”，决定同一 Schema 可生成多少不同题目。

```python
transform_params: Dict[str, Any]
```

示例：

```python
transform_params = {
    "K": {"min": 1, "max": 100000},
    "D": {"min": 0, "max": 10**9},
    "objective_options": ["max_length", "count"],
    "multi_constraints": True
}
```

### 3.6 完整 Python 表示

```python
@dataclass
class ProblemSchema:
    name: str
    input_structure: InputStructure
    core_constraints: List[Constraint]
    objective: Objective
    invariant: Invariant
    transform_params: Dict[str, Any]
```

该结构具备三项关键能力：

- 可扩展：Transform Space 支持参数化与组合式变形
- 可去重：可基于五元组定义结构距离
- 可生成：可直接为题面、数据、解法生成模块提供输入

---

## 4. 母题来源与候选题目的获取

项目中的“母题”不是某一道具体题，而是从高质量竞赛题中抽象出的算法结构原型。候选题选择遵循以下原则：

1. 算法模型清晰
2. 题面信息完整
3. 竞赛验证充分
4. 结构可抽象为 Problem Schema

### 4.1 各题源与获取方式

#### ICPC World Finals / Regional

- 特点：题目质量高，算法模型稳定，母题纯度高
- 获取方式：收集公开 PDF，提取文本后整理为标准题面

```text
PDF 文件
  -> 文本提取
  -> 标准化题面格式
  -> 保存为 .txt 或 .md
```

#### Codeforces

- 特点：题量大、覆盖广，同一 Schema 下变形丰富
- 重点范围：Div.2 D/E，Div.1 C/D
- 推荐方式：通过官方 API 获取题目，再清洗 HTML 题面

```text
Codeforces API
  -> 获取题目列表
  -> 获取题目 HTML
  -> 清洗并提取题面文本
  -> 统一格式存储
```

```python
import requests
from bs4 import BeautifulSoup

def fetch_cf_problem(contest_id, problem_index):
    url = f"https://codeforces.com/contest/{contest_id}/problem/{problem_index}"
    html = requests.get(url).text
    soup = BeautifulSoup(html, "html.parser")
    statement = soup.find("div", class_="problem-statement")
    return statement.get_text(separator="\n")
```

#### AtCoder

- 特点：题面严谨、冗余少、约束规范
- 推荐范围：ABC F，ARC C 及以上，AGC 全部题目
- 获取方式：官网 HTML 题面或 AtCoder Problem Archive

```text
题目页面 HTML
  -> 抽取 Problem Statement 区域
  -> 按段落整理文本
  -> 标准化格式存储
```

#### NOI / 省选

- 特点：覆盖高难度 DP 与图论 Schema
- 获取方式：公开 PDF 题面与教学整理资料

### 4.2 候选题文本标准化格式

为便于 LLM 抽取 Schema，所有候选题面统一为：

```text
[Problem Title]

[Problem Description]

Input
...

Output
...

Constraints
...
```

标准化要求：

- 不包含样例
- 不包含提示或解题说明
- 保留全部约束信息

### 4.3 获取流水线

```text
竞赛平台 / PDF / API
        ↓
题面文本获取
        ↓
文本清洗与标准化
        ↓
结构化存储（txt / md）
        ↓
输入至 LLM 进行 Schema 抽取
```

该模块输出标准化题面文本，直接作为下一阶段 Schema 抽取的输入，从而实现题源获取与后续流程解耦。

---

## 5. 基于 Schema 的母题去重与相似度计算

如果仅在题目文本层面去重，会遇到三个问题：

- 同一题可能有多个平台版本
- 不同题面描述可能对应同一算法结构
- 文本相似度无法反映算法本质

因此，系统采用的原则是：

> 不在题目层面去重，而在 Problem Schema 层面去重。

### 5.1 去重层级

系统区分三个层次：

- Problem：具体题目
- Schema Instance：参数化后的 Schema
- Mother Schema：母题 Schema

去重与聚类的目标是 **Mother Schema 层级**。

### 5.2 Schema 距离函数

每个 Schema 表示为：

```text
S = (I, C, O, V, T)
```

定义距离函数：

```text
D(S1, S2) ∈ [0, 1]
```

- 距离越小，Schema 越相似
- 距离越大，Schema 越不同

### 5.3 五个分量的距离设计

#### 输入结构距离 `d_I`

输入结构为离散类型，可用人工定义的距离矩阵表示：

| I1    | I2    | 距离 |
| ----- | ----- | ---- |
| array | array | 0.0  |
| tree  | graph | 0.3  |
| array | graph | 1.0  |

```python
INPUT_STRUCTURE_DISTANCE = {
    ("array", "array"): 0.0,
    ("tree", "graph"): 0.3,
    ("array", "graph"): 1.0,
}
```

#### 核心约束集合距离 `d_C`

将约束视为集合，采用 Jaccard Distance：

```text
d_C = 1 - |C1 ∩ C2| / |C1 ∪ C2|
```

```python
def constraint_distance(c1, c2):
    set1 = set(c.name for c in c1)
    set2 = set(c.name for c in c2)
    return 1 - len(set1 & set2) / len(set1 | set2)
```

#### 目标函数距离 `d_O`

目标函数属于有限枚举，目标不同不一定代表母题不同，但应增加距离：

| O1         | O2         | 距离 |
| ---------- | ---------- | ---- |
| max_length | max_length | 0.0  |
| max_length | count      | 0.5  |
| count      | decision   | 0.7  |

```python
OBJECTIVE_DISTANCE = {
    ("max_length", "count"): 0.5,
    ("count", "decision"): 0.7,
}
```

#### 算法不变量距离 `d_V`

这是最关键的维度，因为不变量几乎直接决定解法范式：

| V1          | V2          | 距离 |
| ----------- | ----------- | ---- |
| two_pointer | two_pointer | 0.0  |
| two_pointer | prefix_sum  | 1.0  |
| dp_tree     | dp_interval | 0.8  |

```python
INVARIANT_DISTANCE = {
    ("two_pointer", "two_pointer"): 0.0,
    ("two_pointer", "prefix_sum"): 1.0,
}
```

#### 可变参数空间距离 `d_T`

简化处理时，可按参数数量的相对差异衡量：

```text
d_T = |len(T1) - len(T2)| / max(len(T1), len(T2))
```

```python
def transform_distance(t1, t2):
    return abs(len(t1) - len(t2)) / max(len(t1), len(t2))
```

### 5.4 总距离函数

五个分量线性加权得到总距离：

```text
D(S1, S2) =
  w1 * d_I +
  w2 * d_C +
  w3 * d_O +
  w4 * d_V +
  w5 * d_T
```

推荐权重如下：

| 维度          | 权重 |
| ------------- | ---- |
| 不变量（V）   | 0.35 |
| 约束集合（C） | 0.25 |
| 输入结构（I） | 0.15 |
| 目标函数（O） | 0.15 |
| 变形空间（T） | 0.10 |

### 5.5 去重与聚类规则

- `D < 0.25`：同一母题
- `0.25 <= D < 0.5`：同一母题族
- `D >= 0.5`：不同母题

该规则用于：

- 判断是否合并 Schema
- 控制母题库规模
- 评估 Schema 多样性

### 5.6 去重流程

```text
候选题目 Schema 集合
        ↓
逐一计算 Schema 距离
        ↓
与已有母题 Schema 比较
        ↓
小于阈值 -> 合并
否则 -> 新增母题
```

```python
mother_schemas = []

for schema in candidate_schemas:
    for m in mother_schemas:
        if schema_distance(schema, m) < THRESHOLD:
            break
    else:
        mother_schemas.append(schema)
```

---

## 6. Schema 驱动的自动出题流水线设计

完成母题库构建与去重后，系统进入自动出题阶段。设计目标包括：

- 结构正确性：生成题目在 Schema 层面必然可解
- 算法一致性：解法符合 Schema 定义的不变量
- 难度可控性：可通过参数与约束调节难度
- 工程可扩展性：不同 Schema 复用统一流水线

### 6.1 总体结构

```text
Mother Schema
  ↓
Schema 参数实例化
  ↓
题面生成（Problem Statement Generator）
  ↓
测试数据生成（Testcase Generator）
  ↓
标准解法生成 / 验证（Solver / Verifier）
```

### 6.2 Schema 参数实例化模块

职责：

- 从 Transform Space 中选取具体参数
- 生成 Schema Instance
- 确定数据规模、约束组合、目标函数与难度等级

```python
def instantiate_schema(schema, difficulty):
    params = {}
    for k, v in schema.transform_params.items():
        params[k] = sample_param(v, difficulty)
    return params
```

### 6.3 题面生成模块

题面生成依赖：

- Input Structure
- Core Constraints
- Objective
- Schema Instance

设计原则：

- 不包含解题提示
- 所有约束必须显式出现
- 语言保持竞赛风格，简洁明确

通常采用 LLM 生成：

```text
输入：
- Schema 五元组
- 实例化参数

输出：
- 标准竞赛题面文本
```

### 6.4 测试数据生成模块

职责：

- 根据输入结构生成合法输入
- 覆盖边界情况与极端参数
- 为解法验证提供数据支持

Schema 信息与作用如下：

| Schema 信息      | 用途           |
| ---------------- | -------------- |
| Input Structure  | 决定数据形态   |
| Transform Space  | 决定规模与分布 |
| Core Constraints | 决定合法性     |

```python
class TestcaseGenerator:
    def generate(self, schema, params):
        # 1. 根据 InputStructure 生成数据框架
        # 2. 根据 Transform Params 决定规模
        # 3. 调整数据以触发关键约束
        pass
```

### 6.5 标准解法生成与验证模块

职责：

- 提供当前 Schema 的标准解法模板
- 对生成数据进行正确性验证
- 保证生成题目“必然可解”

Solver 主要由不变量驱动选择：

| Invariant   | Solver       |
| ----------- | ------------ |
| two_pointer | 双指针模板   |
| prefix_sum  | 前缀和模板   |
| dp_interval | 区间 DP 模板 |

```python
class Solver:
    def __init__(self, schema):
        self.invariant = schema.invariant.name

    def solve(self, input_data):
        if self.invariant == "two_pointer":
            return solve_two_pointer(input_data)
```

### 6.6 模块解耦关系

各模块保持最小耦合：

- 题面生成不依赖数据生成细节
- 数据生成不依赖具体解法实现
- Solver 仅依赖不变量，不依赖题面文本

因此，Schema 可复用、模块可替换、系统易扩展。

### 6.7 自动出题整体伪流程

```text
选择母题 Schema
      ↓
实例化 Schema 参数
      ↓
生成题面文本
      ↓
生成测试数据
      ↓
运行 Solver 验证正确性
      ↓
输出完整新题
```

---

## 7. 总结

本项目的核心方法可以概括为：

1. 从高质量竞赛题中获取标准化题面
2. 使用 LLM 抽取 Problem Schema 五元组
3. 在 Schema 层面完成母题去重与聚类
4. 基于母题 Schema 和变形参数自动生成新题
5. 通过测试数据与标准解法验证生成结果

Problem Schema 是整个系统的统一中间表示，也是题目获取、结构去重、自动生成与工程实现之间的核心桥梁。
