# P3-26 历史会话候选与恢复建议设计

## 目标

在已有 `attach / resume / continue-latest` 基础上，补一层可追溯的历史会话候选能力：

- AIOS 自动从已有执行记录里整理出“已知会话”
- 针对当前任务给出历史候选排序
- 支持显式使用最佳历史候选生成恢复命令
- Web UI 支持查看候选并一键挂接

这一步不依赖读取外部 App 内部状态，只依赖 AIOS 已经掌握的执行记录，因此稳定性比桌面自动化更高。

## 核心行为

### 1. 历史会话候选

候选来源：

- 手动 `run attach`
- 执行器自动提取到的 session id / session name

排序规则：

- 同执行器优先
- 同任务优先
- 同任务标题优先
- 同推荐模型优先
- 最近更新时间优先

### 2. 历史恢复模式

`run resume` 新增可选参数：

```bash
aios run resume TASK-ID --history-fallback
```

行为：

1. 如果当前任务已经挂接会话，优先使用当前挂接会话
2. 如果没有挂接会话，且显式启用 `--history-fallback`
3. AIOS 会从历史候选里选出最佳会话
4. 生成 `mode=history` 的恢复命令
5. 在执行记录中留下这次历史恢复来源

如果没有候选，再回退到 `continue-latest` 或报错。

### 3. 会话候选查看

新增 CLI：

```bash
aios run sessions TASK-ID
```

新增 API：

```text
GET /api/run/sessions/:task_id
```

返回：

- `session_ref`
- `executor_id`
- `task_id`
- `task_title`
- `model`
- `match_score`
- `session_source`
- `attached_at`

### 4. Web UI

单项目任务检查器新增：

- `历史会话候选` 卡片
- `复制最佳历史会话恢复命令`
- `在终端继续最佳历史会话`
- 每条候选支持 `挂接此历史会话`

## 数据模型

本轮不新增独立持久化文件。  
历史会话候选直接从 `.aios/executions.json` 派生，避免维护第二套真相源。

执行记录新增辅助字段：

- `executor_resume_history_session_ref`
- `executor_resume_history_session_kind`
- `executor_resume_history_task_id`
- `executor_resume_history_task_title`
- `executor_resume_history_execution_id`

这些字段只记录“最近一次历史恢复建议用了谁”，便于审计。

## 测试计划

### 自动化测试

1. CLI 历史恢复
   - 先在任务 A 上挂接会话
   - 再在任务 B 上执行 `run resume --history-fallback`
   - 断言返回 `mode=history`

2. CLI 候选列表
   - 执行 `run sessions TASK-ID`
   - 断言能列出历史候选

3. API 候选与恢复
   - `GET /api/run/sessions/:task_id` 返回排序后的候选
   - `POST /api/run/resume` 传 `history_fallback=true` 返回 `mode=history`

4. Web UI 入口
   - 页面包含历史候选区域和历史恢复按钮

### 验收标准

- 历史会话可被系统识别和排序
- 没有当前挂接会话时，可显式使用最佳历史候选恢复
- 操作者能在 Web UI 直接看到并挂接候选
- 不破坏现有 `attached` / `latest` 恢复逻辑

## 边界

- 这是“历史候选恢复”，不是“自动确认恢复正确”
- 不会默认启用
- 不会替代 bridge 确认链
- 不会自动猜测外部窗口是否真的切换成功
