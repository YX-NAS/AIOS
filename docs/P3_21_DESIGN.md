# P3-21 Bridge 确认闭环设计

生成时间：2026-07-02

## 目标

在 `P3-20` 已经具备 bridge 步骤审计后，补上“结果确认闭环”：

- 系统观察到 bridge 动作执行到了哪一步；
- 操作者确认外部切换结果是否真的可继续；
- AIOS 形成 `pending_confirmation -> confirmed_ready / confirmed_failed` 的显式收口。

这一步的目的，不是伪装成已经能自动读取 `ccswitch` 内部状态，而是先把“观察结果”和“人工确认结果”分离建模。

## 本期范围

- CLI：`aios ccswitch confirm TASK-ID --status ...`
- API：`POST /api/ccswitch/confirm`
- Web UI：bridge 成功/失败确认按钮
- bridge JSON 与 execution record 增加确认字段

## 状态模型

bridge 运行状态：

- `prepared`
- `running`
- `completed`
- `failed`

bridge 确认状态：

- `not_requested`
- `pending_confirmation`
- `confirmed_ready`
- `confirmed_failed`

规则：

- 仅导出 bridge 但未执行：`not_requested`
- 执行过 bridge：进入 `pending_confirmation`
- 操作者确认外部状态正常：`confirmed_ready`
- 操作者确认 bridge 结果不可继续：`confirmed_failed`

## 数据结构

bridge JSON 新增：

- `bridge_confirmation_status`
- `bridge_confirmation_note`
- `bridge_confirmed_at`

执行记录新增：

- `ccswitch_bridge_confirmation_status`
- `ccswitch_bridge_confirmation_note`
- `ccswitch_bridge_confirmed_at`

## CLI 设计

新增：

```bash
aios ccswitch confirm TASK-ID --status confirmed_ready
aios ccswitch confirm TASK-ID --status confirmed_failed --note "provider 已导入但会话不对"
```

目的：

- 让外部切换结果进入 AIOS 的任务记录；
- 为后续调度器判断“是否可继续自动执行”提供依据。

## Web 设计

单项目页新增：

- `确认桥接成功`
- `标记桥接失败`

以及一个可选备注输入框。

这不是多余按钮，而是 bridge 闭环的一部分。没有这一步，系统只知道动作发过，不知道外部状态是否真的达标。

## 边界

本期仍然不做：

- 自动读取 `ccswitch` 当前 provider
- 自动读取 `ccswitch` 当前会话
- 自动判断导入 prompt 后是否进入正确上下文

这些能力需要稳定的外部接口或更重的桌面控制层，当前没有可靠前提。

## 测试方案

自动化测试：

1. CLI confirm
   - bridge 执行后确认 `confirmed_ready`
   - 校验 execution 和 bridge JSON 都被更新

2. API confirm
   - bridge 执行后确认 `confirmed_failed`
   - 校验状态和备注回写

3. 回归
   - 旧 bridge 成功/失败测试继续通过

## 下一步关系

P3-21 完成后，AIOS 才具备继续做这些事情的前提：

- 调度器跳过 `pending_confirmation` 的任务
- 对 `confirmed_failed` 的任务触发重试建议
- 对 `confirmed_ready` 的任务继续推进执行或验收
