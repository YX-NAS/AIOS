# P2 智能化设计方案

生成时间：2026-07-01

## 依赖关系

P2-2（路由学习）依赖 P2-1（模型评分）产出的分数数据。
P2-3（Git diff）和 P2-4（token 预估）互相独立，也不依赖评分。
推荐实现顺序：P2-1 → P2-2 → P2-3 → P2-4。

---

## P2-1 模型效果评分

### 目标

任务完成后可对使用的模型打分（1-5），评分写入 `.aios/model-scores.json`，作为路由学习的数据源。

### 数据模型

`.aios/model-scores.json`：

```json
[
  {
    "task_id": "TASK-20260701-003",
    "task_type": "simple_coding",
    "model": "deepseek-v4-pro",
    "score": 4,
    "note": "一次通过，输出干净",
    "scored_at": "2026-07-01T16:30:00+08:00"
  }
]
```

### 改动点

**新增文件**：`src/aios/core/scoring.py`

- `save_score(root, task_id, model, score, note=None)` — 追加一条评分到 `model-scores.json`
- `load_scores(root)` — 读取全部评分
- `model_score_summary(root, model_id=None)` — 按模型聚合统计（平均分、样本数、按任务类型拆分）

**CLI**：`src/aios/commands/complete.py`

- `aios complete TASK-ID --summary "..." --score 4 --score-note "一次通过"`
- `--score` 可选，1-5 整数；`--score-note` 可选备注
- 调用 `save_score()` 写入

**Web API**：`src/aios/core/webapp.py`

- `POST /api/complete` 增加 `score` 和 `score_note` 可选字段
- `GET /api/scores` 返回评分列表
- `GET /api/scores/summary` 返回按模型聚合的统计

**Web UI**：任务完成表单加评分行（5 个单选按钮 + 可选备注输入框）；任务检查器中显示历史评分。

**Launcher UI**：模型表格中增加"平均分"列，数据来自 `/api/scores/summary`。

### 测试

1. `test_complete_with_score_writes_model_scores` — complete 带 score，验证文件写入
2. `test_load_scores_and_summary` — 多条评分，验证聚合统计
3. `test_api_scores_endpoints` — 验证 API 返回格式

---

## P2-2 路由策略学习

### 目标

根据历史评分自动调整模型推荐顺序。评分高的模型在同类任务中排名提前，评分低的降级。

### 核心逻辑

在 `resolve_models_for_task()` 中，当全局模型库的 `task_types` 匹配到多个模型时，按评分加权排序而不是纯 rank。

**新增文件**：`src/aios/core/route_learning.py`

- `compute_model_weights(root)` — 读取 `model-scores.json`，按 (model, task_type) 计算加权分
  - 公式：`weight = avg_score * ln(sample_count + 1)`
  - 样本太少时（<3 条）权重退化为 0，使用原始 rank
  - 返回 `{(model_id, task_type): float}` 的 dict
- `apply_learned_order(candidates, task_type, weights, original_rank)` — 对候选模型按 weight 降序排列，weight=0 的保持原 rank 顺序

**改动点**：`src/aios/core/router.py`

- `resolve_models_for_task()` 调用 `compute_model_weights()` 和 `apply_learned_order()`
- 学习权重仅在样本充足（>=3 条同类评分）时生效，否则保持 `models.json` 的 rank 排序
- 学习结果不写回 `models.json`，纯粹是路由时的运行时调整

**CLI**：新增 `aios route --explain TASK-ID`，输出推荐理由中包含"基于 N 条历史评分，权重调整：xxx"

**Web UI**：路由卡片中显示"学习调整"标签和样本数。

### 不做的事

- 不自动修改 `models.json` 的 rank（用户手动设的 rank 优先）
- 不删除或禁用模型（评分低只是排序靠后）
- 学习权重是软信号，和 rank 加权合并，不是唯一决定因素

### 测试

1. `test_compute_model_weights_with_enough_samples` — 3+ 条评分，验证权重计算
2. `test_compute_model_weights_with_few_samples` — 2 条评分，权重退化为 0
3. `test_resolve_models_uses_learned_weights` — 验证排序调整
4. `test_resolve_models_preserves_rank_without_scores` — 无评分时保持原始 rank

---

## P2-3 Git diff 分析

### 目标

`aios scan` 时读取最近 git diff，自动识别变更文件并关联到正在进行的任务。

### 数据模型

`file-index.json` 的每个文件条目新增字段：

```json
{
  "path": "src/app/api/chat/route.ts",
  "type": "backend",
  "language": "typescript",
  "importance": "high",
  "summary": "后端或服务入口相关文件",
  "size_bytes": 3420,
  "git_status": "modified"
}
```

`git_status` 取值：`"modified"` / `"added"` / `"deleted"` / `"untracked"` / `null`（无变更或非 git 仓库）

`scan` 报告 `summary` 新增：

```json
{
  "changed_files": 5,
  "git_branch": "main",
  "git_commit": "a1b2c3d"
}
```

### 改动点

**`src/aios/core/scanner.py`**：`scan_project()` 末尾调用 `collect_git_status(root)`

**新增文件**：`src/aios/core/git_utils.py`

- `is_git_repo(root)` — 检查 `.git` 存在
- `collect_git_status(root)` — 执行 `git status --porcelain`，返回 `{path: status}` dict
- `get_current_branch(root)` — `git rev-parse --abbrev-ref HEAD`
- `get_current_commit(root)` — `git rev-parse --short HEAD`
- `get_recent_diff(root, max_files=50)` — `git diff --name-only HEAD~1`，返回最近一次提交的变更文件列表

**`src/aios/core/context_builder.py`**：`choose_relevant_files()` 优先选择 `git_status != null` 的文件（变更文件相关性更高）

**CLI**：`aios scan` 输出增加"变更文件: N"

**Web UI**：项目状态面板显示"最近变更: N 个文件"；文件索引中变更文件高亮标记。

### 降级策略

- 非 git 仓库：跳过，不报错
- `git` 命令不存在：跳过
- 仓库太浅（无 commit）：跳过

### 测试

1. `test_scan_includes_git_status` — git 仓库内 scan，验证 `git_status` 字段
2. `test_scan_non_git_repo_skips_git` — 非仓库目录，`git_status` 全为 null
3. `test_context_pack_prefers_changed_files` — 有变更文件时，Pack 优先包含
4. `test_git_utils_branch_and_commit` — 验证分支和 commit 读取

---

## P2-4 上下文窗口预估

### 目标

Pack 生成时估算 token 数，超出模型上下文窗口时发出警告。

### 数据模型

`models.json` 中每个模型新增可选字段：

```json
{
  "id": "gpt-5.5",
  "context_window": 200000,
  ...
}
```

默认模型上下文窗口值（写死在代码里，`reset` 时使用）：

| 模型 | context_window |
|------|---------------|
| gpt-5.5 | 200000 |
| claude | 200000 |
| deepseek-v4-pro | 128000 |
| deepseek-v4-flash | 128000 |
| gpt-5.4-mini | 128000 |
| minimax-m2.7-highspeed | 32000 |

Pack 生成后额外返回：

```json
{
  "path": ".aios/context-packs/TASK-xxx-gpt-5.5.md",
  "token_estimate": 8520,
  "context_window": 200000,
  "window_usage_pct": 4.3,
  "warning": null
}
```

当 `token_estimate > context_window * 0.9` 时，`warning` 设为 `"Context pack exceeds 90% of model context window"`。

### 改动点

**`src/aios/core/context_builder.py`**：

- `build_context_pack()` 返回值从 `Path` 改为 `dict`（包含 path + token 元信息）
- 新增 `estimate_tokens(text: str) -> int` — 按中文 1.5 token/字、英文 0.75 token/word 估算
- 查询模型的 `context_window`（从 `models.json` 读，缺失时用 128000 兜底）

**`src/aios/core/models.py`**：

- `normalize_models()` 保留 `context_window` 字段（int 或 null）
- `default_model_library()` 填入默认值

**CLI**：`aios pack` 输出增加 token 估算和窗口使用率；超阈值时 stderr 警告

**Web API**：`POST /api/pack` 返回值增加 token 元信息

**Web UI**：Pack 生成后在操作反馈中显示 token 估算

### 精度说明

初版用规则估算（中英混合公式），不调真实 tokenizer。精度要求是"量级正确"，即 1 万 vs 10 万的区分，不需要精确到百位。后续可接入 tiktoken 提升精度。

### 测试

1. `test_estimate_tokens_chinese_text` — 中文文本估算合理
2. `test_estimate_tokens_english_code` — 代码文本估算合理
3. `test_pack_returns_token_estimate` — pack 返回 token 元信息
4. `test_pack_warns_on_large_context` — 估算超 90% 窗口时 warning 非空
5. `test_pack_no_warning_within_window` — 正常范围内 warning 为 null

---

## 实现顺序与验收

| 步骤 | 内容 | 验收标准 |
|------|------|---------|
| 1 | P2-1 模型评分 | complete 带 score 写入；API 可查；聚合统计正确 |
| 2 | P2-2 路由学习 | 评分>=3 条时排序调整；无评分时保持原序 |
| 3 | P2-3 Git diff | scan 包含 git_status；Pack 优先选变更文件；非 git 仓库不报错 |
| 4 | P2-4 token 预估 | pack 返回 token 估算和窗口使用率；超 90% 有警告 |

每步完成后补对应单元测试和 API 测试，`python3 -m pytest` 全绿才进入下一步。
