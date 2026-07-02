# P3-23 Bridge 恢复信号设计

生成时间：2026-07-02

## 目标

在 `P3-22 bridge 确认安全门` 之后，再补一层更强的自动证据：

- 当 bridge 的最后一步真正把终端恢复命令发出去时；
- AIOS 自动写入一个本地 signal 文件；
- Web/API 能自动看到“终端恢复已启动”。

这不是 `ccswitch` 内部状态读取，但它比纯人工确认更强，因为它能自动证明 bridge 至少走到了终端恢复这一步。

## 本期范围

- bridge JSON 新增 `resume_signal_path`
- 终端恢复命令增加 signal wrapper
- API 读取任务详情时自动合并 signal 状态
- 单项目页显示 bridge 恢复信号状态

## 设计

bridge 终端步骤不再直接执行原始恢复命令，而是执行：

1. 写入 `.aios/ccswitch/*-resume-signal.json`
2. 再执行原始恢复命令

signal 内容最小字段：

- `task_id`
- `execution_id`
- `model`
- `bridge_mode`
- `started_at`

## 价值

这层能力让 AIOS 可以自动知道：

- deeplink 打开动作是否已经走到终端恢复阶段
- 终端恢复命令是否至少已被触发

虽然仍然不能证明 `ccswitch` 内部状态完全正确，但它已经是一个真实的自动证据点。

## 限制

- 只能证明“恢复命令已启动”
- 不能证明恢复到的就是正确会话
- 不能证明 `ccswitch` provider / prompt 导入已被正确应用

所以它是 bridge 确认的辅助证据，不替代 bridge 的最终确认状态。

## 测试方案

1. wrapper 命令本地执行后写出 signal 文件
2. Web API 读取任务详情时自动带出 signal 状态
