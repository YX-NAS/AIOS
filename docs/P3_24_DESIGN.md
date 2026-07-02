# P3-24 Bridge 恢复信号自动确认设计

## 目标

在 `P3-23` 已经具备本地恢复 signal 证据后，新增一层受控自动化：

- 当 AIOS 已检测到 bridge 恢复 signal；
- 且操作者显式允许自动确认；
- 系统可把 bridge 从 `signal_detected` 自动收口到 `confirmed_ready`；
- 然后重新进入调度评估。

这一步仍然不是读取 `ccswitch` 内部状态，也不保证 provider、会话和业务上下文百分之百正确。  
它只是在已有本地证据成立时，减少一次重复人工确认。

## 默认边界

- 默认关闭
- 只在 `signal_detected` 时触发
- 只把 bridge 确认状态更新为 `confirmed_ready`
- 不会顺手自动派发下一条新任务
- 不会绕过已有 `review_pending` / `failed` / `active` 安全门

## CLI 变化

新增参数：

```bash
aios run auto --auto-confirm-bridge-signal
```

行为：

1. 调度器先看当前 `next_action`
2. 如果是 `validate_resumed_session`
3. 且检测到恢复 signal
4. 且显式带了 `--auto-confirm-bridge-signal`
5. 则自动执行一次：

```text
pending_confirmation / signal_detected -> confirmed_ready
```

然后输出 bridge 已自动确认，并重新计算当前调度状态。

## Web API 变化

新增 `/api/run/dispatch` 请求字段：

- `auto_confirm_bridge_signal: boolean`

返回字段新增：

- `auto_confirmed_bridge`

当本次动作只是自动确认 bridge，而不是派发新任务时：

- `progressed = true`
- `dispatched = false`
- `auto_confirmed_bridge = true`

## Web UI 变化

`自动推进下一步` 所用表单新增一个选项：

- `检测到 Bridge 恢复信号时自动确认切换已就绪`

反馈区会明确显示：

- 已自动确认 bridge
- 当前任务
- bridge 确认状态
- 调度器下一步动作

## 状态机变化

原有：

```text
pending_confirmation -> confirmed_ready / confirmed_failed
signal_detected -> 等待人工确认
```

新增受控分支：

```text
signal_detected --(auto_confirm_bridge_signal)--> confirmed_ready
```

后续调度回到既有规则：

- 若任务本身仍是 `running`，则显示 `monitor_running`
- 不会直接把任务标记完成
- 不会自动跨到下一条任务

## 测试计划

### 自动化测试

1. CLI 自动确认
   - bridge 已写 signal
   - 执行 `aios run auto --auto-confirm-bridge-signal`
   - 校验执行记录变成 `confirmed_ready`

2. API 自动确认
   - `/api/run/dispatch` 传 `auto_confirm_bridge_signal=true`
   - 返回 `auto_confirmed_bridge = true`
   - `dispatched = false`
   - 调度器重新计算为 `monitor_running`

3. 兼容性
   - 不带该参数时，原有阻塞行为不变
   - `pending_confirmation` 仍需人工确认

## 风险与限制

- signal 只能证明恢复命令已被拉起，不能证明一定恢复到了正确会话
- 因此自动确认必须保持显式开关，而不是默认开启
- 如果未来能稳定读取 `ccswitch` 或执行器会话状态，再考虑把这一步升级成更强证据链
