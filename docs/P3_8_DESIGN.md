# P3-8 自动完成收口设计

生成时间：2026-07-02

## 目标

让 AIOS 从“自动派发并执行”继续推进到“执行成功后按规则自动完成回写”。

这一阶段的重点，是把原来必须人工执行的：

- review 通过
- 跑验证命令
- `run finish`

收敛成受控的自动收口动作。

## 范围

本阶段实现：

- `aios run auto --auto-finish --summary "..."`
- `aios run TASK-ID --executor ... --auto-finish --summary "..."`
- `aios run approve TASK-ID --summary "..."`
- `POST /api/run/dispatch` 支持自动收口参数
- `POST /api/run/execute` 支持自动收口参数
- 单项目 Web UI 的“自动推进下一步”按钮支持自动收口

本阶段不实现：

- 自动阅读 diff 后自行生成可信 summary
- 自动判断业务验收是否真的通过
- 自动合并 PR / 自动发版
- 自动 Git commit

## 收口规则

自动收口分两种路径：

### 1. 刚执行完成的任务

如果当前调度步骤是 `run_executor`：

1. 派发执行器
2. 执行器返回成功，任务进入 `review_pending`
3. 若启用 `auto_finish`：
   - 可选执行 `verify_command`
   - 验证通过后自动调用 `finish`
   - 任务进入 `done`

### 2. 已存在的待复核任务

如果当前调度步骤是 `review_finish` 且启用了 `auto_finish`：

1. 定位当前调度器建议的 `review_pending` 任务
2. 可选执行 `verify_command`
3. 验证通过后自动调用 `finish`

## 安全边界

自动收口必须满足：

- 显式提供 `summary`
- 任务当前执行状态为 `review_pending`

如果配置了 `verify_command`：

- 命令退出码非 0 时，不会自动完成任务
- 执行记录会写入测试命令和失败摘要
- 任务继续保持 `review_pending`

也就是说，这一版的自动收口是“可中止”的，不会因为验证失败而误把任务改成 `done`。

## CLI 变化

新增能力：

```bash
aios run auto --executor codex-cli --auto-finish --summary "完成登录修复" --verify-command "pytest -q"
aios run TASK-ID --executor codex-cli --auto-finish --summary "完成登录修复" --verify-command "pytest -q"
aios run approve TASK-ID --summary "确认交付" --verify-command "pytest -q"
```

说明：

- `auto`：按调度器建议推进下一步，可能是派发，也可能是完成 `review_pending`
- `approve`：针对单个任务执行自动收口
- `verify-command`：执行本地验证命令，结果写回执行记录

## API 变化

新增 / 扩展字段：

- `POST /api/run/dispatch`
- `POST /api/run/execute`

支持参数：

- `auto_finish`
- `summary`
- `actual_model`
- `verify_command`
- `score`
- `score_note`

返回补充：

- `progressed`
- `auto_finished`
- `verification`
- `reason`

## Web UI 变化

任务检查器中的主按钮从“只负责派发”升级为“自动推进下一步”：

- 如果下一步是 `run_executor`，则派发执行
- 如果下一步是 `review_finish` 且表单中已填写总结，则自动完成回写
- 如果填写了测试命令，则会先执行验证命令

## 测试计划

### 自动化测试

1. 单任务执行器支持 `--auto-finish`
2. `run auto` 在 `review_pending` 状态下支持自动收口
3. 验证命令失败时，任务保持 `review_pending`
4. Web API 返回 `progressed` / `auto_finished` / `verification`

### 手工验收

1. 创建任务并配置执行器
2. 运行自动执行
3. 填写总结和测试命令
4. 点击“自动推进下一步”
5. 若验证通过，任务进入 `done`
6. 若验证失败，任务仍停留在 `review_pending`

## 下一步

P3-8 完成后，后续真正接近“全自动执行”的重点会变成：

- `P3-9` 成本与执行统计
- `P3-10` 自动 Git 提交
- `P3-11` 外部模型切换与会话接管

也就是说，AIOS 的自动化主线会从“执行入口自动化”进入“交付闭环自动化”。
