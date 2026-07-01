# P3 半自动执行层设计

生成时间：2026-07-01

## 目标

把 AIOS 从“任务管理 + Pack/Handoff 生成器”推进到“可追踪的半自动执行中枢”。

这一阶段仍然保留：

- 人工切换 `ccswitch`
- 人工在 Codex / Claude Code 中执行
- 人工确认测试和完成总结

这一阶段开始新增：

- 执行记录文件 `.aios/executions.json`
- 统一手动执行入口 `aios run --manual`
- 执行状态可观测：prepared / running / finished / cancelled

## P3-0：执行稳定层

### 数据结构

每个项目新增 `.aios/executions.json`：

```json
{
  "executions": []
}
```

单条记录最小字段：

- `execution_id`
- `task_id`
- `task_title`
- `mode`
- `status`
- `planned_model`
- `actual_model`
- `fallback_models`
- `pack_path`
- `handoff_path`
- `started_at`
- `finished_at`
- `operator_note`
- `test_command`
- `test_result`
- `completion_summary`
- `updated_at`

### 状态模型

- `prepared`：已生成执行记录、Pack、交接单，但还没确认开始执行
- `running`：已开始执行，任务状态同步切到 `running`
- `finished`：已完成回写，任务状态同步切到 `done`
- `cancelled`：本版先保留字段，不提供显式入口

### 兼容规则

- 旧项目没有 `executions.json` 时按空记录处理
- 旧 `handoff` 仍可用，但只负责生成交接单
- 旧 `complete` 仍可用；如果任务存在活跃执行记录，会优先把该记录收口为 `finished`

## P3-1：统一手动执行入口

### CLI

新增命令：

```bash
aios run --manual TASK-ID --start
aios run status TASK-ID
aios run finish TASK-ID --summary "..."
```

`run --manual` 的行为：

1. 读取任务和路由结果
2. 生成或复用 Context Pack
3. 生成或复用 handoff
4. 创建或更新一条执行记录
5. 输出模型、Pack、交接单和下一步人工提示

`run finish` 的行为：

1. 接收完成总结
2. 可选记录实际模型、测试命令、测试结果和评分
3. 更新执行记录为 `finished`
4. 复用既有完成回写逻辑更新 `tasks.json`、`memory.md`、`changelog.md`

### Web API

新增接口：

- `POST /api/run/manual`
- `GET /api/run/task/:task_id`
- `POST /api/run/finish`

接口原则：

- 直接返回任务最近一次执行记录
- 任务还没有执行记录时返回 `null`
- 保持 `POST /api/handoff` 和 `POST /api/complete` 兼容

### Web UI

单项目页面改动：

- “开始执行”成为任务主按钮
- “生成并复制任务交接单”保留为辅助动作
- 任务检查器新增执行状态面板
- 完成表单补充：
  - 实际模型
  - 测试命令
  - 测试结果
  - 模型评分
  - 评分备注

### Launcher

launcher 首页项目摘要新增：

- 活跃执行数
- 最近执行状态
- 最近执行更新时间

仍然只做摘要和跳转，不直接承载单项目执行详情。

## 测试与验收

自动化测试覆盖：

- 执行记录读写与无文件兼容
- `aios run --manual` / `run finish`
- 单项目 Web API 的开始执行、查询执行、完成回写
- launcher 项目摘要中的执行统计

本阶段验收标准：

1. 能从一个任务开始，生成执行记录、Context Pack 和交接单
2. 能把任务切到 `running`
3. 能记录实际模型、测试命令、测试结果和完成总结
4. 能把执行记录收口成 `finished`
5. launcher 首页能实时显示执行摘要
