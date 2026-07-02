# P3-29 Provider / 鉴权就绪探测设计

生成时间：2026-07-02

## 目标

P3-27 已经解决“执行器命令能不能跑”的问题，但自动执行仍然会遇到另一类空转：

- 任务路由推荐了模型；
- 执行器也可用；
- 但本机根本没有配置对应 provider 地址或鉴权变量；
- 最终在真正调用模型或导入 provider 时才失败。

P3-29 的目标是把这层真相前置暴露出来，让 AIOS 在“开始执行前”就知道：

1. 某个模型对应的 provider 是否已配置；
2. 本机是否已经具备该 provider 需要的鉴权环境变量；
3. launcher 首页和 CLI 是否能直接看到这些状态。

本阶段不做远端 API 真正握手，不伪装成“已经验证登录态可用”。

## 范围

### 本轮交付

- 全局模型库新增 `auth_env_vars`
- 默认 provider 补默认 endpoint 和默认鉴权变量
- `model_summary()` 返回每个模型的运行时状态
- 新增 CLI：
  - `aios model list`
  - `aios model doctor`
  - `aios model doctor MODEL_ID`
- `aios status` 增加 provider readiness 汇总
- launcher 首页模型表支持：
  - 编辑鉴权环境变量
  - 展示模型运行时状态
- launcher 项目卡片增加：
  - `provider_ready_count`

### 本轮不做

- 不直接请求真实 provider API
- 不自动验证 token 是否有效
- 不读取第三方 App 内部登录态
- 不把 provider readiness 直接当作任务已可自动执行的唯一依据

## 数据设计

全局模型库记录新增字段：

```json
{
  "id": "gpt-5.5",
  "provider": "openai",
  "endpoint": "https://api.openai.com/v1",
  "config_url": null,
  "auth_env_vars": ["OPENAI_API_KEY"]
}
```

运行时状态结构：

```json
{
  "ready": true,
  "provider_config_status": "ready",
  "auth_status": "ready",
  "auth_env_vars": ["OPENAI_API_KEY"],
  "present_auth_env_vars": ["OPENAI_API_KEY"],
  "missing_auth_env_vars": [],
  "endpoint": "https://api.openai.com/v1",
  "config_url": null,
  "reason": null
}
```

状态规则：

- `provider_config_status`
  - `ready`
  - `missing_config`
- `auth_status`
  - `ready`
  - `missing_env`
  - `not_configured`
- `ready=true`
  - 需要 provider 存在
  - 且 provider 配置存在
  - 且鉴权变量全部已在本机环境中出现

## CLI 设计

### `aios model list`

输出所有模型的：

- model id
- provider
- enabled / disabled
- ready / not-ready
- rank

适合快速看全局模型库是否有明显缺口。

### `aios model doctor`

输出单模型或全部模型的细项：

- provider
- endpoint
- config_url
- auth_status
- auth_env_vars
- present_env_vars
- missing_env_vars
- provider_config
- reason

这个命令是模型层的 doctor，对应 `aios executor doctor` 的执行器层 doctor。

## Web / Launcher 设计

### 模型表

模型表新增两列：

- 鉴权变量
- 运行时状态

运行时状态直接展示：

- 是否就绪
- provider 配置是否完整
- 缺少哪些环境变量
- 当前阻塞原因

### 项目卡片

项目卡片新增 `provider_ready_count`，用于回答一个更实际的问题：

“这个项目当前启用的模型里，有多少个在本机上已经具备基本调用条件？”

由于模型库是全局共享，这个指标在不同项目上通常一致，但放在项目卡片里可以和执行器、任务数、活跃执行一起看。

## 测试计划

### 自动化测试

1. 模型库持久化
   - 新建带 `auth_env_vars` 的自定义模型
   - 重启 launcher 后仍能读到

2. launcher API
   - `/api/models` 返回 `provider_ready_count`
   - 返回模型 `runtime`
   - create/update 支持 `auth_env_vars`

3. CLI
   - `aios model doctor gpt-5.5` 能输出 auth readiness
   - `aios status` 能输出 provider readiness 汇总

4. 项目摘要
   - 项目摘要包含 `provider_ready_count`

### 手工验收

1. 启动 launcher
2. 打开全局模型库
3. 为某个模型设置 provider 地址和鉴权变量
4. 在本机导出对应环境变量
5. 刷新页面，确认模型状态变为“就绪”
6. 查看项目卡片，确认 provider readiness 统计同步变化
7. 执行 `aios model doctor MODEL_ID`，确认 CLI 输出与页面一致

## 风险与边界

### 已解决

- 减少“路由推荐正确但本机没配好 provider”造成的空跑
- 让模型库从静态推荐表升级为“带运行时真相的配置表”

### 仍未解决

- token 是否真的有效
- provider 网络是否真的通
- 第三方桌面工具里是否真的恢复到了正确会话

这些属于后续阶段：

- provider API handshake
- session truth source
- 更强的 bridge 自动确认

## 结论

P3-29 解决的是“模型层 readiness 盲区”。

P3-27 负责判断执行器能不能跑，P3-29 负责判断模型 provider 是否至少在本机配置层面可用。两者合在一起，AIOS 才开始具备更可靠的自动执行前置判断。
