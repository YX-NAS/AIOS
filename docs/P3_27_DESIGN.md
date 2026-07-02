# P3-27 执行器真实 CLI 可用性探测设计

## 目标

把执行器从“静态配置”推进到“真实可接管”。

当前 AIOS 已经能：

- 配置执行器
- 调起执行器
- 记录日志
- 恢复会话

但在自动派发前，系统并不知道：

- 二进制是否真的存在
- CLI 是否能正常响应
- 当前环境里有哪些执行器实际上可用

P3-27 补的就是这层运行时真相。

## 核心能力

### 1. 运行时可用性

对命令型执行器新增运行时探测：

- `binary` 是否在 PATH 中可找到
- 可选 `healthcheck_args` 是否能执行成功

当前内置默认：

- `codex-cli` 使用 `codex --version`
- `claude-code-cli` 使用 `claude --version`

### 2. 执行器 Doctor

新增 CLI：

```bash
aios executor doctor
aios executor doctor codex-cli
```

输出：

- 是否 available
- binary 路径
- healthcheck 状态
- healthcheck 命令
- healthcheck 输出
- 失败原因

### 3. 自动派发安全门

`aios run auto` 在选择默认命令型执行器时，不再只看配置表：

- 只会选择运行时 `available=true` 的命令型执行器
- 如果当前没有可用命令型执行器，会直接停止推进
- 明确提示先运行 `aios executor doctor`

这一步能避免系统把任务自动派发给一个根本不存在的 CLI。

### 4. 状态摘要

执行器摘要新增：

- `available_executor_count`

单项目状态接口和 launcher 项目摘要会带出这个数量，方便总览当前机器到底有多少真实可用执行器。

## 数据模型

本轮不新增持久化文件。  
运行时可用性是动态派生，不写回配置。

执行器配置新增可选字段：

- `healthcheck_args`

用于定义探测命令参数，例如：

```json
["--version"]
```

## 测试计划

### 自动化测试

1. 运行时探测
   - mock `which` 和 `subprocess.run`
   - 断言 `executor_summary()` 返回 `available=true/false`

2. Doctor CLI
   - `aios executor doctor codex-cli`
   - 断言输出包含 `available` 和 `healthcheck`

3. 自动派发阻塞
   - mock 所有命令型执行器 binary 不存在
   - `aios run auto`
   - 断言不会派发，并提示先检查执行器

4. 兼容性
   - 现有可用执行器仍能正常派发
   - 旧执行器库即使没有 `healthcheck_args` 也能自动补默认值

## 边界

- 这只是“CLI 可用性探测”，不是“业务执行成功保证”
- `--version` 成功不代表模型登录态一定可用
- 后续如果要继续推进全自动执行，还需要补：
  - provider / auth 状态检查
  - 实际 prompt 提交后的 session 回执
  - 验证失败后的自动重试策略
