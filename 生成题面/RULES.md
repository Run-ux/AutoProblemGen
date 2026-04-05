# 规则开发说明

本目录的规则系统采用“规则声明 + 代码执行”模式。

## 新增规则的最小交付

新增一条规则时，需要同时完成四部分：

- 更新 `planning_rules.json`
- 在 `rule_handlers.py` 注册对应 `handler`
- 补单元测试或集成测试
- 同步更新文档

缺任意一项，都不应视为规则已经接入。

## 规则文件要求

每条规则至少包含：

- `id`
- `family`
- `audit_tags`
- `handler`
- `required_axis_changes`
- `planner_output_contract`
- `validation_contract`

`handler` 必须和 `rule_handlers.py` 中注册的名称一致。

## Handler 合同

每个 handler 需要覆盖三类责任：

- `check_eligibility`
  - 通过角色审查式 prompt 发起 LLM 资格审查
  - 定义该规则的 `review_role`
  - 返回结构化分数、失败码、风险标签，并写入审计细节
- `validate_plan`
  - 先执行代码级通用硬门槛校验
  - 再通过规则专属 prompt 发起 LLM 规划审查
  - 检查辅助动作、变化轴、主目标、主状态演化与复用风险，并把规则专属审查结果落成结构化审计记录
- `validate_problem`
  - 在通用结构校验之后，通过规则专属 prompt 发起 LLM 题面审查
  - 校验题面是否兑现该规则的输出责任、失败语义与核心承诺

## 审计要求

规则实现必须能产出结构化审计信息，至少覆盖：

- 资格判断结论
- 资格审查角色与 LLM 证据摘录
- 规划校验结论
- 题面校验结论
- 规则专属 LLM 审查的证据摘录
- 失败码
- 可读失败原因

这些信息会进入 artifact 的以下字段：

- `rule_version`
- `selection_trace`
- `validation_trace`
- `candidate_attempts`

## 测试要求

每条规则至少应覆盖：

- 一个资格通过用例
- 一个资格拒绝用例
- 一个规划通过用例
- 一个题面拒绝用例

如果规则参与排序式选择，还应补至少一个候选回退用例。
