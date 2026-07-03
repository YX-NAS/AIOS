# P3-32 Provider API 深度权限验证设计

生成时间：2026-07-03

## 目标

P3-29 解决了两层问题：

- provider 地址和鉴权变量有没有配
- provider 最近一次网络握手能不能通

但自动执行要更可靠，还差第三层：

- 这组鉴权信息到底有没有权限访问 provider API

也就是说，系统不能只知道“门在这里”，还要知道“钥匙能不能开门”。

P3-32 的目标，就是把模型 readiness 从：

- 配置存在
- 网络可达

推进到：

- API 权限经过一次受控验证

## 本轮范围

本轮落地：

- `aios model probe` 在现有握手基础上增加 provider API 权限验证
- 当前支持首版深度验证的 provider：
  - `openai`
  - `anthropic`
  - `deepseek`
- 探测结果写回模型握手缓存
- `model doctor`、`status`、launcher、项目控制台回显权限验证状态
- 调度器把“权限验证失败”作为可执行前阻塞条件

本轮不做：

- 所有 provider 的业务接口级细分验证
- 拉取真实账单或额度
- 自动修复 provider 配置或自动刷新密钥
- 针对不同 provider 的复杂多接口 smoke test

## 数据模型

模型运行时新增字段：

```json
{
  "auth_probe_status": "ok",
  "auth_probe_checked_at": "2026-07-03T14:00:00",
  "auth_probe_http_status": 200,
  "auth_probe_latency_ms": 123.45,
  "auth_probe_target_url": "https://api.openai.com/v1/models",
  "auth_probe_reason": null
}
```

状态含义：

- `ok`
  - 已完成权限验证，请求被 provider 正常接受
- `failed`
  - 明确验证失败，例如 401 / 403，或探测链路明确失败
- `skipped`
  - 当前 provider 暂未支持深度验证，或本机鉴权变量本身不完整
- `unknown`
  - 还没做过探测

## 探测策略

### 第一层：基础握手

仍沿用 P3-29 的轻量握手：

- 对 endpoint 做受控 GET
- 2xx-4xx 视为网络可达
- DNS / 连接拒绝 / 超时视为失败

### 第二层：API 权限验证

在握手成功或至少可达的前提下，继续对 provider 的公开列表接口发起一次带鉴权头的请求。

当前规则：

1. `openai`
- URL：`/models`
- Header：`Authorization: Bearer <OPENAI_API_KEY>`

2. `anthropic`
- URL：`/v1/models`
- Header：
  - `x-api-key`
  - `anthropic-version`

3. `deepseek`
- URL：`/models`
- Header：`Authorization: Bearer <DEEPSEEK_API_KEY>`

结果判定：

- `2xx` => `auth_probe_status = ok`
- `401 / 403` => `auth_probe_status = failed`
- 其他 `4xx / 5xx` => `failed`
- 未支持 provider 或本机变量不完整 => `skipped`

## 调度接入

新增一个非常关键的行为：

- 如果推荐模型的 `auth_probe_status == failed`
- 调度器不再把任务视为 `ready`
- 而是标记为：
  - `scheduler_state = blocked`
  - `next_action = fix_provider_auth`

这样自动派发就不会把任务继续发给一个“网络能通、但账号无权限”的模型。

其他模型阻塞条件也统一纳入调度入口：

- 缺 provider 配置
- 缺鉴权环境变量
- 最近握手失败
- 最近权限验证失败

## UI / CLI 变化

### `aios model doctor`

新增输出：

- `auth_probe_status`
- `auth_probe_http_status`
- `auth_probe_checked_at`
- `auth_probe_target_url`

### `aios model probe`

新增输出：

- `auth_probe: ok/failed/skipped`

### `aios status`

新增聚合行：

- `Provider API: X verified / Y failed`

### launcher / 项目控制台

新增可见信息：

- provider API 权限验证通过数 / 失败数
- 模型运行时卡片展示权限验证状态

## 测试方案

### 自动化测试

1. `model probe` 成功权限验证
- 握手返回 401
- API 探测返回 200
- 最终记录 `auth_probe_status = ok`

2. `model probe` 鉴权失败
- 握手可达
- API 探测返回 401
- 最终模型变为 `not-ready`

3. 调度器阻塞
- 如果推荐模型最近权限验证失败
- 任务进入 `blocked`
- `next_action = fix_provider_auth`

4. launcher API
- `/api/models/probe` 返回 `auth_probe_status`
- 汇总统计包含 verified / failed 数

### 手工验收

1. 给模型配置 provider 和本机密钥
2. 执行 `aios model probe MODEL-ID`
3. 执行 `aios model doctor MODEL-ID`
4. 确认看到握手状态和权限验证状态
5. 故意使用错误密钥再次探测
6. 确认模型状态变成 `not-ready`
7. 回到项目控制台，确认相关任务被阻塞，提示修复 provider auth

## 结论

P3-32 的价值，不是“多打一次 HTTP 请求”，而是把 provider 真相继续推进了一层。

现在 AIOS 不再只知道：

- 有没有填 endpoint
- 网络是不是通

还开始知道：

- 这组鉴权信息到底有没有权限调用模型 API

这会直接减少自动派发中的空跑，为下一步的：

- 多轮自动恢复
- provider 级差异化调度
- 更接近真实可执行的 readiness truth source

提供更可靠的前置判断。
