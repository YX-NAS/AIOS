# AIOS MVP V1 测试方案与验收计划

> 执行状态：已实现并执行自动化验收（v0.42.0，2026-07-11）。新增 `tests/test_mvp_v1_progress.py` 覆盖 Goal 创建、任务树绑定、当前任务优先级、完成后的自动推进、单项目 API 和 Launcher 摘要字段。

## 1. 测试目标

验证 AIOS MVP V1 是否真正形成业务主链，而不是只具备分散功能。

验收的核心不是：

- 页面能打开
- 接口有返回
- 任务能创建

而是：

**一个项目目标能否在系统内持续推进，直到完成并回到总控台。**

---

## 2. 测试范围

覆盖模块：

1. Goal 数据层
2. Goal 与任务树绑定
3. 当前任务选择器
4. 单项目推进页
5. 执行回写
6. 自动切换下一任务
7. launcher 项目推进摘要
8. 推荐模型与运行时可执行能力联动

不覆盖：

1. `ccswitch` 自动切换
2. 全自动编码执行
3. 自动 commit / push / PR
4. 多目标并行调度

---

## 3. 测试策略

采用三层测试：

### A. 单元测试

验证纯逻辑：

- Goal 创建
- 状态迁移
- 当前任务选择
- ready 判定
- 任务依赖关系
- 推荐模型切换

### B. 集成测试

验证模块协作：

- Goal -> task plan -> scheduler -> execution -> progress
- Web API 返回是否正确
- launcher 聚合是否正确

### C. 手工端到端验收

验证真实用户链路：

- 进入项目
- 输入目标
- 生成任务树
- 执行一条任务
- 回写
- 自动切到下一条
- launcher 展示进度

---

## 4. 自动化测试设计

---

### 4.1 Goal 数据层测试

#### 用例 1：创建目标

输入：

- 新项目
- 一个目标标题

预期：

- 生成 `.aios/goals.json`
- 生成唯一 `goal_id`
- 状态为 `active`
- `current_task_id` 初始为空或待生成

#### 用例 2：读取目标

预期：

- 能读取已创建 Goal
- 不存在 Goal 时返回空列表，不报错

#### 用例 3：更新目标状态

预期：

- `active -> blocked`
- `blocked -> active`
- `active -> done`

状态更新有持久化结果。

---

### 4.2 Goal 与任务树绑定测试

#### 用例 4：基于目标创建任务树

输入：

- `goal = 开发会员积分系统`

预期：

- 生成多条任务
- 每条任务带 `goal_id`
- 根任务与子任务关系正确
- `depends_on_task_ids` 正确写入

#### 用例 5：旧任务兼容

输入：

- 已有无 `goal_id` 的历史任务

预期：

- 系统不报错
- Goal 视图仍可工作
- 历史任务仍可显示和执行

---

### 4.3 当前任务选择器测试

#### 用例 6：优先选择 running

预期：

- 当存在 `running` 任务时
- `current_task_id` 应该就是该任务

#### 用例 7：优先选择 review_pending

预期：

- 没有 running，但有 `review_pending`
- 当前任务应切到待验收任务

#### 用例 8：选择 ready 任务

预期：

- 没有 running/review_pending 时
- 从 ready 任务中按优先级选择

#### 用例 9：依赖未满足不进入 ready

预期：

- 有依赖未完成的任务不能成为当前任务

#### 用例 10：目标无 ready 任务进入 blocked

预期：

- 仍有未完成任务
- 但没有 ready/running/review_pending
- Goal 状态应变成 `blocked`

---

### 4.4 推荐模型与可执行性联动测试

#### 用例 11：ready 模型优先

输入：

- 旧推荐模型不可用
- fallback 模型 ready

预期：

- route 结果切到 ready 模型

#### 用例 12：scheduler 使用有效推荐模型

预期：

- scheduler 不再被历史旧推荐卡死
- `recommended_model` 使用有效模型

#### 用例 13：证书链兜底

输入：

- Python 默认 SSL 链异常
- `certifi` 可用

预期：

- provider probe 使用 `certifi` 证书链
- 不再因为本机默认 OpenSSL 证书问题误判 provider down

---

### 4.5 执行回写测试

#### 用例 14：任务执行完成回写

输入：

- 一条 ready 任务
- 完成 summary / test result

预期：

- execution 状态进入 `finished`
- task 状态进入 `done`
- Goal 进度刷新

#### 用例 15：回写后自动选择下一任务

预期：

- 当前任务完成后
- 系统重新计算并选出新的 `current_task_id`

#### 用例 16：所有任务完成后 Goal done

预期：

- 全部任务 `done`
- Goal 状态自动进入 `done`

---

### 4.6 单项目 API 测试

#### 用例 17：Goal API

验证：

- `POST /api/goals`
- `GET /api/goals`
- `GET /api/goals/:goal_id`

#### 用例 18：Progress API

验证：

- `GET /api/progress/current`
- `POST /api/progress/advance`

返回必须带：

- 当前 Goal
- 当前任务
- 推荐模型
- 下一步动作
- 原因

---

### 4.7 Launcher 聚合测试

#### 用例 19：项目推进摘要显示

验证：

- `current_goal_title`
- `current_task_title`
- `progress_percent`
- `next_action`
- `last_progress_at`

#### 用例 20：多项目互不串扰

验证：

- 项目 A/B 各自有独立 Goal
- launcher 聚合正确
- `.aios/` 数据不混淆

---

## 5. 手工验收方案

这是 V1 是否算“转起来”的最终判断依据。

### 5.1 v0.42.0 自动化验收记录

已在本地完成以下分组回归：

- `41 passed`：CLI、Web UI、Launcher、MVP Progress、模型持久化和错误处理。
- `35 passed`：P1 / P2 功能、Git diff、路由学习、评分和 token 估算。
- `78 passed`：P3 执行层、调度器和 CC Switch Deep Link Base64 编码。
- `16 passed`：P4 自动切换、自动 pipeline 和完整 pipeline。

同时通过 `python3 -m compileall -q src`、两份前端脚本的 `node --check` 和 `git diff --check`。本机当前没有可连接的浏览器自动化实例，因此页面视觉验收由 Web API、静态页面标识断言和 JavaScript 语法检查替代；真实浏览器打开后的人工检查仍建议执行一次。

---

### 场景 1：从目标到任务树

步骤：

1. 启动单项目工作区
2. 输入目标：`开发会员积分系统`
3. 提交目标

预期：

- Goal 创建成功
- 自动生成任务树
- 页面显示当前目标与当前任务

---

### 场景 2：完成一条任务并自动切下一条

步骤：

1. 进入当前任务
2. 生成 Pack / handoff
3. 完成任务并回写结果

预期：

- 当前任务状态变为 `done`
- 新的当前任务自动出现
- Goal 进度变化

---

### 场景 3：阻塞场景

步骤：

1. 制造依赖未满足或 provider 不可执行
2. 刷新项目推进页

预期：

- Goal 或任务显示 blocked
- 页面能明确显示阻塞原因
- launcher 项目卡同步显示阻塞状态

---

### 场景 4：launcher 回显

步骤：

1. 启动 launcher
2. 进入项目 A
3. 创建目标并推进一条任务
4. 回到 launcher

预期：

- 项目卡显示当前目标
- 显示当前任务
- 显示完成度
- 显示最近推进时间

---

### 场景 5：目标完成

步骤：

1. 将一个 Goal 下的所有任务依次完成

预期：

- Goal 状态自动变为 `done`
- 当前任务清空
- launcher 项目卡显示目标完成

---

## 6. 验收通过标准

只有同时满足以下条件，V1 才算通过：

1. 能创建 Goal
2. Goal 能生成任务树
3. 系统能稳定选出当前任务
4. 任务完成后能自动切到下一任务
5. 所有任务完成后 Goal 进入 `done`
6. launcher 能正确显示项目推进状态
7. 旧任务/旧项目兼容
8. 推荐模型与真实可执行能力一致

---

## 7. 回归重点

V1 开发完成后，必须重点回归现有能力：

1. `task create`
2. `task plan`
3. `route`
4. `pack`
5. `run --manual`
6. `run finish`
7. scheduler 摘要
8. launcher 项目摘要
9. model doctor / model probe

原因：

V1 会碰到 Goal、task、route、scheduler、launcher 多个中间层，回归范围不能只盯 Goal 新功能。

---

## 8. 测试执行顺序建议

建议按以下顺序执行：

1. 单元测试：Goal / Progress / Route / Scheduler
2. API 测试：Web + Launcher
3. 集成测试：任务推进链
4. 手工端到端验收
5. 多项目回归

---

## 9. 风险与测试注意事项

### 9.1 历史缓存污染

模型握手缓存会影响 ready 判定，测试必须隔离 `AIOS_STATE_DIR`。

### 9.2 旧任务状态影响当前任务选择

测试必须显式设置任务状态，避免历史默认值干扰。

### 9.3 provider 探测不应依赖真实公网

自动化测试应继续 mock `urlopen`，只在手工验收中验证真实链路。

### 9.4 UI 验收不能只看 HTML 文本

需要验证：

- 当前目标是否更新
- 当前任务是否切换
- launcher 项目卡是否同步变化

---

## 10. 结论

MVP V1 的测试成败，不取决于页面是否更好看，也不取决于多了多少状态字段，而取决于一条链是否跑通：

**目标创建 -> 任务树生成 -> 当前任务确定 -> 执行回写 -> 下一任务推进 -> launcher 回显**

这条链路打通，AIOS 才算真正进入“业务主链 MVP”。
