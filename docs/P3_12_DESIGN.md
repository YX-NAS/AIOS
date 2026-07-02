# P3-12 自动 Push / 远程交付设计

生成时间：2026-07-02

## 目标

在本地自动 commit 的基础上，让 AIOS 可以继续把当前分支自动 push 到远端。

这一阶段先解决“本地完成 -> 远端分支更新”，不直接自动开 PR。

## 范围

本阶段实现：

- `aios run finish ... --auto-push`
- `aios run approve ... --auto-push`
- `aios run auto --auto-finish --auto-commit --auto-push`
- Web UI 完成表单支持“自动 push 当前分支”
- 执行记录写入 push 结果

本阶段不实现：

- 自动创建 PR
- 自动 merge
- 自动推送到受保护主分支

## 安全边界

自动 push 依赖前置条件：

1. 这次动作已经产生新的自动 commit
2. 远端存在，例如 `origin`
3. 当前分支不是 `main` / `master`，除非显式允许

当前默认会跳过 `main` / `master`，原因很直接：

- 自动提交到主分支风险过高
- 在没有仓库策略感知和审查门禁之前，不应该默认把 AIOS 变成主分支直接投递器

## CLI 变化

新增参数：

```bash
aios run finish TASK-ID --summary "完成修复" --auto-commit --auto-push
aios run auto --executor codex-cli --auto-finish --summary "完成修复" --verify-command "pytest -q" --auto-commit --auto-push
```

补充参数：

- `--push-remote origin`
- `--allow-protected-push`

## 数据回写

执行记录补充：

- `auto_push_enabled`
- `auto_push_status`
- `auto_push_reason`
- `auto_push_remote`
- `auto_push_branch`

## Web UI 变化

完成表单新增：

- `完成后自动 push 当前分支（默认跳过 main/master）`

执行状态卡显示：

- 自动 Push 状态
- Push 远端

## 测试计划

### 自动化测试

1. 特性分支上 `--auto-push` 成功 push
2. `main/master` 默认跳过
3. API / CLI 返回 push 结果

### 手工验收

1. 在特性分支执行任务
2. 勾选自动 commit 和自动 push
3. 完成任务后检查：
   - `git log`
   - `git status`
   - `git ls-remote origin`

## 下一步

P3-12 完成后，真正的远程交付闭环还差：

- PR 草案创建
- 分支策略感知
- 受保护分支策略

也就是从“push 远端”继续推进到“可审查交付”。
