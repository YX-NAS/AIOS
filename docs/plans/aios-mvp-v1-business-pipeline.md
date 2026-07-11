# AIOS MVP V1 业务主链技术方案

> 实现状态：已落地（v0.42.0，2026-07-11）。审核确认既有任务树、依赖判定、模型路由和执行记录可直接复用；本轮补齐 Goal 生命周期、当前任务选择器、完成回写推进和总控台摘要。

## 1. 文档目标

本方案定义 AIOS MVP V1 的核心目标：把当前“多项目入口 + 任务管理 + 模型推荐 + 执行记录”的离散能力，串成一条可以持续推进项目目标的业务主链。

这份文档用于：

1. 设计评审
2. 开发拆分
3. 测试设计输入
4. 验收标准对齐

本方案默认在当前代码基础上演进，不推翻现有 `.aios/` 目录模型，不引入远程数据库，不把全自动编码当作 V1 目标。

---

## 2. 当前状态与问题

结合当前仓库状态，AIOS 已经具备这些基础能力：

- 多项目 launcher 首页
- 单项目 Web UI
- 目标拆解为任务列表
- 任务推荐模型
- Context Pack / handoff 生成
- execution record
- scheduler 摘要
- takeover 队列

但当前 MVP 没有真正转起来，原因不是单点功能缺失，而是业务链条没有形成默认主路径。

当前核心断点：

1. 目标拆解与执行链脱节
   `task plan` 能生成任务，但这些任务不会自然进入“当前任务 -> 执行 -> 回写 -> 下一任务”的默认推进链。

2. 任务状态只记录，不驱动
   `tasks.json`、`executions.json`、scheduler 摘要是分开的，系统能描述状态，但不能稳定驱动状态迁移。

3. 总控台偏可观测，不偏可推进
   launcher 能展示 ready / blocked / running，但不能成为“项目正在推进哪个目标”的总控入口。

4. 路由推荐与真实可执行能力没有完全闭环
   当前推荐模型、旧任务模型、运行时 provider readiness 之间仍存在脱节，导致看板和实际执行能力不一致。

5. 完成回写不是业务主链默认收口
   执行完成后，系统没有稳定推进到下一条 ready 任务，仍需要人手动判断。

---

## 3. MVP V1 产品目标

MVP V1 只做一件事：

**让一个项目目标在 AIOS 内形成一条可持续推进的闭环。**

目标链路：

1. 选择项目
2. 输入目标
3. 自动拆解为任务树
4. 自动判断当前任务
5. 推荐真实可执行模型
6. 执行
7. 回写
8. 自动切换下一条任务
9. 总控台同步显示项目推进状态

一句话定义：

**用户只需要给出目标，AIOS 就能明确当前该做什么，并持续把项目从目标推进到完成。**

---

## 4. V1 范围

### 4.1 V1 必做

1. 项目级 Goal 记录
2. Goal 与任务树绑定
3. 当前任务选择器
4. 单项目推进页
5. 当前任务与推荐模型联动
6. 执行完成后的自动推进
7. launcher 项目级推进摘要
8. 统一状态流转规则

### 4.2 V1 不做

1. 自动切换 `ccswitch`
2. 自动调起 Codex / Claude Code 完整编码
3. 自动 Git commit / push / PR
4. websocket 实时推送
5. 跨项目全局任务调度
6. 自主业务验收判断
7. 多目标并行推进策略

---

## 5. 用户主流程

### 5.1 创建目标

用户进入单项目工作区，输入一句目标：

- 修复聊天时间上下文问题
- 开发会员积分系统
- 优化首页任务管理体验

系统执行：

1. 创建 Goal
2. 调用现有 `plan_goal` 生成任务树
3. 建立 `goal_id -> tasks` 的绑定
4. 计算第一条当前任务

### 5.2 推进任务

系统在项目页只突出一条当前任务，显示：

- 当前任务标题
- 任务类型
- 推荐模型
- 下一步动作
- 为什么是这条
- 是否阻塞

### 5.3 执行与回写

V1 默认仍是半自动：

- AIOS 生成 Pack / handoff
- 用户人工切模型或调用执行器
- 完成后 AIOS 回写执行结果

### 5.4 自动切换下一任务

当一条任务进入 `done` 后，系统自动：

1. 重算任务依赖
2. 重新计算 ready 列表
3. 选出新的当前任务
4. 更新 Goal 的 `current_task_id`

### 5.5 总控台回显

launcher 首页按项目显示：

- 当前目标
- 当前任务
- 当前阶段
- 是否阻塞
- 最近推进时间
- 完成度

---

## 6. 核心数据模型

---

### 6.1 Goal

新增文件：

- `.aios/goals.json`

结构建议：

```json
{
  "version": 1,
  "goals": [
    {
      "goal_id": "GOAL-20260711-001",
      "title": "开发会员积分系统",
      "summary": "完成会员积分系统的范围、设计、实现、测试与交付",
      "status": "active",
      "current_task_id": "TASK-20260711-003",
      "root_task_ids": ["TASK-20260711-001"],
      "created_from": "manual",
      "created_at": "2026-07-11T20:00:00",
      "updated_at": "2026-07-11T20:05:00",
      "finished_at": null,
      "blocked_reason": null
    }
  ]
}
```

字段说明：

- `goal_id`: 稳定唯一标识
- `title`: 用户输入目标
- `summary`: 系统摘要
- `status`: `draft | active | blocked | done`
- `current_task_id`: 当前正在推进的任务
- `root_task_ids`: 根任务节点
- `created_from`: 入口来源
- `blocked_reason`: 当前无 ready 任务时的原因

---

### 6.2 Task

继续复用 `.aios/tasks.json`，新增或强化这些字段：

- `goal_id`
- `parent_task_id`
- `depends_on_task_ids`
- `sequence_order`
- `status`
- `recommended_model`
- `fallback_models`
- `source_goal`

要求：

1. 所有通过 Goal 创建的任务必须绑定 `goal_id`
2. 旧任务没有 `goal_id` 时保持兼容
3. 任务树关系仍由 `parent_task_id + depends_on_task_ids` 表达

---

### 6.3 Execution

继续使用 `.aios/executions.json`，V1 不改主结构，只统一它与任务推进关系。

关键状态：

- `prepared`
- `running`
- `review_pending`
- `finished`
- `failed`

执行记录仍然作为任务推进的事实来源之一。

---

### 6.4 Project Progress Summary

新增项目级摘要对象，不一定单独落盘，也可以由聚合层实时计算：

```json
{
  "goal_id": "GOAL-20260711-001",
  "goal_title": "开发会员积分系统",
  "goal_status": "active",
  "current_task_id": "TASK-20260711-003",
  "current_task_title": "实现积分获取：会员积分系统",
  "next_action": "run_executor",
  "ready_count": 2,
  "blocked_count": 1,
  "done_count": 3,
  "total_count": 8,
  "progress_percent": 37.5,
  "last_progress_at": "2026-07-11T20:11:00"
}
```

---

## 7. 状态机设计

### 7.1 Goal 状态

- `draft`: 已创建但未激活
- `active`: 正在推进
- `blocked`: 当前无可推进任务或存在强阻塞
- `done`: 所有任务完成

状态迁移：

1. 创建 Goal 后进入 `active`
2. 若所有任务完成，则进入 `done`
3. 若没有 ready/running/review_pending 且仍有未完成任务，则进入 `blocked`
4. blocked 问题解除后回到 `active`

### 7.2 Task 状态

任务状态统一为：

- `todo`
- `running`
- `review_pending`
- `done`
- `blocked`（由调度摘要推导，不要求直接落库）

注意：

- `ready` 不强制作为落库状态，优先作为 scheduler 的推导态
- 当前仓库已经广泛使用 `todo/running/done`，V1 保持兼容

### 7.3 Execution 状态

复用现有 execution 状态，不新增状态机分支，只加强其与任务流转的关系。

---

## 8. 当前任务选择器

这是 V1 的核心编排器。

### 8.1 目标

在任意时刻，只选出一条“当前最该推进的任务”。

输出：

- `current_task_id`
- `current_task_title`
- `recommended_model`
- `next_action`
- `reason`

### 8.2 选择优先级

优先顺序：

1. `running` 的任务优先
2. `review_pending` 的任务优先
3. `ready` 任务中：
   - 依赖已满足
   - priority 高优先
   - 当前真实 ready 的模型优先
   - 更低成本可作为次级排序
   - 最后按创建顺序

### 8.3 ready 判定

任务成为 ready 的条件：

1. 任务状态不是 `done`
2. 不存在未完成依赖
3. 不是 `running`
4. 不是 `review_pending`
5. 推荐模型存在至少一个真实可执行候选
6. Context Pack 不存在强告警
7. 预算策略不阻塞

### 8.4 旧任务兼容

如果任务历史上写死了不可用推荐模型：

1. 通过 `route_task(task, root)` 重新得到有效推荐模型
2. scheduler 以有效推荐模型作为执行判定模型
3. 不要求立刻重写 `tasks.json`，但 UI 和调度应以“有效推荐模型”为准

---

## 9. 路由与模型策略

### 9.1 V1 原则

推荐模型不能只看理论优先级，必须看当前可执行性。

### 9.2 路由策略

对任务进行路由时：

1. 先取任务类型匹配模型
2. 再取学习排序
3. 再把当前 `runtime.ready = true` 的模型提升到前面
4. 若旧推荐模型不可用，允许自动切换到当前 ready 模型

### 9.3 V1 的最低要求

只要本机至少有一个模型当前可执行，AIOS 就不应该把整个任务链卡死在一个旧的不可用模型上。

---

## 10. 接口设计

---

### 10.1 Goal API

新增单项目接口：

- `GET /api/goals`
- `POST /api/goals`
- `GET /api/goals/:goal_id`
- `POST /api/goals/:goal_id/activate`
- `GET /api/goals/:goal_id/progress`

最小要求：

- 创建目标
- 查询目标
- 获取目标的当前任务和进度

---

### 10.2 项目推进 API

新增单项目接口：

- `GET /api/progress/current`

返回：

```json
{
  "goal": {},
  "current_task": {},
  "route": {},
  "execution": {},
  "next_action": "run_executor",
  "reason": "依赖已满足，推荐模型可执行。"
}
```

---

### 10.3 任务推进 API

新增：

- `POST /api/progress/advance`

作用：

1. 在任务完成回写后刷新 Goal 进度
2. 重新选择当前任务
3. 返回新的当前任务摘要

V1 中也可以在 `run finish` / `complete` 后内部自动调用，不一定暴露给用户。

---

### 10.4 Launcher API 增强

在现有 `/api/workbench` 或 `/api/projects` 摘要中增加：

- `current_goal_title`
- `current_goal_status`
- `current_task_title`
- `current_task_status`
- `next_action`
- `progress_percent`
- `last_progress_at`

---

## 11. 页面改造方案

### 11.1 单项目页改造

当前单项目页已有：

- 初始化
- 扫描
- 任务列表
- Context Pack / handoff
- 执行状态

V1 改造成“推进页”，增加三个核心区块：

#### A. 当前目标面板

显示：

- 当前目标标题
- 目标状态
- 目标完成度
- 当前阶段

#### B. 当前任务面板

显示：

- 当前任务标题
- 任务类型
- 推荐模型
- 下一步动作
- 推荐原因
- 执行入口

#### C. 任务树面板

以树状或分组列表显示：

- 已完成
- 进行中
- 待执行
- 被阻塞

不要求 V1 就做复杂树图，列表化即可。

### 11.2 Launcher 总控台改造

launcher 首页已经有总览、队列和监控摘要。V1 进一步强化项目卡：

新增字段：

- 当前目标
- 当前任务
- 当前阶段
- 完成度
- 最近推进时间

项目卡片从“项目状态摘要”升级为“项目推进摘要”。

---

## 12. 关键模块拆分

建议新增：

- `src/aios/core/goals.py`
- `src/aios/core/progress.py`

职责：

### `goals.py`

- `load_goals`
- `save_goals`
- `create_goal`
- `get_goal`
- `update_goal_status`

### `progress.py`

- `build_goal_progress`
- `select_current_task`
- `advance_goal_progress`
- `project_progress_summary`

现有模块协作：

- `tasks.py`: 任务生成与持久化
- `router.py`: 有效推荐模型
- `scheduler.py`: 任务执行判定
- `executions.py`: 执行事实
- `projects.py`: launcher 聚合
- `webapp.py`: 单项目接口
- `launcher.py`: 多项目摘要接口

---

## 13. 兼容策略

### 13.1 旧项目兼容

旧项目没有 `goals.json` 时：

- 视为无目标状态
- 不报错
- 用户第一次创建目标时再生成

### 13.2 旧任务兼容

旧任务无 `goal_id` 时：

- 保持可读可执行
- 不强制迁移
- Goal 视图仅显示新建目标绑定的任务

### 13.3 旧执行记录兼容

`executions.json` 无需迁移，只在推进层按现有结构读取。

---

## 14. 开发拆分建议

### 已实现：P1 Goal 数据层

1. 新增 `goals.py`
2. 落盘 `.aios/goals.json`
3. Goal 创建 / 查询 / 更新

### 已实现：P2 任务树绑定

1. `plan_goal` 输出绑定 `goal_id`
2. 任务树与 Goal 关联
3. 兼容旧任务

### 已实现：P3 当前任务选择器

1. 新增 `progress.py`
2. 计算 ready / current / blocked
3. 计算项目推进摘要

### 已实现：P4 单项目推进页

1. 当前目标面板
2. 当前任务面板
3. 任务树列表
4. 回写后自动刷新下一任务

### 已实现：P5 Launcher 项目推进摘要

1. 项目卡新增 goal/progress 字段
2. 工作台按项目推进视角展示

### 已实现：P6 回归与验收

1. Goal API
2. Progress API
3. 任务推进状态机
4. launcher 摘要
5. 端到端手工验收

---

## 15. 审核重点

进入开发前，建议重点 review 这 6 项：

1. Goal 是否需要支持并行多个 active
   V1 建议每项目只允许一个 active goal。

2. ready 是否作为落库状态
   V1 建议不落库，只作为推导态。

3. 当前任务选择器优先级是否合理
   当前实现为 `running(active) > review_pending > bridge_confirmation / failed > ready`。bridge 确认和失败被置于 ready 前，避免错误跳过需要人工处理的任务。

4. 旧任务如何兼容
   当前建议是不做强制迁移。

5. 推荐模型切换是否允许自动覆盖旧推荐
   当前建议允许在调度层覆盖“无效旧推荐”。

6. launcher 是否只展示，不直接推进
   当前建议 V1 只做展示 + 跳转，不直接承载完整执行详情。

---

## 16. 开发前结论

MVP V1 的关键，不是继续增加零散功能，而是让 AIOS 的默认主路径变成：

**目标 -> 任务树 -> 当前任务 -> 执行 -> 回写 -> 下一任务 -> 项目推进摘要**

只要这条链路走通，AIOS 才算真正从“工具集合”进入“业务推进系统”。

## 17. 实现清单

- `src/aios/core/goals.py`：Goal 读写、单活动目标约束、状态更新。
- `src/aios/core/progress.py`：当前任务选择、完成度计算、Goal 自动推进、项目摘要。
- `tasks.py`：Goal 任务写入 `goal_id` 和 `sequence_order`，保留既有父子和依赖关系。
- `executions.py`：开始与完成执行时刷新 Goal；完成后返回新的推进结果。
- `webapp.py`：提供 Goal 与 Progress API；单项目状态带推进摘要。
- 单项目 UI：新增「项目推进」面板，目标输入主路径改为直接创建 Goal 和任务树。
- Launcher：项目卡展示当前目标、当前任务、进度、下一步与推进时间。
- CLI：新增 `aios goal create|list|show|activate|advance`。
