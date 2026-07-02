# P3-7 自动调度执行链路原型设计

生成时间：2026-07-02

## 目标

让 AIOS 从“能看到下一步该做什么”升级到“能按调度结果自动派发下一条任务并调用执行器”。

这一阶段仍然是受控自动化，不追求全自动闭环。重点是先把：

- 自动选下一条可执行任务
- 调用统一执行器入口
- 回写执行记录和调度状态

这三件事跑通。

## 范围

本阶段实现：

- 新增 `auto_dispatch_next_task`
- 新增 CLI 入口：`aios run auto`
- 新增 API：`POST /api/run/dispatch`
- 单项目 Web UI 增加“自动派发下一任务”按钮
- 自动派发结果复用现有执行记录、handoff、executor 日志和 scheduler 摘要

本阶段不实现：

- 自动切换 `ccswitch`
- 自动打开或控制 Codex / Claude Code 会话
- 自动 `finish`
- 自动重试失败任务
- 并行调度多条任务

## 调度规则

V1 只派发满足以下条件的任务：

1. `scheduler_state == ready`
2. `next_action == run_executor`

当前选择策略保持简单：

- 按现有任务顺序取第一条 `ready` 任务
- 如果没有可执行任务，则不报系统异常，返回“未派发”结果和阻塞原因

阻塞提示优先级：

1. 存在 `review_pending`
2. 存在 `failed`
3. 存在 `active`
4. 仍有 `blocked`
5. 没有可执行任务

## CLI 变化

新增：

```bash
aios run auto
aios run auto --executor codex-cli
```

行为：

- 若未显式指定 `--executor`，自动选全局执行器库中第一个启用的命令型执行器
- 若成功派发，输出任务、执行器、模型、Pack、Handoff、日志路径
- 若当前不允许派发，输出阻塞原因和调度器建议动作

## API 变化

新增：

- `POST /api/run/dispatch`

请求字段：

- `executor_id` 可选
- `model` 可选
- `refresh_pack` 可选
- `note` 可选

返回结构：

- `dispatched`
- `reason`
- `scheduler_before`
- `scheduler_after`
- `scheduler_item`
- `task`
- `route`
- `handoff`
- `execution`
- `executor`

若没有可派发任务，`dispatched = false`，其余任务相关字段为 `null`。

## Web UI 变化

单项目任务检查器新增主动作：

- `自动派发下一任务`

行为：

- 默认使用当前全局默认执行器
- 成功后自动刷新状态并选中被派发任务
- 若当前有待复核、失败或阻塞任务，则直接显示原因

## 兼容边界

- 原有 `aios run TASK-ID --executor ...` 保持不变
- 原有 `POST /api/run/execute` 保持不变
- 自动派发只是新入口，不替代显式单任务执行
- 执行成功后依旧进入 `review_pending`，仍需人工 review + `run finish`

## 测试计划

### 自动化测试

1. `aios run auto --executor ...` 能派发第一条 `ready` 任务
2. `POST /api/run/dispatch` 能返回执行结果
3. 若存在 `review_pending`，自动派发返回 `dispatched = false`
4. Web 资源中包含自动派发入口

### 手工验收

1. 初始化项目并扫描
2. 创建一个有依赖关系的任务组
3. 点击“自动派发下一任务”
4. 确认系统选择的是第一条可执行任务，而不是被阻塞任务
5. 执行结束后任务进入 `review_pending`
6. 回写完成总结，确认任务进入 `done`

## 下一步

P3-7 跑通后，后续自动化主线可以继续推进：

- `P3-8` 自动 `finish` 收口策略
- `P3-9` 成本统计
- `P3-10` 自动 Git 提交

但前提仍然是先把执行器稳定性、调度顺序和 review 收口打牢。
