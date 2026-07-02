# P3-11 外部模型切换接管设计

生成时间：2026-07-02

## 目标

把 AIOS 从“只能导出 `ccswitch` JSON”推进到“可以直接生成并使用 `ccswitch` 官方 Deep Link”。

这一阶段的重点，是利用 `ccswitch` 已公开、可验证的能力做最小可用接管，而不是假装已经拥有一个稳定 CLI。

## 结论

当前 `ccswitch` 更适合接入的能力是：

- Deep Link 导入
- 会话历史恢复
- 桌面端会话切换

当前不适合把它当作稳定依赖的能力是：

- 官方 CLI 自动切换
- 无确认的脚本注入

所以这一版不做“静默切换模型”，而是做：

- `ccswitch` Deep Link 生成
- 可选本机打开 Deep Link
- AIOS 执行记录中保留 Deep Link 审计信息

## 范围

本阶段实现：

- `aios ccswitch deeplink TASK-ID --app codex`
- `POST /api/ccswitch/deeplink`
- 单项目 Web UI 一键复制 Deep Link
- 执行记录写入：
  - `ccswitch_deeplink`
  - `ccswitch_deeplink_app`
  - `ccswitch_deeplink_generated_at`
  - `ccswitch_deeplink_opened_at`

本阶段不实现：

- 自动注入 provider API Key
- 自动切换 provider 配置
- 自动恢复指定历史会话
- 自动启动 Codex / Claude Code 会话并确认上下文生效

## Deep Link 策略

当前选用的官方可验证资源类型是：

- `resource=prompt`

也就是说，AIOS 会把当前任务 handoff 作为一个 prompt 资源，生成：

```text
ccswitch://v1/import?resource=prompt&app=codex&name=...&content=...
```

这样可以直接把任务交接内容导入 `ccswitch`，缩短“复制 handoff -> 打开 `ccswitch` -> 粘贴上下文”的人工步骤。

## 为什么先做 prompt Deep Link

因为 provider 类型的导入虽然也能走 Deep Link，但通常涉及：

- endpoint
- model
- apiKey
- provider 名称

这些字段如果没有统一来源，就容易把 AIOS 变成秘密管理和 provider 配置分发系统，风险太高。

而 prompt Deep Link：

- 不碰密钥
- 不碰用户现有 provider 配置
- 直接复用 AIOS 已有 handoff
- 足够支撑下一步手动或半自动会话切换

## CLI 变化

新增：

```bash
aios ccswitch deeplink TASK-ID --app codex --stdout
aios ccswitch deeplink TASK-ID --app claude --open
```

说明：

- `--app` 默认 `codex`
- `--stdout` 输出完整 Deep Link
- `--open` 尝试调用本机 `open` / `xdg-open` / `start`

## Web UI 变化

任务检查器新增：

- `复制 ccswitch Deep Link`

当前默认按 `codex` 目标应用生成并复制。

## 测试计划

### 自动化测试

1. CLI `ccswitch deeplink` 能生成 `ccswitch://v1/import?...`
2. API `/api/ccswitch/deeplink` 返回 Deep Link
3. 执行记录能保留 Deep Link 字段

### 手工验收

1. 先准备一条任务执行记录
2. 生成或复制 Deep Link
3. 在本机打开 `ccswitch`
4. 确认 `ccswitch` 能导入 prompt 资源

## 下一步

P3-11 完成后，后续真正逼近“自动切换”的工作会变成：

- `P3-12` push / PR 远程交付
- `P3-13` provider / session 适配器
- `P3-14` 会话恢复与继续执行

也就是说，这一版先把“导入入口”打通，后面再把“会话定位和切换控制”逐步接上。
