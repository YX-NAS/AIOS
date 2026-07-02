# P3-16 执行器会话留痕与恢复入口设计

生成时间：2026-07-02

## 目标

把 AIOS 从“只知道执行过一次命令”推进到“知道应该如何继续这个执行会话”。

这一阶段不尝试自动点击桌面，也不假设所有执行器都能直接返回 session id。先补一层稳定且可审计的能力：

- 执行器是否支持恢复会话
- 会话引用如何记录到任务执行记录里
- AIOS 如何为当前任务生成恢复命令和继续最近会话命令

## 背景

当前 AIOS 已经有：

- 任务执行记录
- Provider / Prompt / Session Handoff
- CLI 执行器调度

但还缺一个关键环节：

- 一旦用户或外部执行器切到了某个真实会话，AIOS 并不知道该如何继续它

这会导致“执行中枢”断在会话层。借鉴其他系统的会话管理能力，这一版先做任务级会话挂接和恢复命令生成。

## 范围

本阶段实现：

- 执行器库新增会话恢复元数据：
  - `resume_args`
  - `continue_args`
  - `resume_in_project_root`
  - `session_ref_label`
- 默认内置执行器补恢复模板：
  - `codex-cli`
  - `claude-code-cli`
- CLI：
  - `aios run attach TASK-ID`
  - `aios run resume TASK-ID`
- Web API：
  - `POST /api/run/attach`
  - `POST /api/run/resume`
- 单项目 Web UI：
  - 挂接当前会话
  - 复制恢复命令
  - 复制最近会话继续命令
- 执行记录新增会话字段

本阶段不实现：

- 自动探测 CLI 输出里的 session id
- 自动打开终端执行恢复命令
- 自动恢复指定桌面端会话
- 调度器自动决定何时 resume 而不是 fresh run

## 数据结构

### 执行器配置

新增字段：

- `resume_args`：恢复指定会话的参数模板
- `continue_args`：继续最近会话的参数模板
- `resume_in_project_root`：生成恢复命令时是否包一层 `cd <project_root> && ...`
- `session_ref_label`：显示给人的字段名，例如 `session_id`

### 执行记录

新增字段：

- `executor_resume_supported`
- `executor_session_id`
- `executor_session_name`
- `executor_session_note`
- `executor_session_attached_at`
- `executor_session_ref_label`
- `executor_resume_command`
- `executor_continue_command`
- `executor_resume_last_command`
- `executor_resume_last_mode`
- `executor_resume_generated_at`

## 交互设计

### CLI

挂接当前会话：

```bash
aios run attach TASK-ID --executor codex-cli --session-id session-123
```

生成恢复命令：

```bash
aios run resume TASK-ID
aios run resume TASK-ID --latest-session
```

说明：

- 默认优先用已经挂接的 session id / session name
- `--latest-session` 强制使用执行器的“继续最近会话”命令

### Web UI

任务检查器新增：

- 一个“挂接当前会话”表单
- 一个“复制恢复命令”按钮
- 一个“复制最近会话继续命令”按钮

### 审计策略

生成恢复命令时，会把本次生成结果回写到执行记录中，保证 AIOS 能追踪：

- 最近一次生成的是哪种恢复模式
- 生成时间是什么
- 用的具体命令是什么

## 为什么这一步有价值

这是从“任务管理系统”走向“执行中枢”的关键一步。

如果 AIOS 不掌握会话恢复入口，就只能不断重复：

- 重新开新会话
- 重新导上下文
- 重新解释当前进度

补上这一层后，AIOS 至少可以做到：

1. 知道某条任务在什么执行器里继续
2. 知道恢复这条任务最短的命令是什么
3. 为后续真正的自动恢复保留稳定数据结构

## 测试计划

### 自动化测试

1. 默认执行器库
- `codex-cli` 带 `resume` / `continue` 模板
- `claude-code-cli` 带 `resume` / `continue` 模板

2. CLI
- 手动执行后可挂接 session id
- `run resume` 能生成 attached 模式命令
- `run resume --latest-session` 能生成 latest 模式命令

3. API
- `/api/run/attach` 正常写回执行记录
- `/api/run/resume` 返回命令文本和模式

4. 兼容性
- 旧执行记录缺少这些字段时不报错
- 旧执行器库缺少这些字段时自动补默认值

### 手工验收

1. 准备一条任务执行记录
2. 挂接一个 Codex 或 Claude CLI 会话引用
3. 在单项目页复制恢复命令
4. 在单项目页复制最近会话继续命令
5. 确认执行状态卡中能看到恢复命令留痕

## 后续衔接

P3-16 完成后，真正接近“全自动执行”的下一步是：

- 自动提取或识别 session id
- 自动打开终端恢复会话
- 自动判定某任务该继续旧会话还是开新会话

也就是说，这一版先把“可恢复的会话入口”固定下来，再继续往自动恢复推进。
