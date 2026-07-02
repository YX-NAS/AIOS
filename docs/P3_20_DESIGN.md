# P3-20 桥接结果可观测层设计

生成时间：2026-07-02

## 目标

在 `P3-19 ccswitch bridge` 已经能发起桥接动作的基础上，补齐：

- 每一步是否执行成功
- 失败停在第几步
- 最后一条错误是什么
- 桥接包和执行记录里是否能完整回看

如果没有这层可观测性，AIOS 虽然“能发动作”，但还不能稳定支撑后续自动调度和失败恢复。

## 本期范围

- bridge JSON 增加步骤状态字段
- 执行记录增加 bridge 运行状态字段
- Web UI 显示 bridge 状态 / 最后步骤 / 错误
- 测试覆盖成功和失败两条路径

## 数据结构

bridge JSON 新增：

- `bridge_status`
- `bridge_last_step`
- `bridge_error`
- `bridge_started_at`
- `bridge_finished_at`

`steps[]` 每一步新增：

- `status`
- `started_at`
- `finished_at`
- `error`

执行记录新增：

- `ccswitch_bridge_status`
- `ccswitch_bridge_last_step`
- `ccswitch_bridge_error`
- `ccswitch_bridge_started_at`
- `ccswitch_bridge_finished_at`

## 状态模型

桥接总状态：

- `prepared`
- `running`
- `completed`
- `failed`

步骤状态：

- `pending`
- `running`
- `completed`
- `failed`

桥接执行原则：

- 任一步失败，后续步骤不再继续；
- 已完成步骤保留完成状态；
- 未开始步骤保持 `pending`；
- 错误信息写入当前失败步骤和桥接总对象。

## UI 变化

单项目任务检查器的执行状态区补充：

- Bridge 状态
- Bridge 最后步骤
- Bridge 错误

活动反馈区在启动桥接后显示：

- bridge 状态
- 每一步的摘要
- 如有失败，显示错误原因

## 测试方案

自动化测试：

1. bridge 成功路径
   - 全部步骤 `completed`
   - 执行记录状态 `completed`

2. bridge 失败路径
   - 模拟 prompt deeplink 打开失败
   - 验证：
     - 第二个 deeplink 步骤为 `failed`
     - 终端步骤仍为 `pending`
     - 执行记录状态为 `failed`

3. API 成功路径
   - 返回 bridge 状态
   - 返回 execution 审计字段

## 下一步关系

P3-20 完成后，下一阶段才适合继续做：

- `ccswitch` 导入确认
- 历史会话自动选择
- 失败后的自动重试

否则系统无法判断前一步是否真的成功。
