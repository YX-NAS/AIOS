# P3-10 自动 Git 提交设计

生成时间：2026-07-02

## 目标

让 AIOS 在任务完成回写之后，进一步自动把本次任务产生的变更提交到 Git 仓库。

这一阶段的重点不是自动推送，也不是自动开 PR，而是把“本地任务完成 -> 本地 Git commit”接起来。

## 范围

本阶段实现：

- `aios run finish ... --auto-commit`
- `aios run approve ... --auto-commit`
- `aios run auto --auto-finish --auto-commit`
- `aios run TASK-ID --executor ... --auto-finish --auto-commit`
- Web UI 完成表单支持“自动提交 Git”
- 执行记录写入 Git 自动提交结果

本阶段不实现：

- 自动 `git push`
- 自动创建 PR
- 自动处理 merge conflict
- 自动拆分多个 commit

## 安全边界

自动 Git 提交只在以下条件满足时启用：

1. 当前目录是 Git 仓库
2. 执行开始前，非 `.aios/` 工作区是干净的
3. 任务完成后存在可提交变更

这里特意忽略 `.aios/` 的预先改动，因为 AIOS 在任务创建、Pack 生成、执行记录写入时会持续更新自己的元数据。如果把这些都当作“脏工作区”，自动提交在真实流程里几乎永远无法使用。

如果执行前已有非 `.aios/` 脏改动：

- 自动提交跳过
- 任务仍然正常完成
- 执行记录里会写明跳过原因

## 提交内容

当前策略：

- 提交任务完成时工作区中的全部变更路径
- 其中既包括业务代码，也包括 `.aios/` 的任务、执行、memory、changelog 更新

提交命名规则：

- subject: `aios: TASK-ID 任务标题`
- body 包含：
  - task id
  - task title
  - completion summary
  - changed paths

## 数据回写

执行记录新增或补全字段：

- `git_is_repo_before`
- `git_branch_before`
- `git_commit_before`
- `git_status_before`
- `git_is_clean_before`
- `git_branch_after`
- `git_commit_after`
- `auto_commit_enabled`
- `auto_commit_status`
- `auto_commit_reason`
- `auto_commit_paths`
- `auto_commit_subject`

## CLI 变化

支持：

```bash
aios run finish TASK-ID --summary "完成登录修复" --auto-commit
aios run approve TASK-ID --summary "确认交付" --verify-command "pytest -q" --auto-commit
aios run auto --executor codex-cli --auto-finish --summary "完成登录修复" --verify-command "pytest -q" --auto-commit
```

CLI 输出会补充：

- Git commit SHA
- branch
- 或跳过原因

## Web UI 变化

完成表单新增：

- `完成后自动提交 Git（仅在执行开始前工作区干净时生效）`

执行卡片显示：

- 自动提交状态
- 提交后版本

## 测试计划

### 自动化测试

1. 干净仓库中 `run finish --auto-commit` 成功提交
2. 执行前已有非 `.aios/` 改动时自动提交跳过
3. `run execute` + `auto_finish` + `auto_commit` 成功提交
4. API 返回 `git_commit` 和执行记录中的提交字段

### 手工验收

1. 初始化 Git 仓库
2. 创建任务并执行
3. 完成表单勾选“自动提交 Git”
4. 任务完成后检查：
   - `git log --oneline`
   - `.aios/executions.json`
   - Web UI 执行状态卡

## 下一步

P3-10 完成后，后续更接近“自动交付”的下一层是：

- `P3-11` 外部模型切换接管
- `P3-12` 自动 push / PR 策略
- `P3-9` 成本统计

也就是说，Git 本地提交打通后，AIOS 才开始真正具备“从任务到交付”的骨架。
