# P3-18 终端继续执行设计

生成时间：2026-07-02

## 目标

把当前“生成恢复命令 -> 手动复制 -> 手动打开终端 -> 手动粘贴”的链路收敛为：

1. AIOS 识别任务对应执行会话；
2. AIOS 生成恢复命令；
3. AIOS 直接在本机终端打开该命令；
4. 操作者只处理真正的代码执行与审核。

这不是全自动编码，但它补上了当前半自动执行层最明显的一段人工摩擦。

## 本期范围

- CLI：`aios run resume TASK-ID --open-terminal`
- CLI：`aios run resume TASK-ID --latest-session --open-terminal`
- Web API：`POST /api/run/resume` 新增 `open_terminal`
- 单项目 Web UI：
  - `在终端继续当前会话`
  - `在终端继续最近会话`
- 执行记录增加最近一次终端拉起审计字段

## 平台边界

V1 只支持 macOS `Terminal.app`。

原因：

- 当前用户环境是 macOS；
- `Terminal.app + osascript` 是现阶段最稳定、最小依赖的本地接管方式；
- 不引入桌面自动点击，不依赖 `ccswitch` 私有接口，不需要额外安装工具。

降级策略：

- 非 macOS：返回明确错误，继续使用“复制恢复命令”路径；
- 非 `Terminal.app`：当前不支持，避免把多终端适配做成新的不稳定面；
- 会话缺失：继续沿用已有 attach / continue-latest 校验逻辑。

## 数据结构

在 `.aios/executions.json` 的执行记录中新增：

- `executor_terminal_launch_supported`
- `executor_terminal_launch_status`
- `executor_terminal_launch_app`
- `executor_terminal_launch_command`
- `executor_terminal_launch_mode`
- `executor_terminal_launch_at`

用途：

- 审计是否已经从 AIOS 发起过终端继续；
- 区分“只是生成了恢复命令”和“已经触发终端继续”；
- 为后续更高自动化等级提供基础状态。

## CLI 设计

新增参数：

- `--open-terminal`
- `--terminal-app Terminal`

行为：

- 不带 `--open-terminal`：保持原行为，只输出恢复命令；
- 带 `--open-terminal`：先生成恢复命令，再调用终端拉起，并回写执行记录；
- `--latest-session` 仍然有效，用于 continue-latest 模式。

## API / Web 设计

沿用现有 `/api/run/resume`，不新增重复路由：

- `open_terminal: true`
- `terminal_app: "Terminal"`

返回结果中补充：

- `terminal.opened`
- `terminal.app`
- `terminal.command`

Web UI 继续保留“复制恢复命令”和“复制最近会话继续命令”，同时新增两个直接打开终端的按钮，保证：

- 稳定场景下可一键继续；
- 出现平台限制或用户想手动处理时，仍有低耦合退路。

## 与全自动化路线的关系

P3-18 不是最终形态，但它是通往全自动执行的必要一层。

它解决的是：

- 会话恢复入口已经可计算，但执行触发还没被系统接管；
- `ccswitch` 与执行器之间仍然靠人工中转；
- 现有自动化更多停在“生成信息”，还没有真正发出本机继续动作。

下一步可以在此基础上继续推进：

1. 扩展更多终端适配；
2. 结合 `ccswitch` / 会话 handoff 做更短链路恢复；
3. 最终把“任务派发 -> 切换模型 -> 恢复会话 -> 执行命令”接成完整自动化。

## 测试方案

自动化测试：

1. CLI `run resume --open-terminal`
   - 伪造 macOS 环境
   - mock `osascript`
   - 校验执行记录写入成功

2. API `POST /api/run/resume` with `open_terminal=true`
   - 校验返回结构包含 `terminal`
   - 校验执行记录中的终端拉起字段

3. 兼容性
   - 不带 `--open-terminal` 的旧用法保持不变
   - attach / resume / continue-latest 的旧测试继续通过

人工验收：

1. 选择已挂接或已自动识别 session 的任务
2. 点击 `在终端继续当前会话`
3. macOS Terminal 自动打开并执行恢复命令
4. 返回 AIOS 后能看到终端继续状态和时间
