# P3-30 失败分类与重试策略设计

生成时间：2026-07-03

## 目标

AIOS 现在已经能：

- 自动派发
- 自动完成
- 验证失败后 fallback 重试一次
- 判断 provider 是否至少可达

但系统还缺一层关键能力：

- 失败时到底是哪一类失败
- 是不是值得自动重试
- 下一步应该修 provider、修执行器、调 timeout，还是人工验收

P3-30 的目标就是把“失败”从一段散乱的 stderr，提升成可调度、可展示、可扩展的结构化状态。

## 本轮范围

本轮落地：

- 为 execution 增加失败分类字段
- 对 executor 失败做首版结构化分类：
  - `executor_missing_binary`
  - `executor_timeout`
  - `provider_auth_failed`
  - `provider_unreachable`
  - `executor_nonzero_exit`
- 对 verification 失败做结构化分类：
  - `verification_failed`
- 为每种失败生成：
  - `failure_source`
  - `failure_category`
  - `failure_summary`
  - `failure_retryable`
  - `failure_next_action`
  - `failure_detected_at`
- scheduler 优先读取结构化失败信息，而不是只看 stderr
- Web 任务检查器显示失败分类和建议动作
- CLI `run` 输出失败分类与建议动作

本轮不做：

- 多轮自动重试树
- 基于失败分类的自动恢复脚本
- provider 业务接口级错误分类
- bridge 失败的更细粒度分类归并

## 数据结构

execution 记录新增字段：

```json
{
  "failure_source": "executor",
  "failure_category": "provider_unreachable",
  "failure_summary": "Execution failed with exit code 1. Provider network appears unreachable.",
  "failure_retryable": true,
  "failure_next_action": "probe_provider",
  "failure_detected_at": "2026-07-03T10:00:00"
}
```

说明：

- `failure_source`
  - `executor`
  - `verification`
- `failure_category`
  - 当前是首版枚举，后续会继续扩展
- `failure_retryable`
  - 系统层是否值得尝试自动恢复
- `failure_next_action`
  - 给调度器、Web、CLI 的统一下一步建议

## 分类规则

### Executor 层

1. `executor_missing_binary`
- 场景：二进制不存在或执行时找不到命令
- 自动重试：否
- 建议动作：`fix_executor_binary`

2. `executor_timeout`
- 场景：执行超时
- 自动重试：是
- 建议动作：`inspect_timeout`

3. `provider_auth_failed`
- 场景：stderr / stdout 命中鉴权失败关键词
- 自动重试：否
- 建议动作：`fix_provider_auth`

4. `provider_unreachable`
- 场景：stderr / stdout 命中网络不可达关键词
- 自动重试：是
- 建议动作：`probe_provider`

5. `executor_nonzero_exit`
- 场景：非零退出，但没命中更明确规则
- 自动重试：是
- 建议动作：`inspect_executor_failure`

### Verification 层

1. `verification_failed`
- 场景：验证命令退出码非 0
- 自动重试：是
- 建议动作：`retry_or_finish`

## 调度层变化

### 1. failed 任务

scheduler 不再只展示 stderr，而是优先读取：

- `failure_next_action`
- `failure_summary`

这样“失败”开始具备真正的调度意义。

### 2. review_pending + verification_failed

这类任务不应该继续显示成泛化的“等待人工 review”。

现在会保留 `review_pending`，但下一步动作会变成：

- `retry_or_finish`

这样系统能明确区分：

- 代码跑完但还没 review
- 代码跑完了，但验证没过

## UI / CLI 变化

### Web 任务检查器

执行状态卡新增：

- 失败来源
- 失败分类
- 是否建议自动重试
- 建议动作
- 失败摘要

调度状态卡新增：

- 失败分类
- 是否建议自动重试

### CLI

`aios run ...` 在失败场景下新增输出：

- `Failure category`
- `Failure action`

## 测试计划

### 自动化测试

1. 执行器缺失二进制
- 生成 execution 记录
- 分类为 `executor_missing_binary`

2. verification 失败
- execution 保持 `review_pending`
- 分类为 `verification_failed`
- `failure_next_action = retry_or_finish`

3. scheduler
- 优先读取结构化失败原因，而不是只回显 stderr

4. Web / CLI
- 任务检查器能拿到失败分类字段
- `run` CLI 输出失败分类

### 手工验收

1. 配一个故意失败的执行器
2. 执行任务
3. 在项目控制台查看失败分类、建议动作
4. 再跑一个验证失败任务
5. 确认状态仍是 `review_pending`，但建议动作变为 `retry_or_finish`

## 结论

P3-30 不是简单地“多记几个字段”，而是把失败从日志文本升级成系统决策输入。

后续做：

- 多轮自动恢复
- provider 深度权限验证后的差异化处理
- 更细的 retry 策略
- bridge / session / provider 的统一失败图谱

都要建立在这层结构化失败模型之上。
