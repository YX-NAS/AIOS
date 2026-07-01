# P3-4 任务树与拆解草案设计

生成时间：2026-07-02

## 目标

解决 AIOS 当前“任务拆解太平、拆解结果确认太轻、复杂目标难表达”的问题。

这一阶段要补齐 3 个能力：

1. 拆解草案持久化
2. 任务父子关系
3. 任务依赖关系

## 范围

本阶段实现：

- `.aios/task-plans.json`
- `task plan --draft`
- `task draft list/show/confirm/delete`
- Web 端拆解预览改为真实草案
- 确认创建时保留父任务和依赖关系
- `tasks.md` 显示父任务和依赖任务

本阶段不实现：

- 任务拖拽排序
- 甘特图 / 看板式依赖视图
- 自动基于依赖关系调度执行器
- launcher 首页跨项目任务树总览

## 数据结构

### 1. 草案文件

新增：

- `.aios/task-plans.json`

结构：

```json
{
  "drafts": []
}
```

单条 draft 最小字段：

- `draft_id`
- `goal`
- `priority`
- `status`
- `tasks`
- `created_at`
- `updated_at`
- `confirmed_at`

### 2. 任务新增字段

任务记录新增：

- `parent_task_id`
- `depends_on_task_ids`
- `plan_draft_id`
- `plan_node_id`

## CLI 入口

### 创建草案

```bash
aios task plan "开发会员积分系统，包含积分获取、积分扣减、明细查询和后台管理" --draft
```

### 仅预览

```bash
aios task plan "修复时间状态同步问题" --preview
```

### 管理草案

```bash
aios task draft list
aios task draft show DRAFT-20260702-001
aios task draft confirm DRAFT-20260702-001
aios task draft delete DRAFT-20260702-001
```

兼容行为：

- 现有 `aios task plan ...` 仍可直接创建正式任务
- `--preview` 仍然只看结果不落盘
- 新增 `--draft` 用于“先落草案，再确认”

## Web 行为

Web 中的目标拆解预览现在不再只是页面临时状态，而是：

1. 提交目标时先创建一条草案
2. 页面显示草案中的任务树和依赖信息
3. 点击确认时用 `draft_id` 正式创建任务
4. 点击取消时删除该草案

## 任务树规则

### 通用目标

默认规则：

- 第一条任务为主任务
- 后续任务默认挂在第一条任务下
- 依赖关系按流程顺序串联

### 系统类目标

例如：

```text
开发会员积分系统，包含积分获取、积分扣减、明细查询和后台管理
```

会生成：

- `scope`：梳理系统范围与模块边界
- `design`：设计核心数据与接口，依赖 `scope`
- 若干模块实现任务，依赖 `design`
- `testing`：依赖全部模块实现任务
- `record`：依赖 `testing`

### Bug 修复类目标

默认规则：

- 现象 / 影响范围
- 根因排查
- 修复
- 回归验证
- 记录与验收

依赖关系按线性顺序串联。

## 测试计划

### 自动化测试

1. `init` 后生成 `task-plans.json`
2. `task plan --draft` 能创建草案
3. `task draft confirm` 能正式生成任务
4. 系统类目标的模块任务依赖 `design`
5. bug 类目标保留顺序依赖
6. Web API 草案创建 / 查询 / 确认 / 删除可用

### 手工验收

1. 创建一个复杂目标草案
2. 查看 `task draft list`
3. `task draft show` 检查父子和依赖
4. 确认草案创建任务
5. 查看 `tasks.md`，确认依赖关系已写入
6. 在 Web 中预览拆解并取消，确认草案被删除

## 下一步

P3-4 补齐后，后续要把这些依赖关系真正用于：

- 自动执行排序
- 失败后阻断后续任务
- 依赖满足后自动推进下一条任务

这会是后续全自动化执行真正能站住脚的前提。
