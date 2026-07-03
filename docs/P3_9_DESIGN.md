# P3-9 成本与执行统计设计

生成时间：2026-07-03

## 目标

AIOS 现在已经能：

- 记录执行状态
- 自动派发
- 自动收口
- 验证失败后 fallback 重试

但系统仍然缺少一层关键可观测性：

- 一共跑了多少 token
- 每次执行大约花了多少钱
- 执行耗时多长
- 多项目下哪个项目更重、更慢、更贵

P3-9 的目标就是补齐这层执行统计。

## 范围

本轮实现：

- 全局模型库支持维护定价元数据
- 执行记录写入：
  - prompt token 估算
  - output token 估算
  - total token 估算
  - 估算输入成本
  - 估算输出成本
  - 估算总成本
  - 执行时长
- `execution_summary()` 聚合：
  - token 总量
  - 成本总量
  - 平均执行时长
  - 最近执行时长
- 单项目 Web UI 执行状态卡显示这些字段
- launcher 项目卡片显示累计成本、累计 token、平均/最近执行时长
- CLI `status` / `model doctor` 同步展示

本轮不实现：

- 真实 provider 账单拉取
- 精确 tokenizer
- 按 PR / 分支 / 目录的成本归因
- 成本预算阈值告警

## 设计原则

### 1. 成本来源于模型库，不硬编码

价格不写死在系统里，而是挂在全局模型库中维护：

- `input_cost_per_1m`
- `output_cost_per_1m`
- `cost_currency`

这样可以在模型升级后由用户自己更新。

### 2. 先做估算，不伪装成账单真相

这轮所有数字都明确是“估算”：

- prompt token：按 Context Pack 文本估算
- output token：按执行输出文本估算
- cost：按模型库配置价格估算

### 3. 执行时长必须是真实起止

CLI 执行器场景中，时长按真实执行前后时间记录，不再只写一个静态时间戳。

## 数据结构

### 模型库新增字段

```json
{
  "input_cost_per_1m": 2.5,
  "output_cost_per_1m": 10.0,
  "cost_currency": "USD"
}
```

### 执行记录新增字段

```json
{
  "prompt_token_estimate": 8421,
  "output_token_estimate": 260,
  "total_token_estimate": 8681,
  "input_cost_per_1m": 2.5,
  "output_cost_per_1m": 10.0,
  "estimated_input_cost": 0.021053,
  "estimated_output_cost": 0.0026,
  "estimated_total_cost": 0.023653,
  "cost_currency": "USD",
  "duration_seconds": 3.184
}
```

## 统计口径

### Prompt Token

从执行时关联的 Context Pack 内容估算。

### Output Token

从执行器 stdout / stderr 文本估算。

### 成本

公式：

- `estimated_input_cost = prompt_tokens / 1_000_000 * input_cost_per_1m`
- `estimated_output_cost = output_tokens / 1_000_000 * output_cost_per_1m`
- `estimated_total_cost = input + output`

### 执行时长

- CLI 执行器：真实开始到退出
- 手动执行：完成回写时按 `started_at -> finished_at` 推导

## 前端展示

### 单项目执行状态卡

新增：

- Prompt Token
- 输出 Token
- 总 Token
- 估算输入成本
- 估算总成本
- 执行时长

### launcher 项目卡片

新增：

- 累计估算成本
- 累计 Token
- 平均执行时长
- 最近执行时长

### 模型库

模型库新增可编辑字段：

- 输入成本 / 1M
- 输出成本 / 1M
- 币种

## CLI 展示

### `aios status`

新增：

- 总 prompt token
- 总 output token
- 总估算成本
- 平均执行时长
- 最近执行时长

### `aios model list / doctor`

新增模型定价信息展示。

## 测试计划

### 自动化测试

1. 模型库持久化
   - 定价字段创建后可保存
   - update 后可保存

2. 执行统计
   - 执行一次 CLI 任务
   - 写出 prompt/output/total token
   - 写出 estimated cost
   - 写出 duration

3. 状态汇总
   - `aios status` 输出 Usage 行

4. launcher API
   - 模型 API 返回定价字段

### 手工验收

1. 在 launcher 中给一个模型配置价格
2. 执行一个任务
3. 打开单项目执行状态卡
4. 确认 token / cost / duration 已显示
5. 回到 launcher
6. 确认项目卡片累计成本与时长已刷新

## 结论

P3-9 不是“财务系统”，而是让 AIOS 从“会执行”变成“知道自己执行了多少、花了多少、慢在哪里”。

这一步补完后，后续做：

- 成本预算
- 调度策略优化
- 模型性价比学习

才有稳定基础。
