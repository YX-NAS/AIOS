# P3-14 自动 PR 草案设计

生成时间：2026-07-02

## 目标

在自动 commit 和自动 push 之后，让 AIOS 继续自动创建 Draft PR。

这一阶段只做 Draft PR，不做 Ready PR，更不做自动 merge。

## 范围

本阶段实现：

- `aios run finish ... --auto-pr`
- `aios run approve ... --auto-pr`
- `aios run auto --auto-finish --auto-commit --auto-push --auto-pr`
- Web UI 完成表单支持“自动创建 Draft PR”
- 执行记录写入 Draft PR 结果

本阶段不实现：

- 自动创建 Ready PR
- 自动 merge
- 自动 reviewer / label / milestone

## 前置条件

自动 PR 草案依赖：

1. 本次任务已经成功自动 push
2. `gh` CLI 可用
3. 当前分支和目标 base 分支不同

如果没有成功 push，AIOS 会直接跳过 Draft PR。

## 默认策略

- base branch 默认 `main`
- PR 标题：`[AIOS] TASK-ID 任务标题`
- PR body 包含：
  - task id
  - task title
  - completion summary

## 安全边界

当前只创建 Draft PR，理由：

- 这一步属于交付候选，而不是最终交付
- 在没有 reviewer / CI / repo policy 感知之前，不应默认把 AIOS 输出直接提升为 Ready PR

## 数据回写

执行记录新增：

- `auto_pr_enabled`
- `auto_pr_status`
- `auto_pr_reason`
- `auto_pr_url`
- `auto_pr_number`
- `auto_pr_base_branch`

## CLI 变化

新增：

```bash
aios run finish TASK-ID --summary "完成修复" --auto-commit --auto-push --auto-pr
```

补充：

- `--pr-base-branch main`

## Web UI 变化

完成表单新增：

- `Push 成功后自动创建 Draft PR`

执行状态卡显示：

- Draft PR 状态
- PR 链接

## 测试计划

### 自动化测试

1. 没有成功 push 时，Draft PR 自动跳过
2. CLI / API 返回 Draft PR 结果
3. 执行记录包含 `auto_pr_*` 字段

### 手工验收

1. 在特性分支执行任务
2. 勾选自动 commit / push / PR
3. 完成任务后检查：
   - 远端分支已更新
   - `gh pr view` 可看到 draft PR
   - `.aios/executions.json` 中记录了 PR URL

## 下一步

P3-14 完成后，更接近完整交付的下一步是：

- provider / session 级接管
- 成本统计
- PR 元数据增强

自动化主线会从“任务自动完成”进一步进入“交付候选自动生成”。
