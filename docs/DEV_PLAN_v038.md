# AIOS 系统开发方案 v0.38

生成时间：2026-07-03
基于版本：v0.37.0

---

## 1. 方案概述

### 1.1 目标

本轮迭代核心目标是**从半自动管理中枢向自动执行中枢推进**，在保持现有半自动流程可用的前提下，强化三大关键能力：

1. **仓库上下文检索增强** — 让 Context Pack 更精准、更智能
2. **执行安全与可观测性** — 让自动执行更可靠、更可追踪
3. **全自动执行链路闭环** — 缩短人工参与环节，逼近全自动

### 1.2 借鉴来源

基于同类项目对比分析和最新行业趋势，本轮主要借鉴：

| 借鉴方向 | 来源项目/论文 | AIOS 落地方式 |
|-----------|-------------|-------------|
| 仓库地图与有界搜索 | FastContext, aider | 构建仓库级 context map，分层索引，bounded search |
| 弹性上下文管理 | LongSeeker, OpenDev | Context Pack 动态压缩，token 预算控制 |
| 执行护栏与卡死检测 | OpenHands, Conductor | 自动派发循环检测，超时/异常兜底 |
| 跨模型分工与审查 | Agent Council, aider | 任务类型驱动模型选择，跨模型审查工作流 |
| 声明式工作流 | Conductor (Microsoft) | YAML 定义的任务编排模板 |

### 1.3 设计原则

1. **不破坏现有流程**：所有新增能力作为可选增强，默认不影响已有半自动链路
2. **CLI-first，渐进增强 Web UI**：核心能力先在 CLI 稳定，再同步到 Web
3. **每步可观测、可回退**：自动化环节保留人工介入点和回退路径
4. **最小依赖，最大兼容**：优先使用标准库和已有依赖，避免引入重量级框架

---

## 2. 模块规划

### 2.1 P3-36：仓库上下文检索增强（Repository Context Engine）

**痛点**：当前 Context Pack 依赖 file-index.json 做全量文件列举，大仓库下无关文件多、token 浪费严重。

**方案**：

1. **仓库结构化地图** (`repo-map.json`)
   - 按目录层级构建项目骨架图
   - 标注关键文件（入口点、配置文件、核心模块）
   - 结合 git history 标记近期变更热点

2. **有界上下文搜索** (`bounded-search`)
   - 根据任务类型和目标关键词进行相关性检索
   - 分层上下文：项目层 → 模块层 → 文件层 → 代码块层
   - 自动排除构建产物、依赖目录、.aios 元数据

3. **智能文件选取** (`smart-file-selection`)
   - 结合任务标题、描述、类型推断所需文件范围
   - 支持手动标注关键文件，提升选取精度
   - 生成选取理由，便于人工审核

**数据模型**：

```json
{
  "repo_map": {
    "root": ".",
    "modules": [
      {
        "name": "core",
        "path": "src/aios/core",
        "role": "核心逻辑层",
        "entry_points": ["main.py", "__init__.py"],
        "key_files": ["executions.py", "tasks.py", "models.py"],
        "hot_files": ["executions.py"],
        "sub_modules": []
      }
    ],
    "generated_at": "2026-07-03T10:00:00"
  },
  "search_index": {
    "tokens": { "execution": ["executions.py", "dispatch.py"], "task": ["tasks.py", "scheduler.py"] },
    "symbols": { "prepare_execution_record": "executions.py", "scheduler_summary": "scheduler.py" },
    "imports": {}
  }
}
```

**CLI 命令**：

```bash
aios repo map              # 生成仓库地图
aios repo search "关键词"   # 有界搜索相关文件
aios pack TASK-ID --smart  # 使用智能选取生成 Context Pack
```

### 2.2 P3-37：执行安全护栏增强（Execution Guard）

**痛点**：自动派发到 CLI 执行器后，缺少进程级监控、卡死检测和资源控制。

**方案**：

1. **卡死检测** (`stuck-detection`)
   - 监控执行器 stdout/stderr 输出频率
   - 超过 N 秒无输出时触发告警
   - 自动分析循环重复输出模式（doom-loop detection）

2. **资源控制** (`resource-control`)
   - CPU/内存使用监控（跨平台）
   - 子进程树追踪，防止孤儿进程
   - 可配置的资源上限和自动终止策略

3. **执行心跳** (`execution-heartbeat`)
   - 执行器定时写入心跳文件
   - AIOS 独立进程读取心跳判断存活
   - 异常终止后自动清理和通知

**CLI 命令**：

```bash
aios guard status TASK-ID     # 查看执行护栏状态
aios guard config              # 配置护栏参数
aios run auto --guard          # 启用护栏的自动派发
```

### 2.3 P3-38：跨模型审查工作流（Cross-Model Review）

**痛点**：当前只做模型路由推荐，缺少"用另一个模型审查前一个模型产出"的结构化流程。

**方案**：

1. **审查任务自动创建** (`review-task`)
   - 任务完成后自动生成审查子任务
   - 审查任务路由到与原任务类型匹配的审查模型
   - 审查结论包含通过/需修改/建议

2. **审查工作流模板** (`review-workflow`)
   - 编码任务：用不同模型审查代码质量和正确性
   - 测试任务：用不同模型审查测试覆盖度和边界
   - 文档任务：用低成本模型审查准确性和完整性

3. **审查结果回写** (`review-feedback`)
   - 审查结论写入原任务
   - 关联执行记录和审查模型信息
   - 支持审查不通过后自动触发修复流程

**CLI 命令**：

```bash
aios review create TASK-ID           # 创建审查任务
aios review run TASK-ID              # 执行审查
aios review workflow --define         # 定义审查工作流
```

### 2.4 P3-39：声明式工作流引擎（Workflow Engine）

**痛点**：当前任务执行是单条线性派发，复杂多步骤流程需要人工编排。

**方案**：

1. **工作流定义** (`workflow.yaml`)
   - YAML 声明式定义多步骤执行流
   - 支持串行、并行、条件分支
   - 内置模板：编码→测试→审查→提交

2. **工作流执行引擎** (`workflow-engine`)
   - 解析 YAML 定义生成执行计划
   - 按步骤自动派发到对应执行器
   - 步骤间传递上下文和执行结果

3. **工作流模板库** (`workflow-templates`)
   - 预置常见工作流模板
   - 支持项目级自定义模板
   - 模板可导入导出

**工作流 YAML 示例**：

```yaml
name: "完整功能开发流程"
steps:
  - id: implement
    type: task_execution
    executor: codex-cli
    model: gpt-5.5
    auto_finish: true
    verify_command: "pytest tests/"

  - id: review
    type: cross_review
    depends_on: [implement]
    executor: claude-code-cli
    model: claude
    review_focus: ["correctness", "code_quality"]

  - id: commit
    type: git_operations
    depends_on: [review]
    auto_commit: true
    auto_push: true
    auto_pr: true
    condition: "review.passed == true"
```

**CLI 命令**：

```bash
aios workflow run TASK-ID --template full-dev
aios workflow define --name my-workflow
aios workflow list-templates
```

### 2.5 P3-40：弹性上下文管理（Adaptive Context）

**痛点**：Context Pack 生成后固定不变，执行过程中如果 token 超限或上下文膨胀无法自适应调整。

**方案**：

1. **Token 预算控制** (`token-budget`)
   - 根据目标模型上下文窗口设置预算上限
   - Pack 生成时严格控制在预算内
   - 支持分层裁剪：先裁文件层，再裁模块层

2. **上下文动态压缩** (`context-compaction`)
   - 执行过程中监控实际 token 消耗
   - 触发阈值时自动压缩非关键上下文
   - 保留任务目标、验收标准和最近变更

3. **上下文质量评分** (`context-quality`)
   - 相关性评分：文件与任务目标的语义匹配度
   - 完整性评分：是否覆盖了所有关键模块
   - 冗余度评分：可裁减的无关内容比例

**CLI 命令**：

```bash
aios pack TASK-ID --budget 100000        # token 预算限制
aios pack TASK-ID --quality-report       # 生成质量报告
aios pack TASK-ID --compact              # 紧凑模式
```

### 2.6 P3-41：执行会话自动续接增强（Session Continuity）

**痛点**：执行中断后需要人工介入恢复会话，不能自动续接。

**方案**：

1. **会话状态持久化** (`session-persistence`)
   - 执行中断前自动保存会话状态快照
   - 支持从快照自动恢复执行
   - 快照包含：当前步骤、已生成文件、待处理事项

2. **智能恢复策略** (`smart-resume`)
   - 根据执行器类型选择最佳恢复方式
   - 优先级：--continue > --resume session_id > 历史候选
   - 恢复前自动验证执行器可用性和项目状态

3. **会话健康检查** (`session-health`)
   - 恢复前验证项目 git 状态
   - 检查目标文件是否被外部修改
   - 冲突检测和自动合并建议

**CLI 命令**：

```bash
aios session snapshot TASK-ID     # 保存会话快照
aios session restore TASK-ID      # 从快照恢复
aios session health TASK-ID       # 检查会话健康状态
```

---

## 3. 实施优先级

### P0 — 立即启动（本轮必做）

| 编号 | 模块 | 范围 | 预估工作量 |
|------|------|------|-----------|
| P3-36 | 仓库上下文检索增强 | repo map + bounded search + smart selection | 大 |
| P3-37 | 执行安全护栏 | stuck detection + heartbeat + resource control | 中 |
| P3-40 | 弹性上下文管理 | token budget + quality scoring | 中 |

### P1 — 本轮重点

| 编号 | 模块 | 范围 | 预估工作量 |
|------|------|------|-----------|
| P3-38 | 跨模型审查工作流 | review task + workflow template | 中 |
| P3-41 | 执行会话续接增强 | session snapshot + smart resume | 中 |

### P2 — 后续迭代

| 编号 | 模块 | 范围 | 预估工作量 |
|------|------|------|-----------|
| P3-39 | 声明式工作流引擎 | YAML workflow + execution engine | 大 |
| P0-3 | 错误处理增强 | CLI 清晰错误信息 + Web API 统一格式 | 小 |
| P0-1 | pytest 补齐 | 核心模块测试覆盖 | 中 |

---

## 4. 技术选型

| 能力 | 选型 | 理由 |
|------|------|------|
| 仓库地图生成 | 纯 Python，基于 ast/pathlib | 无外部依赖，跨平台 |
| 文件相关性搜索 | TF-IDF + 关键词匹配 | 轻量级，无需向量数据库 |
| 进程监控 | subprocess + psutil (可选) | 优先 subprocess，psutil 作为可选增强 |
| 工作流定义 | PyYAML | 标准库外最常见 YAML 库 |
| HTML Web UI | 纯 HTML/JS（现状保持不变） | 零依赖，即开即用 |

---

## 5. 文件结构变更

```
src/aios/
├── core/
│   ├── repo_map.py          # 新增：仓库地图生成
│   ├── bounded_search.py   # 新增：有界上下文搜索
│   ├── guard.py            # 新增：执行护栏
│   ├── review.py           # 新增：跨模型审查
│   ├── workflow_engine.py  # 新增：工作流引擎
│   ├── context_adaptive.py # 新增：弹性上下文
│   └── session_persist.py  # 新增：会话持久化
├── commands/
│   ├── repo.py             # 新增：仓库命令
│   ├── guard.py            # 新增：护栏命令
│   ├── review.py           # 新增：审查命令
│   ├── workflow.py         # 新增：工作流命令
│   └── session.py          # 新增：会话命令
└── main.py                 # 修改：注册新命令
```

---

## 6. 验收标准

### P3-36 验收标准

- `aios repo map` 能生成结构化的仓库地图文件
- `aios repo search "关键词"` 能返回相关性排序的文件列表
- `aios pack TASK-ID --smart` 生成的 Pack 比默认 Pack 的文件数减少 30%+，且不遗漏关键文件
- 大仓库（500+ 文件）下 bounded search 能在 2 秒内完成

### P3-37 验收标准

- 自动派发执行器时，超过可配置时间无输出触发卡死告警
- 循环输出重复模式（同一行重复 5 次+）触发 doom-loop 检测
- 执行器异常终止后，心跳文件能反映真实状态
- `aios guard status` 能展示当前执行的安全状态

### P3-40 验收标准

- `aios pack TASK-ID --budget 50000` 生成的 Pack token 数在预算内
- 质量报告能给出相关性、完整性、冗余度三项评分
- Pack 超出模型上下文窗口时给出明确警告

### P3-38 验收标准

- `aios review create TASK-ID` 能自动创建并路由审查任务
- 审查结论结构化为通过/需修改/建议
- 审查不通过时任务状态回退到 todo 并记录原因

### P3-41 验收标准

- 执行中断后可从快照恢复会话
- 恢复前自动检查 git 状态和执行器可用性
- 优先级正确的恢复策略选择

---

## 7. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| 仓库地图不准确导致遗漏关键文件 | 执行质量下降 | 支持人工标注和调整，结合 git history |
| 有界搜索在大仓库慢 | 用户体验差 | 缓存索引，增量更新 |
| 进程监控跨平台兼容性 | 某些平台不可用 | 优先 subprocess，psutil 作为可选增强 |
| 自动恢复可能误操作 | 安全隐患 | 恢复前展示差异，支持 dry-run 模式 |

---

## 8. 后续路线简图

```
v0.37 (当前)                  v0.38 (本轮)                    v0.39+ (下轮)
┌─────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│ 半自动执行中枢    │  →   │ 增强型自动执行中枢    │  →   │ 全自动开发操作系统    │
│                 │      │                     │      │                     │
│ ✓ 任务拆解/路由  │      │ + 仓库上下文检索     │      │ + 声明式工作流引擎   │
│ ✓ Context Pack  │      │ + 执行安全护栏      │      │ + 跨项目编排        │
│ ✓ 执行器适配    │      │ + 弹性上下文管理     │      │ + 多人协作          │
│ ✓ 自动恢复链    │      │ + 跨模型审查        │      │ + 插件市场          │
│ ✓ Bridge 桥接   │      │ + 会话智能续接      │      │ + 远程执行节点      │
│ ✓ 成本/预算     │      │                     │      │                     │
└─────────────────┘      └─────────────────────┘      └─────────────────────┘
```
