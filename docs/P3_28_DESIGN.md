# P3-28 验证失败后的自动二次派发设计

生成时间：2026-07-02

## 目标

P3-8 让 AIOS 具备了自动收口能力，但也留下一个明显断点：

- 执行器成功跑完；
- `verify_command` 失败；
- 任务停在 `review_pending`；
- 自动链路被完全卡住。

P3-28 要解决的是这个断点。

本阶段新增一条受控策略：当验证失败时，AIOS 可以把当前执行留痕后，自动切到下一候选模型，再重试一次。

## 范围

本轮实现：

- CLI 参数 `--retry-on-verify-fail`
- `run auto` 支持验证失败后自动二次派发
- `run TASK-ID --executor ...` 支持同样的单任务自动二次派发
- `/api/run/dispatch` 与 `/api/run/execute` 支持该能力
- Web UI “自动推进下一步”支持该开关

本轮不做：

- 无限重试
- 同一步骤多轮模型轮换
- 自动改写验证命令
- 基于失败类型选择不同执行器

## 设计原则

### 1. 只重试一次

这一版只允许一次自动 fallback 重试，避免系统在多个模型之间循环。

### 2. 保留失败痕迹

第一次执行不会被覆盖，而是写成独立执行记录状态 `retry_queued`，并保留：

- 失败模型
- 验证摘要
- 下一次准备重试的模型
- 第几次自动重试

### 3. 必须有 fallback 才重试

如果当前任务没有剩余候选模型，AIOS 不会强行再派发，而是继续停留在人工处理路径。

### 4. 不突破现有安全门

这轮自动二次派发只针对“验证失败”这一类受控场景，不会绕过：

- bridge 待确认
- 执行器不可用
- provider 未就绪
- 依赖未完成

## 状态变化

第一次执行成功但验证失败时：

1. 当前执行原本处于 `review_pending`
2. AIOS 将该执行改写为 `retry_queued`
3. 任务状态回到 `todo`
4. 任务推荐模型切到下一候选模型
5. 立刻再派发一次执行

如果第二次重试验证通过：

- 新执行进入 `finished`
- 任务进入 `done`

如果第二次重试仍未通过：

- 新执行保持 `review_pending`
- 不再继续自动重试

## 数据变化

### 执行记录新增字段

- `retry_trigger`
- `retry_reason`
- `retry_failed_model`
- `retry_next_model`
- `retry_attempt`
- `retry_source_execution_id`
- `retry_source_model`

### 任务记录新增字段

- `auto_retry_count`
- `last_retry_at`
- `last_retry_reason`
- `last_failed_model`
- `last_retry_execution_id`
- `last_retry_trigger`

这些字段用于后续做失败画像、调度统计和策略学习。

## CLI 变化

新增参数：

```bash
aios run auto --executor codex-cli --auto-finish --summary "完成修复" --verify-command "pytest -q" --retry-on-verify-fail

aios run TASK-ID --executor codex-cli --auto-finish --summary "完成修复" --verify-command "pytest -q" --retry-on-verify-fail
```

输出补充：

- 上一次验证摘要
- 自动重试是否发生
- 从哪个模型切到了哪个模型

## API 变化

新增请求字段：

- `retry_on_verify_fail`

新增返回字段：

- `auto_retried`
- `retry`
- `previous_verification`

## Web UI 变化

完成表单新增复选项：

- `验证失败时自动切换到下一候选模型并重试一次`

活动反馈中会显示：

- 上一次验证失败摘要
- 自动重试切换前后的模型

## 测试计划

### 自动化测试

1. 单任务 CLI
   - 第一次验证失败
   - 自动切到 fallback
   - 第二次验证通过
   - 任务最终 `done`

2. Dispatch API
   - `/api/run/dispatch` 触发自动二次派发
   - 返回 `auto_retried = true`
   - 首次执行记录状态为 `retry_queued`
   - 第二次执行记录带 `retry_source_execution_id`

3. 回退边界
   - 没有 fallback 时不自动重试
   - 第二次仍失败时不继续自动重试

### 手工验收

1. 创建一个带 fallback 的任务
2. 配置自动执行器
3. 使用会先失败一次的验证命令
4. 勾选自动重试
5. 观察 AIOS 自动切到下一候选模型
6. 确认执行记录中保留两次执行痕迹

## 结论

P3-28 的价值不是“让系统更激进”，而是让自动链路在一个很常见的失败点上不至于立刻断掉。

这一步完成后，AIOS 的自动执行链路从：

- 派发
- 执行
- 验证
- 卡住

变成：

- 派发
- 执行
- 验证
- 受控 fallback 重试一次
- 成功则收口，失败则交还人工
