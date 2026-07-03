# P3-33 差异化自动恢复策略设计

生成时间：2026-07-03

## 目标

P3-28 解决的是一种很具体的断点：

- 验证失败后，自动切到下一候选模型再试一次

P3-30 又让系统开始知道：

- 失败属于哪一类
- 下一步更像是该重试、切模型，还是修配置

P3-33 的目标，就是把这两层真正接起来，让 AIOS 在“执行失败”这一步不再只有一种恢复动作。

## 本轮范围

本轮落地：

- 新增统一自动恢复入口
- 保持旧 `--retry-on-verify-fail` 兼容，但内部升级为更通用的自动恢复开关
- 按失败分类执行不同恢复策略
- 自动恢复结果写回 execution 留痕
- Web / CLI 回显恢复触发、恢复策略和来源 execution

## 恢复策略

### 1. `verification_failed`

策略：

- `reroute_fallback_model`

行为：

- 把任务推荐模型切到下一候选 fallback
- 重新派发一次执行

这是 P3-28 既有能力，P3-33 继续复用它。

### 2. `provider_unreachable`

策略：

- `rerun_same_model`

行为：

- 同模型、同执行器自动再跑一次

原因：

- 这类失败更像瞬时网络抖动，不该直接改模型。

### 3. `executor_timeout`

策略：

- `rerun_same_model`

行为：

- 同模型、同执行器自动再跑一次

原因：

- 先给一次最小恢复机会，后续再细分成 timeout 参数调整或长任务升级。

### 4. `executor_nonzero_exit`

策略：

- `rerun_same_model`

行为：

- 自动再跑一次

边界：

- 当前不做更复杂的 stderr 语义树，只给一次受控重跑。

### 5. `provider_auth_failed`

策略：

- 不自动恢复

原因：

- 这不是瞬时问题，而是配置 / 鉴权真相问题，继续自动重试只会空跑。

## 数据留痕

恢复后的新 execution 会补这些字段：

```json
{
  "retry_source_execution_id": "EXEC-001",
  "retry_source_model": "gpt-5.5",
  "retry_attempt": 1,
  "recovery_trigger": "provider_unreachable",
  "recovery_strategy": "rerun_same_model"
}
```

来源 execution 会写：

- `status = retry_queued`
- `retry_trigger`
- `retry_reason`
- `recovery_disposition = queued`

## 入口变化

### CLI

新增主开关：

```bash
aios run auto --auto-recover-failures
aios run TASK-ID --executor codex-cli --auto-recover-failures
```

兼容旧写法：

```bash
aios run auto --retry-on-verify-fail
```

旧参数继续可用，但现在语义已经扩大为“按失败类型自动恢复一次”。

### Web

项目控制台完成表单中的选项升级为：

- 按失败类型自动恢复一次

## 测试方案

### 自动化测试

1. 验证失败
- 自动切到 fallback 模型

2. 网络型失败
- 首次失败分类为 `provider_unreachable`
- 自动同模型重跑
- 第二次执行进入 `review_pending`

3. 鉴权型失败
- 分类为 `provider_auth_failed`
- 不自动恢复

4. 留痕
- 新 execution 包含 `recovery_trigger / recovery_strategy`
- 旧 execution 进入 `retry_queued`

## 结论

P3-33 的价值，在于让 AIOS 从“有失败分类”推进到“会用失败分类”。

现在系统已经开始具备：

- 验证失败切 fallback
- 瞬时失败同模型重跑
- 配置类失败直接停下

这比单一的“一次 fallback retry”更接近真正的自动执行中枢。
