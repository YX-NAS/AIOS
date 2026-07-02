# P3-17 执行会话自动识别设计

生成时间：2026-07-02

## 目标

把 AIOS 从“会话要人工挂接”推进到“执行器跑完后，能自动从输出里提取会话引用并回写执行记录”。

这是全自动执行链路里一个很现实的缺口。只要这一层不补，用户仍然要手工去复制 session id，再回到 AIOS 里挂接。

## 范围

本阶段实现：

- 执行器新增 `session_capture_patterns`
- `run ... --executor ...` 执行完成后自动扫描 stdout / stderr
- 如果命中会话引用：
  - 自动写入 `executor_session_id` / `executor_session_name`
  - 自动生成 `executor_resume_command`
  - 自动生成 `executor_continue_command`
  - 标记 `executor_session_auto_captured = true`
- CLI / Web UI 状态卡显示会话来源

本阶段不实现：

- 自动打开恢复命令
- 自动拉起终端
- 自动从桌面 UI 读取会话
- 自动决定恢复哪个历史 session

## 数据设计

### 执行器配置

新增字段：

- `session_capture_patterns`

每一项结构：

- `pattern`
- `source`: `stdout | stderr | combined`

命名捕获约定：

- `(?P<session_id>...)`
- `(?P<session_name>...)`

### 执行记录

新增或补强字段：

- `executor_session_auto_captured`
- `executor_session_capture_source`
- `executor_session_capture_pattern`

## 默认策略

### Codex

默认尝试：

1. 带 `session id:` 前缀的输出
2. UUID 兜底

### Claude Code

默认尝试：

1. 带 `session id:` 前缀的输出
2. 输出中出现 `--resume <id>` 的提示

这些都是启发式规则，不保证所有版本都成立，但足够构成首版自动识别层。

## 交互设计

用户不需要新增动作。

当执行器跑完后，如果输出里有可识别会话引用，AIOS 自动完成：

1. 识别会话
2. 回写执行记录
3. 在状态卡显示恢复命令

若未识别到，会保持原有手动挂接路径。

## 测试计划

### 自动化测试

1. Mock 执行器输出 session id
- CLI 执行后自动写入 `executor_session_id`
- 自动写入 `executor_session_auto_captured`
- 自动生成 resume command

2. API 执行
- `/api/run/execute` 返回的执行记录带自动提取的 session

3. 兼容性
- 没有 capture pattern 的执行器不报错
- 没有命中 pattern 的执行器不报错

## 风险

主要风险不是实现复杂，而是误识别。

因此本阶段选择：

- 只做正向匹配
- 只在命中明确 regex 时回写
- 保留手动挂接覆盖路径

## 后续衔接

P3-17 完成后，下一步可以继续做：

1. 运行后自动打开 resume 命令
2. 调度器判断本次该继续旧会话还是新建会话
3. 针对不同执行器补更准确的 session 提取规则
