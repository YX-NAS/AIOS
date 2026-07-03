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
4. provider 服务本身现在是否至少网络可达。

当前阶段采用“受控 handshake + 本地缓存”的方式补强真相，但仍不伪装成“已经验证账号权限完全可用”。

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
- 新增主动探测能力：
  - `aios model probe`
  - launcher 模型表“探测”按钮
- provider handshake 结果写入本地缓存并回显到运行时状态
- launcher 首页模型表支持：
  - 编辑鉴权环境变量
  - 展示模型运行时状态
- launcher 项目卡片增加：
  - `provider_ready_count`
  - `provider_handshake_ready_count`

### 本轮不做

- 不做带鉴权业务请求的完整功能验证
- 不自动验证 token 是否具备真实额度和权限
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
  "handshake_status": "ok",
  "handshake_checked_at": "2026-07-03T09:30:00",
  "handshake_http_status": 401,
  "handshake_target_url": "https://api.openai.com/v1",
  "handshake_reason": null,
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
  - 且最近一次 handshake 结果不是 `failed`

### handshake 状态

- `unknown`
  - 尚未主动探测
- `ok`
  - 成功建立网络连接，或收到 provider 的 2xx-4xx 响应
- `failed`
  - 网络不可达、DNS 失败、连接被拒绝，或 provider 返回 5xx

这里的判断目标是“服务是否在线可达”，不是“当前 token 一定可用”。

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
- handshake_status
- handshake_http_status
- handshake_checked_at
- handshake_target_url
- reason

这个命令是模型层的 doctor，对应 `aios executor doctor` 的执行器层 doctor。

### `aios model probe`

主动请求模型的 `endpoint` 或 `config_url`：

- 成功时写入 `ok`
- 网络错误或 5xx 时写入 `failed`
- 结果缓存到全局状态目录，供 launcher / CLI / 项目摘要复用

## Web / Launcher 设计

### 模型表

模型表新增两列：

- 鉴权变量
- 运行时状态

运行时状态直接展示：

- 是否就绪
- provider 配置是否完整
- 缺少哪些环境变量
- 最近一次 handshake 是否成功
- 当前阻塞原因

### 项目卡片

项目卡片新增 `provider_ready_count`，用于回答一个更实际的问题：

“这个项目当前启用的模型里，有多少个在本机上已经具备基本调用条件？”

由于模型库是全局共享，这个指标在不同项目上通常一致，但放在项目卡片里可以和执行器、任务数、活跃执行一起看。

项目卡片还会显示 provider handshake 正常 / 失败数量，帮助回答：

“这些模型不只是配好了，而且最近探测时真的能连上吗？”

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
   - `aios model probe gpt-5.5` 能输出 handshake 结果
   - `aios status` 能输出 provider readiness 汇总

4. 项目摘要
   - 项目摘要包含 `provider_ready_count`
   - 项目摘要包含 handshake 统计

### 手工验收

1. 启动 launcher
2. 打开全局模型库
3. 为某个模型设置 provider 地址和鉴权变量
4. 在本机导出对应环境变量
5. 点击模型表“探测”，或执行 `aios model probe MODEL_ID`
6. 刷新页面，确认模型状态变为“就绪”，并带最近 handshake 信息
7. 查看项目卡片，确认 provider readiness 与 handshake 统计同步变化
8. 执行 `aios model doctor MODEL_ID`，确认 CLI 输出与页面一致

## 风险与边界

### 已解决

- 减少“路由推荐正确但本机没配好 provider”造成的空跑
- 让模型库从静态推荐表升级为“带运行时真相的配置表”

### 仍未解决

- token 是否真的有效
- 第三方桌面工具里是否真的恢复到了正确会话
- provider 某个具体业务接口是否真的可用

这些属于后续阶段：

- provider API 深度握手 / 权限验证
- session truth source
- 更强的 bridge 自动确认

## 结论

P3-29 解决的是“模型层 readiness 盲区”，当前又向前推进了一步：  
系统不仅知道你有没有填 provider 和密钥，还知道这个 provider 最近一次探测时到底能不能连上。

P3-27 负责判断执行器能不能跑，P3-29 负责判断模型 provider 是否至少在“配置 + 可达性”层面可用。两者合在一起，AIOS 才开始具备更可靠的自动执行前置判断。
