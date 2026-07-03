# P3-31 预算阈值与调度策略设计

生成时间：2026-07-03

## 目标

P3-9 已经让 AIOS 能看到 token、成本和耗时，但系统还不会根据这些数据改变自动派发行为。

P3-31 的目标是把“成本可观测”推进到“成本可决策”：

- 给每个项目配置自动化预算策略
- 在自动派发前检查单次预算和累计预算
- 允许按成本优先级调整 ready 任务的选择顺序
- 在 Web UI 和多项目首页持续显示预算状态

## 借鉴来源

这轮设计借鉴了几类现成系统的成熟思路，但不照搬它们的完整架构：

1. OpenHands  
   参考点：把自动执行链路放在明确的运行状态机之下，而不是裸调用模型。  
   链接：[OpenHands](https://github.com/OpenHands/openhands)

2. LangGraph  
   参考点：把“继续执行前的门槛判断”建模成可恢复、可观测的节点状态。  
   链接：[LangGraph](https://github.com/langchain-ai/langgraph)

3. AutoGen  
   参考点：多代理或多模型协作前，先把成本和策略约束放进调度层。  
   链接：[AutoGen](https://github.com/microsoft/autogen)

AIOS 当前不需要把这些系统完整引入进来。最适合的做法是先补“预算安全门 + 调度策略”这一层，让自动派发不再盲跑。

## 本轮范围

本轮落地内容：

- 新增 `.aios/runtime-policy.json`
- 新增项目级预算策略：
  - `max_total_estimated_cost`
  - `max_single_execution_cost`
  - `block_on_unpriced_model`
  - `dispatch_strategy`
  - `cost_currency`
- 调度器在任务 ready 前增加预算判定
- 当预算不满足时，任务进入 `blocked`，下一步动作标记为 `adjust_budget`
- `dispatch_strategy=cheapest_first` 时，自动派发优先选择预计成本最低的 ready 任务
- Web UI 支持查看和修改预算策略
- Launcher 首页显示每个项目的调度策略、剩余预算、单次上限
- CLI `status` 输出当前预算策略

本轮不做：

- 真实 provider 账单同步
- 日预算 / 周预算
- 按分支、PR、模块拆成本
- 预算超限后的自动通知
- 动态学习“哪种任务更值得用贵模型”

## 数据结构

新增文件：

```json
{
  "max_total_estimated_cost": null,
  "max_single_execution_cost": null,
  "block_on_unpriced_model": false,
  "dispatch_strategy": "default",
  "cost_currency": "USD",
  "updated_at": null
}
```

说明：

- `max_total_estimated_cost`：项目累计估算成本上限
- `max_single_execution_cost`：单次自动执行上限
- `block_on_unpriced_model`：模型没填价格时是否禁止自动派发
- `dispatch_strategy`：
  - `default`
  - `cheapest_first`

## 调度规则

### 1. 预算阻塞

如果满足以下任一条件，任务不会进入 `ready`：

- 模型未定价，且 `block_on_unpriced_model=true`
- 单次预计成本超过 `max_single_execution_cost`
- 累计成本已达到 `max_total_estimated_cost`
- 本次执行后预计累计成本会超过 `max_total_estimated_cost`

阻塞后：

- `scheduler_state = blocked`
- `next_action = adjust_budget`
- `reason` 写明预算阻塞原因

### 2. 最便宜优先

当 `dispatch_strategy=cheapest_first` 时：

- 调度器先筛出所有 `ready` 任务
- 按 `estimated_total_cost` 从低到高排序
- 成本未知的任务排在最后

这条规则只改变 ready 队列内部顺序，不会越过：

- `review_pending`
- `failed`
- `bridge_confirmation`
- `active`

这些更高优先级状态门槛。

## UI / CLI 变化

### 单项目 Web UI

新增“自动化预算策略”模块，可直接配置：

- 项目总预算
- 单次执行上限
- 调度策略
- 未定价模型阻塞开关
- 币种

任务检查器中的调度卡新增：

- 预算状态
- 预计 Prompt Token
- 预计成本
- 剩余项目预算

### Launcher 首页

项目卡新增：

- 调度策略
- 剩余预算
- 单次上限

### CLI

`aios status` 新增：

- 当前策略
- 总预算 / 单次预算
- 是否阻止未定价模型
- 剩余预算

## 测试计划

### 自动化测试

1. 初始化项目时自动生成 `runtime-policy.json`
2. 预算超限时任务从 `ready` 变为 `blocked`
3. `cheapest_first` 能改变 scheduler 的下一条 ready 任务
4. `run auto` 在 `cheapest_first` 下实际派发更便宜的 ready 任务
5. Web API 能读写 `/api/runtime-policy`
6. `status` CLI 输出策略字段

### 手工验收

1. 初始化项目并扫描
2. 在项目控制台设置：
   - 单次预算
   - 项目总预算
   - cheapest_first
3. 创建两条成本差异明显的 ready 任务
4. 点击“自动推进下一步”
5. 确认系统先派发更便宜的任务
6. 再把预算调到极低
7. 确认任务进入 blocked，原因显示预算阻塞

## 结论

P3-31 不是“成本统计的续集”，而是 AIOS 自动化真正开始具备调度约束。

它的价值在于把系统从：

- “知道花了多少”

推进到：

- “知道什么时候该停”
- “知道应该先跑哪条”

这也是后续做：

- provider 真实握手
- 多轮重试策略
- 模型性价比学习
- 全自动执行编排

之前必须先补上的基础层。
