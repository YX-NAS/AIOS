# P3-3 执行器适配层设计

生成时间：2026-07-02

## 目标

把 AIOS 从“只能生成执行材料”推进到“可以受控调起 CLI 执行器”的阶段，为后续全自动化执行打基础。

这一阶段先解决两个问题：

1. AIOS 能否统一调起不同执行器；
2. 执行过程和结果能否被结构化记录并回收到任务流程中。

## 范围

本阶段实现：

- 全局执行器库 `executors.json`
- 内置 `manual` / `codex-cli` / `claude-code-cli` 执行器模板
- `aios executor` 管理命令
- `aios run TASK-ID --executor EXECUTOR-ID` 自动执行原型
- 执行日志落盘
- 执行结果回写到 `.aios/executions.json`
- 单项目 Web API 暴露执行器列表与自动执行入口

本阶段不实现：

- 自动切换 `ccswitch`
- 自动恢复桌面会话
- 自动判定任务完成并直接写 `done`
- 自动 Git 提交
- launcher 中完整执行器配置界面

## 数据结构

新增全局文件：

- `~/.aios-local/executors.json`

最小字段：

- `id`
- `label`
- `kind`: `manual | command`
- `enabled`
- `rank`
- `binary`
- `args`
- `timeout_seconds`
- `pass_model_as_flag`
- `env`

## 执行状态模型

执行记录新增字段：

- `executor_id`
- `executor_label`
- `executor_command`
- `executor_exit_code`
- `executor_log_path`
- `executor_stdout_excerpt`
- `executor_stderr_excerpt`

执行记录状态约定：

- `prepared`：已准备但未启动
- `running`：执行器正在运行或人工执行中
- `review_pending`：CLI 执行器已退出成功，但任务还未人工验收
- `finished`：已人工确认完成并完成回写
- `failed`：执行器退出失败或超时

任务状态本阶段仍保持：

- `todo`
- `running`
- `done`

自动执行成功后，任务先保持 `running`，待人工 review 后再用 `aios run finish` 收口为 `done`。

## CLI 入口

### 执行器管理

```bash
aios executor list
aios executor show codex-cli
aios executor create mock-cli --binary python3 --arg=-c --arg="print('ok')" --arg="{prompt}"
aios executor update mock-cli --binary python3 --arg=-c --arg="print('ok')" --arg="{prompt}"
aios executor delete mock-cli
aios executor reset
```

### 自动执行

```bash
aios run TASK-ID --executor codex-cli
aios run TASK-ID --executor claude-code-cli
aios run status TASK-ID
aios run finish TASK-ID --summary "..."
```

行为约定：

1. `aios run TASK-ID --executor ...`
   - 生成或复用 Pack / handoff
   - 创建执行记录
   - 调起目标 CLI
   - 记录命令、退出码、stdout/stderr 摘要和日志文件
   - 成功则写 `review_pending`
   - 失败则写 `failed`

2. `aios run finish TASK-ID --summary "..."`
   - 用于人工审核通过后正式完成任务
   - 继续复用现有回写逻辑更新 `tasks.json`、`changelog.md`、`memory.md`

## Web API

新增接口：

- `GET /api/executors`
- `POST /api/run/execute`

返回原则：

- 自动执行接口返回当前执行记录、handoff、route、executor
- 执行失败也返回 201 + `execution.status = failed`，由前端明确展示失败状态

## 设计决策

### 1. 为什么先做 CLI-first

因为桌面 GUI 自动化不稳定，而官方 CLI 更适合作为可编排执行器。

### 2. 为什么自动执行成功后不直接把任务标成 `done`

因为当前阶段还没有自动测试判定和自动验收能力。  
先把“执行完成”和“任务验收通过”拆开，风险更可控。

### 3. 为什么要保留 `manual`

因为任何自动执行都必须可回退到当前半自动方案，避免外部 CLI 不可用时整条链路断掉。

## 测试计划

### 自动化测试

1. 执行器库管理
- 默认执行器可列出
- 自定义执行器可创建、更新、删除、重置

2. CLI 自动执行
- 自定义 mock executor 成功执行后，状态为 `review_pending`
- 退出码、日志路径、命令预览写入 execution record

3. Web API 自动执行
- `POST /api/run/execute` 成功返回执行记录
- 失败执行器返回 `failed` 状态和退出码

4. 兼容性
- `aios run --manual` 不回归
- `aios run finish` 仍能完成人工和自动执行后的任务

### 手工验收

1. `aios executor list`
2. 选择一个项目并创建任务
3. 用 `aios run TASK-ID --executor ...` 启动一次自动执行
4. 查看 `.aios/logs/EXEC-*.log`
5. 查看 `aios run status TASK-ID`
6. 人工 review 后执行 `aios run finish`
7. 确认任务变为 `done`

## 下一步

P3-3 完成后，下一步应接：

- P3-4：任务树与拆解草案
- P3-5：Context Engine 补强
- P3-6：执行总览增强

这样才能把自动执行从“能跑”推进到“能稳定调度和验收”。
