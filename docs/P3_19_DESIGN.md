# P3-19 CC Switch 到执行器恢复桥接层设计

生成时间：2026-07-02

## 目标

把当前分散的 3 段动作收成一条受控桥接链路：

1. 导入 provider 配置；
2. 导入 prompt / handoff；
3. 在终端继续已挂接会话或最近会话。

这一步仍然不是“无人值守全自动编码”，但它解决了当前最明显的人工断点：

- `ccswitch` Deep Link 已能生成；
- 会话恢复命令已能生成；
- 终端也能自动打开；
- 但这三者此前还没有被同一个入口统一编排。

## 本期范围

- CLI：`aios ccswitch bridge TASK-ID`
- CLI：`aios ccswitch bridge TASK-ID --open`
- API：`POST /api/ccswitch/bridge`
- 单项目 Web UI：新增“一键桥接到 CC Switch 与终端”
- `.aios/ccswitch/*-bridge.json` 桥接包
- 执行记录补桥接留痕

## 能力边界

本期桥接层只做：

- 顺序打开 provider deeplink
- 顺序打开 prompt deeplink
- 调用本机终端继续执行命令

本期明确不做：

- 静默确认 `ccswitch` 导入是否成功
- 读取 `ccswitch` 当前 UI 状态
- 自动选择 `ccswitch` 里的历史会话
- 自动判断 provider 导入后的认证状态
- 自动控制 Codex / Claude Code 桌面窗口

原因很简单：这些动作没有稳定、公开、可审计的接口基础，直接强做会把系统变脆。

## 桥接包结构

新增：

`.aios/ccswitch/TASK-ID-EXECUTION-ID-模型名-bridge.json`

最小字段：

- `task_id`
- `task_title`
- `execution_id`
- `app`
- `model`
- `provider`
- `bridge_mode`
- `provider_deeplink`
- `prompt_deeplink`
- `resume_command`
- `session_ref`
- `session_handoff_path`
- `delay_ms`
- `terminal_app`
- `steps`
- `exported_at`

这个桥接包的用途不是给用户手工阅读，而是给后续自动化层提供稳定中间格式。

## CLI 设计

新增子命令：

```bash
aios ccswitch bridge TASK-ID
aios ccswitch bridge TASK-ID --open
aios ccswitch bridge TASK-ID --latest-session
```

参数：

- `--app`
- `--model`
- `--latest-session`
- `--open`
- `--stdout`
- `--terminal-app`
- `--delay-ms`

行为：

- 默认只导出桥接包，不触发本机动作；
- `--open` 时按顺序打开 provider、prompt、终端恢复；
- `--latest-session` 时改用 continue-latest，而不是 attached session。

## API / Web 设计

新增接口：

- `POST /api/ccswitch/bridge`

请求最小字段：

- `task_id`
- `app`
- `latest`
- `open`
- `terminal_app`
- `delay_ms`

Web UI 新增一个主操作按钮：

- `一键桥接到 CC Switch 与终端`

这个按钮的实际行为是：

1. 生成或复用 provider deeplink
2. 生成或复用 prompt deeplink
3. 生成或复用 resume command
4. 按顺序触发打开动作
5. 回写桥接包路径和执行留痕

## 执行记录新增留痕

执行记录新增：

- `ccswitch_bridge_path`
- `ccswitch_bridge_app`
- `ccswitch_bridge_mode`
- `ccswitch_bridge_terminal_app`
- `ccswitch_bridge_generated_at`
- `ccswitch_bridge_opened_at`

这样后续就能区分：

- 只是导出了 provider / prompt
- 还是已经实际发起过桥接执行

## 与其他系统借鉴点的关系

这一版借鉴的是“把执行链拆成可追踪步骤再编排”，而不是直接照搬完整代理平台。

参考方向：

- OpenHands：运行时把浏览器、终端、编辑动作放进统一代理循环
- SWE-agent：把计划、编辑、验证、提交固定成受控步骤
- aider：把仓库映射、验证、Git 收口做成默认工程流程

AIOS 对应的落地方式是：

- 不直接引入完整 agent runtime
- 先把 `ccswitch -> resume` 做成最小桥接步骤
- 每一步都保留中间产物和执行留痕

## 风险与降级

风险：

1. `ccswitch` Deep Link 被系统成功打开，但导入结果无法自动确认
2. provider 导入和 prompt 导入之间需要一点时间，过短可能失败
3. 终端恢复已经启动，但执行器内部是否恢复到预期上下文仍取决于执行器自身

降级策略：

- 任一步失败，都仍然保留 bridge JSON；
- 用户可以回退到：
  - 单独复制 Provider Deep Link
  - 单独复制 Prompt Deep Link
  - 单独执行 `run resume --open-terminal`

## 测试方案

自动化测试：

1. CLI `ccswitch bridge --open`
   - mock deeplink 打开
   - mock terminal 打开
   - 校验 bridge JSON 和 execution 审计字段

2. API `POST /api/ccswitch/bridge`
   - 校验返回 bundle
   - 校验执行记录里的 bridge 字段

3. 兼容性
   - 原 `ccswitch export/provider/session` 不回归
   - 原 `run resume --open-terminal` 不回归

人工验收：

1. 选择一个已开始执行且已挂接 session 的任务
2. 点击“一键桥接到 CC Switch 与终端”
3. `ccswitch` 依次收到 provider / prompt 导入
4. Terminal 自动打开恢复命令
5. 回到 AIOS 能看到 bridge 留痕
