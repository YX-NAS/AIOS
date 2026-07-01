# P3-2 ccswitch 适配层开发方案

生成时间：2026-07-01

## 目标

在已经跑通的半自动执行链路上，再往前推进一步：

- 不自动控制 `ccswitch`
- 不自动调用 Codex / Claude Code
- 先把 AIOS 当前任务、推荐模型、fallback、执行记录整理成稳定的适配输出

这一阶段的目标不是“自动切换”，而是“减少人工抄模型名、抄任务信息、抄执行上下文”。

## 设计边界

本阶段做：

- 新增 `ccswitch` 适配输出结构
- CLI 和 Web UI 都能导出该结构
- 导出结果与当前任务执行记录绑定
- 记录导出时间、目标模型、fallback 模型和上下文路径

本阶段不做：

- 不直接调用桌面端 `ccswitch`
- 不假设 `ccswitch` 一定存在稳定 CLI
- 不接管 Codex / Claude Code 窗口或会话
- 不自动完成任务

## 开发方案

### 1. 新增适配输出文件

每个项目新增目录：

- `.aios/ccswitch/`

每次导出生成一个 JSON 文件，命名建议：

- `TASK-ID-模型名-ccswitch.json`

最小字段：

- `task_id`
- `task_title`
- `execution_id`
- `recommended_model`
- `fallback_models`
- `context_pack_path`
- `handoff_path`
- `operator_note`
- `exported_at`
- `format_version`

设计原则：

- 保持字段稳定、可被脚本消费
- 只输出 AIOS 已确认的事实，不伪造 `ccswitch` 私有字段
- 如果后续确认 `ccswitch` 有稳定脚本接口，再做第二层转换

### 2. 新增适配服务层

新增一个独立的导出模块，负责：

1. 读取任务
2. 读取最近执行记录
3. 如果没有执行记录，拒绝导出并提示先 `run --manual`
4. 生成 JSON 文件
5. 返回文件路径和导出内容

这样做的原因：

- 不把 `ccswitch` 导出逻辑塞进 `run` 主流程
- 后续如果要接别的模型切换器，也能复用这一层

### 3. CLI 入口

新增命令：

```bash
aios ccswitch export TASK-ID
```

可选参数：

- `--model`
- `--stdout`

行为：

- 默认读取最近执行记录里的 `planned_model`
- 如果带 `--model`，允许覆盖导出目标模型
- 默认写文件
- 如果带 `--stdout`，同时把 JSON 输出到终端，方便脚本接管

### 4. Web UI 入口

在任务检查器中新增辅助按钮：

- `导出 ccswitch 适配文件`
- `复制 ccswitch JSON`

位置放在“开始执行”和“复制交接单”附近，但不替代主执行入口。

### 5. 执行记录联动

执行记录增加两个可选字段：

- `ccswitch_export_path`
- `ccswitch_exported_at`

导出后回写到最近执行记录，便于用户知道：

- 这个任务是否已经导出过
- 导出的文件在哪
- 是什么时候导出的

### 6. 风险控制

这一阶段必须明确：

- `ccswitch` 当前是否存在稳定 CLI 不是前提条件
- 即使没有 CLI，这一层也仍然有价值，因为它把切换所需信息标准化了
- 真正自动调用前，必须先验证：
  - CLI 是否官方支持
  - 参数是否稳定
  - 切换后外部工具是否能立即感知配置变更

## 任务拆分

### P3-2.1 数据结构与文件输出

完成标准：

- 新增 `.aios/ccswitch/`
- 能生成 JSON 文件
- 文件内容字段稳定

### P3-2.2 导出服务层

完成标准：

- 给定 `task_id` 能导出对应 `ccswitch` JSON
- 没有执行记录时返回清晰错误

### P3-2.3 CLI 入口

完成标准：

- `aios ccswitch export TASK-ID` 可用
- 支持 `--stdout`

### P3-2.4 Web UI 入口

完成标准：

- 页面可导出 JSON 文件
- 页面可一键复制 JSON

### P3-2.5 执行记录回写

完成标准：

- 导出后执行记录有导出路径和时间
- 任务检查器可见

### P3-2.6 文档与验收

完成标准：

- README 和操作手册补导出流程
- 说明“适配输出 != 自动切换”

## 测试计划

### 自动化测试

1. 导出服务
- 有执行记录时能导出 JSON
- 无执行记录时返回错误
- 导出字段完整

2. CLI
- `aios ccswitch export TASK-ID` 生成文件
- `--stdout` 输出合法 JSON

3. Web API
- 导出接口返回文件路径和 JSON 内容
- 导出后执行记录被更新

4. Web UI
- 导出按钮不影响原有执行流程
- 复制按钮可拿到 JSON 文本

5. 兼容性
- 没有 `ccswitch` 目录时自动创建
- 旧项目升级后无需手工迁移

### 手工验收

1. 初始化项目并创建任务
2. `run --manual` 开始执行
3. 导出 `ccswitch` 适配文件
4. 在页面或终端确认：
   - 推荐模型正确
   - fallback 正确
   - Context Pack 路径正确
   - handoff 路径正确
5. 回到 AIOS，确认执行记录出现导出信息

## 验收标准

满足以下条件才算通过：

1. 不依赖 `ccswitch` CLI 也能完成导出
2. 用户不需要再手工整理模型切换信息
3. 导出内容可追溯到当前任务和执行记录
4. 不破坏现有 `run --manual` / `run finish` 流程
