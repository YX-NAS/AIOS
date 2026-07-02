# P3-6 执行总览增强与调度前置状态设计

生成时间：2026-07-02

## 目标

让 AIOS 从“知道有哪些任务和执行记录”升级到“知道当前哪些任务能执行、哪些被阻塞、下一步应该做什么”。

这一阶段的重点不是自动调度本身，而是先把自动调度所需的状态面板和前置判断补齐。

## 范围

本阶段实现：

- 新增 `scheduler_summary`
- 单项目 Web API 暴露 `/api/scheduler`
- 单项目状态返回：
  - `ready_count`
  - `blocked_count`
  - `review_pending_count`
  - `failed_count`
  - `next_task_id`
  - `next_task_title`
  - `next_action`
- 单项目页显示调度状态卡
- launcher 项目卡片显示调度摘要

本阶段不实现：

- 真正自动串行执行下一条任务
- 自动重试失败任务
- 并行任务调度
- 基于成本或执行器可用性的复杂策略优化

## 调度状态定义

当前调度状态包括：

- `ready`
- `blocked`
- `review_pending`
- `failed`
- `active`
- `done`

判定规则：

1. 任务已完成 -> `done`
2. 执行记录为 `review_pending` -> `review_pending`
3. 执行记录为 `failed` -> `failed`
4. 任务状态为 `running` -> `active`
5. 依赖未满足 -> `blocked`
6. Pack 质量存在强告警 -> `blocked`
7. 其他待执行任务 -> `ready`

## 下一步动作

每条调度项会给出一个 `next_action`：

- `run_executor`
- `wait_dependencies`
- `review_finish`
- `inspect_retry`
- `monitor_running`

这一步是为了给后续自动调度链路提供明确控制点。

## 前端展示

### 单项目页

新增：

- 概览卡片中的“可执行任务”“被阻塞任务”
- 任务检查器中的“调度状态”卡

### launcher 首页

新增：

- 可执行任务数
- 被阻塞任务数
- 待复核数
- 执行失败数
- 下一步动作
- 下一条建议任务

## 测试计划

### 自动化测试

1. `scheduler_summary` 能区分 `ready` / `blocked`
2. 执行器运行成功后进入 `review_pending`
3. `/api/scheduler` 返回调度项
4. launcher 项目摘要包含调度字段
5. 前端静态资源包含调度卡和调度指标入口

### 手工验收

1. 创建带依赖关系的任务树
2. 查看单项目页调度状态
3. 执行一条任务并让其进入 `review_pending`
4. 查看 launcher 首页摘要是否刷新
5. 确认下一步动作和下一条任务显示合理

## 下一步

P3-6 完成后，后续自动化主线就该转入：

- 调度器驱动的自动执行排序
- 失败阻断和回退
- review_pending 收口策略

也就是从“看得见调度状态”，正式进入“按调度状态驱动执行”。
