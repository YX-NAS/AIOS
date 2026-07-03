# P3-35 分类级恢复上限与冷却策略设计

生成时间：2026-07-03

## 目标

P3-34 已经解决了一个重要问题：

- 自动恢复不会无限循环

但真正稳定的自动执行还需要再细一层：

- 不同失败类别，本来就不该用同一套恢复次数
- 连续恢复之间，应该允许设置冷却时间

P3-35 的目标，就是把恢复护栏从“项目总上限”推进到：

- 分类级恢复上限
- 项目级恢复冷却

## 本轮范围

本轮落地：

- runtime policy 新增 `auto_recovery_limits`
- runtime policy 新增 `auto_recovery_cooldown_seconds`
- Web 项目控制台可直接配置这些字段
- 自动恢复在每一轮前都会检查：
  - 项目总恢复上限
  - 当前失败类别上限
  - 是否处于恢复冷却期
- execution 回写：
  - `recovery_blocked_reason`
  - `recovery_next_retry_at`

## 策略结构

```json
{
  "max_auto_recovery_attempts": 2,
  "auto_recovery_cooldown_seconds": 0,
  "auto_recovery_limits": {
    "verification_failed": 1,
    "provider_unreachable": 2,
    "executor_timeout": 1,
    "executor_nonzero_exit": 1,
    "provider_auth_failed": 0
  }
}
```

含义：

- `max_auto_recovery_attempts`
  - 项目总恢复上限
- `auto_recovery_cooldown_seconds`
  - 两轮自动恢复之间最少等待秒数
- `auto_recovery_limits`
  - 当前失败类别最多还能恢复多少轮

## 当前默认值

- `verification_failed = 1`
- `provider_unreachable = 2`
- `executor_timeout = 1`
- `executor_nonzero_exit = 1`
- `provider_auth_failed = 0`
- `auto_recovery_cooldown_seconds = 0`

解释：

- 验证失败更像代码 / 测试结论问题，默认只给一次 fallback
- 网络失败更像瞬时问题，默认给两次机会
- provider 鉴权失败本质是配置问题，默认不自动恢复

## 判定顺序

每次准备进入下一轮恢复前，AIOS 会按顺序检查：

1. 是否已经达到项目总恢复上限
2. 是否已经达到当前失败类别上限
3. 是否仍在恢复冷却期

只要任一条件不满足，自动恢复立即停止。

## 返回与留痕

如果被策略拦住，execution 会写：

```json
{
  "recovery_blocked_reason": "自动恢复冷却中，需等待到 ...",
  "recovery_next_retry_at": "2026-07-03T15:00:00"
}
```

这样 AIOS 不只是停下，还能说明：

- 为什么停
- 下次最早什么时候能继续

## UI 变化

项目控制台预算策略区域新增：

- 自动恢复冷却秒数
- 验证失败恢复上限
- 网络失败恢复上限
- 超时恢复上限
- 非零退出恢复上限

## 测试方案

### 自动化测试

1. Web policy API
- 默认返回分类级恢复上限
- 更新后能正确持久化

2. 分类级上限
- 项目总上限足够大
- 但 `provider_unreachable` 上限设为 1
- 自动恢复一轮后停止

3. 恢复冷却
- 项目总上限足够大
- 冷却秒数设为 60
- 第一轮恢复后立即停止下一轮
- execution 记录 `recovery_blocked_reason`

## 结论

P3-35 的价值，在于让 AIOS 的自动恢复开始具备“区别对待失败”的能力。

这一步之后，系统不再只是：

- 最多恢复几次

而是开始知道：

- 这个失败值不值得多给几次机会
- 现在该不该立刻再试

这会让后续的 provider 节流、时间窗口、通知和人工接管策略更容易接入。
