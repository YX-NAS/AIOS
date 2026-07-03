# P4 全自动调度闭环设计方案

版本：v0.39 (draft) | 生成时间：2026-07-03

## 当前状态（P3-33 到 P3-35 完成后）

v0.38 已完成的能力：

| 层级 | 能力 | 成熟度 |
|------|------|--------|
| 执行准备 | 任务拆解（三种策略）、模型路由推荐、Context Pack 生成、handoff 生成 | 稳定 |
| 手动执行 | `aios run --manual` → Pack + 交接单 + 执行记录 | 稳定 |
| 半自动调度 | `aios run auto` → 自动派发下一个 ready 任务 | 稳定 |
| 执行器适配 | `aios run TASK-ID --executor codex-cli` → 调起外部 CLI | 稳定 |
| 自动完成 | 验证命令通过后自动 finish（--auto-finish） | 稳定 |
| 自动 Git 提交 | 工作区干净时 finish 自动提交（--auto-commit） | 稳定 |
| 自动 Push | finish 后自动 push 特性分支（--auto-push） | 稳定 |
| 自动 PR | push 成功自动创建 Draft PR（--auto-pr） | 稳定 |
| Session 挂接 | `attach` / `resume` / `sessions` → 会话恢复入口 | 稳定 |
| 终端续接 | macOS Terminal 一键继续（--open-terminal） | 稳定 |
| ccswitch bridge | provider → prompt → resume 顺序桥接 | 稳定 |
| bridge 确认 | 状态回写、恢复 signal 检测、自动确认能力 | 稳定 |
| bridge 安全门 | 调度阻塞在 bridge 未确认时 | 已修复 |
| 验证 fallback 重试 | 验证失败后自动用 fallback 模型重试 | 稳定 |
| 失败分类 | execution/verification 失败归类 | 稳定 |
| Provider 就绪探测 | auth env、握手、API 权限检测 | 稳定 |
| 差异化自动恢复 | 按失败类型决定恢复策略 | 稳定 |
| 多轮自动恢复 | 恢复次数上限 + 冷却护栏 | 稳定 |
| 预算策略 | 项目级总预算 + cheapest_first 派发 | 稳定 |
| 成本统计 | 模型定价 + Token 估算 + 运行耗时 | 稳定 |
| 仓库上下文检索 | repo map + repo search + 有界文件搜索 | 稳定 |
| 执行安全护栏 | guard status + heartbeat + doom-loop 检测 | 稳定 |
| 跨模型审查 | review create/complete 工作流 | 稳定 |

## P4 目标

**打通"从目标到 PR"的受控全自动闭环**，补上两个关键缺口：

1. **ccswitch 自动切换**（P4-0）：不再人工切换模型
2. **Codex/Claude Code 自动调用**（P4-1）：不再人工粘贴 Pack

## ccswitch 自动切换（P4-0）

### 现状

- ccswitch 已有 Deep Link 导入 API（`ccswitch://v1/import`）
- AIOS 已能生成 prompt/provider/session 三种 Deep Link
- bridge 已能按 provider → prompt → resume 顺序编排
- AIOS 已能检测 bridge 恢复 signal、自动确认 bridge 就绪
- AIOS 没有直接读取 ccswitch 内部状态的能力

### 技术方案

#### 方案 A：完全依赖 ccswitch Deep Link API（推荐）

利用 ccswitch 的 `ccswitch://v1/import` Deep Link API 实现自动化：

1. 执行准备：AIOS 为任务生成 provider Deep Link + prompt Deep Link
2. 自动打开 Deep Link：AIOS 使用 `open` 命令打开 provider/prompt Deep Link
3. 等待导入完成：AIOS 轮询检查 ccswitch 是否切换完成
4. 自动启动执行器：ccswitch 就绪后自动调起 Codex CLI

**可行性评估：**
- ccswitch 的 Deep Link API 已公开稳定，方案可行性高
- 需要确认 ccswitch 导入是否有间隔限制、是否有并发限制
- 需要确认 Deep Link 导入后 Session 是否能被外部 CLI 识别

**风险：**
- Deep Link 导入延迟不确定
- 并发导入时 ccswitch 行为未知
- 不同版本的 ccswitch 行为可能不一致

#### 方案 B：Computer Use + Accessibility（备选）

使用 Computer Use 控制桌面 App UI：

1. 截取 ccswitch 界面截图
2. 通过 Accessibility Tree 定位控件
3. 自动点击切换模型
4. 确认切换完成

**风险：**
- 可靠性和维护成本高
- 依赖特定 macOS 版本
- 不同 ccswitch 版本界面差异

### 推荐：并行方案

- P4-0 采用方案 A 作为主路径
- 方案 B 仅作为 fallback，在 Deep Link 无法稳定工作时启用
- 先验证 Deep Link 通路的稳定性和延迟

## Codex / Claude Code 自动调用（P4-1）

### 现状

- 执行器适配层已落地，可用 `aios run TASK-ID --executor codex-cli` 调起 CLI
- Context Pack 已生成 Markdown/文本格式，可直接注入
- Session 恢复命令已生成

### 技术方案

**主路径：CLI 模式绕过 ccswitch bridge**

当前代码已实现了一个关键的优化：**CLI 模式下 `ccswitch bridge` 对调度器透明**。

```python
# scheduler.py
is_cli_mode = bool(execution and execution.get("mode") == "cli")
if is_cli_mode and bridge_confirmation_status in ("pending_confirmation", "signal_detected"):
    # CLI executors bypass ccswitch — model is passed via --model flag.
    scheduler_state = "ready"
    next_action = "run_executor"
```

这意味着：
- 用 `aios run TASK-ID --executor codex-cli --model gpt-5.5` 启动，CLI 接管模型选择
- 不需要 ccswitch 切换，因为模型已由命令行参数指定
- 不需要 Session Handoff，因为每轮执行都有完整 Context Pack

**核心改进方向：**

1. 与 Codex CLI 做 model 参数桥接
2. 确保 Context Pack 以文件或标准输入传给 CLI
3. 执行后自动提取结果并进行质量检查

**可行性评估：**
- Codex CLI 已支持 `--model` 参数（通过环境变量或参数指定）
- Claude Code CLI 也支持类似能力
- Context Pack 可通过 pipe、临时文件或 stdin 传入

## P4 任务拆分

### P4-0：ccswitch 自动切换

1. **P4-0-1**: 验证 ccswitch Deep Link 协议稳定性
   - 测试 `ccswitch://v1/import` 的 provider 和 prompt 导入
   - 测试并发导入行为
   - 测试导入延迟

2. **P4-0-2**: 实现自动 Deep Link 开关
   - `aios run TASK-ID --auto-switch` 自动打开 provider → prompt Deep Link
   - 可配置延迟等待

3. **P4-0-3**: 轮询检测与 fallback
   - 轮询检测 ccswitch 切换完成状态
   - 超时 fallback

4. **P4-0-4**: Web UI 自动切换按钮
   - "一键切换并开始执行" 按钮

### P4-1：Codex / Claude Code 全自动调用

1. **P4-1-1**: 完善 CLI 模式 model 参数桥接
   - Codex CLI: `codex --model <model>` 或环境变量
   - Claude Code CLI: `claude --model <model>` 或环境变量

2. **P4-1-2**: Context Pack 文件化传入
   - 生成临时 `.md` Pack 文件
   - 以 stdin 或文件路径传入

3. **P4-1-3**: 自动开始 + 自动等待
   - 自动启动执行器 CLI
   - 等待执行完成（超时检测）
   - 自动提取退出码和结果

4. **P4-1-4**: Web UI 全自动执行流程
   - "全自动执行" 按钮（串联 switch + execute + verify）

### P4-2：端到端闭环调度

1. **P4-2-1**: 从目标到 PR 的全自动一级命令
   - `aios run auto --pipeline` 一次性完成所有任务
   - 按调度状态自动选择任务、自动执行、自动回写

2. **P4-2-2**: Launcher 端到端进度看板
   - 实时显示当前任务状态
   - 显示全链路进度

### P4-3：质量保障和护栏

1. **P4-3-1**: 端到端超时控制
2. **P4-3-2**: 任务级重试策略
3. **P4-3-3**: 人工接管队列（当自动化遇到不可恢复的错误时）

## 测试计划

### P4-0 测试

1. Deep Link 稳定性：连续 20 次导入不报错
2. 并发导入：两个任务同时导入不冲突
3. 超时 fallback：导入超时后正确回退

### P4-1 测试

1. CLI 命令正确生成：包含 model 参数和 Pack 路径
2. 自动执行到完成：任务从 ready 到 done
3. 超时终止：执行超时后正确标记失败

### P4-2 测试

1. 完整 pipeline 走通：目标拆解 → 任务执行 → 自动 finish → git commit → push → PR
2. 多轮任务串联：上一个任务完成后自动下一个
3. 失败任务中断：失败时不继续执行依赖任务

### P4-3 测试

1. 超时控制：超过最大执行时间自动停止
2. 人工接管触发：不可恢复错误时进入人工接管队列
3. 全量回归：140 个现有测试 + 新增测试

## 实施顺序

```
P4-0-1 (验证 Deep Link)  ─┐
                          ├─→ P4-0-2 (自动开关) → P4-0-3 (轮询) → P4-0-4 (Web UI)
P4-1-1 (model 桥接)      ─┤
                          ├─→ P4-1-2 (Pack 传入) → P4-1-3 (自动等待) → P4-1-4 (Web UI)
P4-3-1 (超时控制)         ─┘
                                → P4-2 (端到端) → P4-3-2 (重试) → P4-3-3 (接管队列)
```

## 版本里程碑

| 版本 | 内容 | 验收标准 |
|------|------|----------|
| v0.38.1 | 测试修复 + dispatch bridge 阻塞检测 | 140 passed |
| v0.39 | P4-0 cswitch 自动切换 | Deep Link 自动切换可用 |
| v0.40 | P4-1 执行器全自动调用 | 自动调起 CLI 并完成执行 |
| v0.41 | P4-2 端到端闭环 | 一键从目标到 PR |
| v0.42 | P4-3 质量保障 | 超时/重试/接管全就绪 |
