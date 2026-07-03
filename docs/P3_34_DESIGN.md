# P3-34 多轮自动恢复护栏设计

生成时间：2026-07-03

## 目标

P3-33 已经让 AIOS 具备“按失败类型自动恢复一次”的能力。

但只要系统开始自动恢复，就必须同时解决两个问题：

- 能不能继续多恢复一轮，把瞬时失败真正跑通
- 怎样防止系统自己陷入恢复循环

P3-34 的目标，就是把自动恢复从“一次动作”升级成“受控多轮链路”，同时加上明确上限。

## 本轮范围

本轮落地：

- 项目级策略新增 `max_auto_recovery_attempts`
- 初始化项目默认写入该策略，默认值为 `2`
- `run auto` / `run TASK-ID --executor ...` / Web `run/execute` 都支持多轮自动恢复
- 恢复链结果回传：
  - `recovery_chain`
  - `auto_recovery_attempts_used`
  - `auto_recovery_limit_reached`
- 修复同秒多条 execution 时“最新记录不稳定”的问题，改为更稳的 execution 排序与精确回读

## 策略模型

新增 runtime policy 字段：

```json
{
  "max_auto_recovery_attempts": 2
}
```

含义：

- `0`
  - 完全关闭自动恢复
- `1`
  - 最多恢复一轮
- `2`
  - 最多恢复两轮

当前默认值：

- `2`

原因：

- 一次恢复对网络抖动不一定够
- 但默认就无限重试风险太高

## 执行行为

当启用：

```bash
--auto-recover-failures
```

系统会按下面逻辑推进：

1. 执行任务
2. 如果失败类型允许恢复，尝试第 1 轮恢复
3. 如果恢复后的执行仍是可恢复失败，且未达到上限，再尝试下一轮
4. 达到上限立即停止，不再继续自动恢复

也就是说，AIOS 现在不只是“是否恢复”，还开始管理：

- 恢复了几次
- 还剩几次机会
- 什么时候必须停下

## 留痕结构

返回与记录补充：

```json
{
  "recovery_chain": [
    {
      "execution_id": "EXEC-001",
      "status": "failed",
      "trigger": "provider_unreachable",
      "strategy": "rerun_same_model"
    },
    {
      "execution_id": "EXEC-002",
      "status": "review_pending",
      "trigger": "provider_unreachable",
      "strategy": "rerun_same_model"
    }
  ],
  "auto_recovery_attempts_used": 2,
  "auto_recovery_limit_reached": true
}
```

这让 AIOS 后续可以继续扩展：

- 更细的恢复树
- 恢复成本控制
- 通知与人工接管门

## UI / CLI 变化

### 项目控制台预算策略

新增字段：

- 自动恢复次数上限

### CLI

自动恢复结果新增输出：

- `Recovery attempts used`

## 测试方案

### 自动化测试

1. runtime policy
- 默认包含 `max_auto_recovery_attempts = 2`
- Web API 可更新该值

2. 多轮恢复成功
- 第一次执行失败
- 第 1 轮恢复后仍失败
- 第 2 轮恢复后成功
- 返回 `recovery_chain` 长度为 2

3. 上限阻断
- 连续失败
- 超过上限后停止
- 返回 `auto_recovery_limit_reached = true`

4. execution 选择稳定性
- 同秒多条 execution 时，最新记录仍能正确指向最后一条

## 结论

P3-34 的价值，是把自动恢复从“能动起来”推进到“知道什么时候该停”。

这一步对全自动执行是必要前提，因为：

- 没有多轮恢复，很多瞬时失败还是需要人工接管
- 没有恢复上限，系统又会失控

P3-34 先把这两个边界一起补齐，后续才能继续往更复杂的恢复树推进。
