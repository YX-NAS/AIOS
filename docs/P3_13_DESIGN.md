# P3-13 Provider / Session 接管设计

生成时间：2026-07-02

## 目标

把 AIOS 从“只会导出 prompt Deep Link”推进到“可以把模型对应的 provider 配置和会话恢复提示一起交给 `ccswitch`”。

这一阶段不追求静默自动切换桌面，也不伪造一个并不存在的稳定 `ccswitch` CLI。目标是先把全自动执行真正缺失的数据层补齐：

- 任务到底要切到哪个 provider
- 这个 provider 的入口地址是什么
- 新会话和旧会话各该怎么继续
- AIOS 如何把这些信息落成可追溯产物

## 外部能力边界

根据 `ccswitch` 当前已公开文档，可验证的能力有：

- `resource=provider` Deep Link 导入 provider 配置
- `resource=prompt` Deep Link 导入 prompt
- Session Manager 可扫描和恢复本机会话

当前没有证据表明 AIOS 可以稳定依赖这些能力：

- 指定切换到某一个 provider 并静默生效
- 直接恢复某一个指定 session id
- 无确认控制桌面 UI

所以这一版的策略是：

1. 用全局模型库补足 provider 元数据；
2. 生成 Provider Deep Link；
3. 生成 Session Handoff JSON，把 provider / prompt / 恢复提示串起来；
4. 在执行记录里完整留痕。

## 范围

本阶段实现：

- 全局模型库新增可选字段：
  - `endpoint`
  - `homepage`
  - `notes`
  - `config_url`
- CLI：
  - `aios ccswitch provider TASK-ID`
  - `aios ccswitch session TASK-ID`
- Web API：
  - `POST /api/ccswitch/provider-deeplink`
  - `POST /api/ccswitch/session-handoff`
- 单项目 Web UI：
  - `复制 Provider Deep Link`
  - `复制 Session Handoff`
- 执行记录新增字段：
  - `ccswitch_provider_deeplink`
  - `ccswitch_provider_deeplink_app`
  - `ccswitch_provider_name`
  - `ccswitch_provider_model`
  - `ccswitch_provider_generated_at`
  - `ccswitch_provider_opened_at`
  - `ccswitch_session_handoff_path`
  - `ccswitch_session_app`
  - `ccswitch_session_provider`
  - `ccswitch_session_model`
  - `ccswitch_session_exported_at`

本阶段不实现：

- 自动写入 API Key
- 自动恢复指定会话 ID
- 自动点击 `ccswitch` 桌面 UI
- 自动确认 provider 导入成功

## 数据设计

### 1. 全局模型库

模型库继续是全局共享配置，但从“只给路由用”扩展为“也给 handoff 用”。

最小新增字段：

- `endpoint`：provider API 地址
- `homepage`：provider 官网或控制台
- `notes`：补充说明，例如“需要本地路由”
- `config_url`：可选远端配置地址

这些字段都不是必填，旧 `models.json` 不需要迁移。

### 2. Session Handoff 文件

导出路径：

```text
.aios/ccswitch/TASK-ID-EXECUTION-ID-模型名-session-handoff.json
```

最小内容：

- `task_id`
- `task_title`
- `execution_id`
- `app`
- `provider`
- `model`
- `project_root`
- `pack_path`
- `handoff_path`
- `provider_deeplink`
- `prompt_deeplink`
- `provider_config`
- `session_search_keywords`
- `resume_guidance`
- `exported_at`

它不是恢复脚本，而是给人和后续自动化适配器共同使用的中间产物。

## 交互设计

### CLI

新增：

```bash
aios ccswitch provider TASK-ID --app codex --stdout
aios ccswitch session TASK-ID --app codex --stdout
```

说明：

- `provider`：输出 `resource=provider` Deep Link
- `session`：导出一个包含 provider/prompt deeplink 的 Session Handoff JSON

### Web UI

任务检查器新增两个动作：

- `复制 Provider Deep Link`
- `复制 Session Handoff`

执行状态面板同步显示：

- Provider Deep Link 是否已生成
- Provider 名称
- Session Handoff 文件路径

### Launcher

Launcher 不直接承载 handoff 逻辑，只扩展全局模型库编辑能力，让 provider 元数据可以维护。

## 为什么这一步有价值

AIOS 当前真正卡住的不是“没有更多按钮”，而是“没有可靠的 provider / session 交接数据”。

补完这一层后，后续自动化才能继续往下做：

1. executor adapter 可以读取统一 provider 元数据；
2. `ccswitch` 适配器可以基于 Session Handoff 做更窄的自动恢复尝试；
3. 自动执行失败时，AIOS 仍然有完整审计链，知道切给谁、提示了什么、落了哪些文件。

## 测试计划

### 自动化测试

1. 模型库兼容
- 旧模型库无新增字段时仍可读取
- 新字段可创建、更新、持久化

2. CLI
- `aios ccswitch provider TASK-ID --stdout` 返回 `resource=provider`
- `aios ccswitch session TASK-ID` 生成 JSON 文件
- 执行记录包含 provider / session 字段

3. API
- `/api/ccswitch/provider-deeplink` 返回可复制链接
- `/api/ccswitch/session-handoff` 返回文件路径和 JSON 内容

4. 执行记录
- prompt deeplink、provider deeplink、session handoff 三类信息可并存
- 旧执行记录缺少这些字段时不报错

### 手工验收

1. 在 launcher 中给某个模型补 provider 地址和说明
2. 在单项目页开始执行一条任务
3. 点击“复制 Provider Deep Link”
4. 点击“复制 Session Handoff”
5. 确认执行状态面板中能看到 provider/session 留痕
6. 在 `ccswitch` 中导入 provider，再导入 prompt，验证人工路径更短

## 后续衔接

P3-13 完成后，合理下一步是：

- `P3-15` 之前先补一个更窄的 `ccswitch` adapter 实验层
- 优先尝试“打开 deeplink + 打开 session manager 搜索”的受控自动化
- 再评估是否值得接入真正的桌面自动恢复

也就是说，这一版先把“provider / session handoff 数据层”做扎实，再决定是否继续走桌面自动控制。
