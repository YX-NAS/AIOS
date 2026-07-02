# P3-22 Bridge 确认安全门设计

生成时间：2026-07-02

## 目标

把 `P3-21` 的 bridge 确认状态真正接入调度和自动派发。

否则系统虽然已经记录：

- bridge 是否执行
- bridge 是否失败
- bridge 是否确认成功

但调度器仍可能把“待确认”的任务继续往下推进，这会让全自动执行变得不可靠。

## 本期范围

- 调度器新增 `bridge_confirmation` 状态
- 自动派发在 `pending_confirmation` 时停止
- Web 调度卡和项目摘要携带 bridge 确认信息
- 测试覆盖 scheduler / dispatch 两条路径

## 调度规则

当任务存在执行记录，且：

- `ccswitch_bridge_confirmation_status == pending_confirmation`

则：

- `scheduler_state = bridge_confirmation`
- `next_action = confirm_bridge`
- 自动派发返回阻塞原因，不继续派发新任务

当：

- `ccswitch_bridge_confirmation_status == confirmed_failed`

则：

- `scheduler_state = failed`
- `next_action = retry_bridge`

这意味着 bridge 现在真正进入调度状态机，而不只是执行记录上的附属字段。

## 价值

这一步的作用不是“多一个状态名”，而是避免 AIOS 自己误推进。

从全自动执行视角看，这是非常关键的一条安全门：

- 没确认，不继续
- 确认失败，不继续
- 只有确认成功，才允许系统继续向下走

## 测试方案

自动化测试：

1. scheduler summary
   - bridge 执行后且待确认
   - 调度状态应为 `bridge_confirmation`

2. dispatch API
   - 存在 `pending_confirmation`
   - 自动派发返回阻塞原因

3. 全量回归
   - review_pending / failed / ready / active 原状态不回归
