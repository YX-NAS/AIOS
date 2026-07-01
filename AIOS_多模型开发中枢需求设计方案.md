# AIOS 多模型开发中枢需求设计方案

## 1. 项目名称

**AIOS：AI Development Operating System**

中文名：**AI 开发中枢 / 多模型开发操作系统**

---

## 2. 项目定位

AIOS 是一个面向 AI 编程的多模型开发中枢。

它的核心目标是：

> 让同一个软件项目可以在 GPT、DeepSeek、Claude、MiniMax 等多个模型之间连续开发，而不丢失项目上下文，并且可以根据任务类型、复杂度、成本和模型能力自动选择最合适的模型执行开发任务。

AIOS 不直接替代 Codex、Cursor、Claude Code、CC Switch，而是作为它们上层的 **项目知识层、上下文构建层、任务调度层和模型路由层**。

---

## 3. 核心问题

### 3.1 项目上下文绑定单一模型

当前 ChatGPT Project、Codex 或其他 AI 编程工具中，项目上下文往往绑定在单一模型或单一 Provider 上。

问题包括：

- ChatGPT Project 中的上下文主要只能 GPT 使用；
- 切换到 DeepSeek / MiniMax 等第三方模型后，项目状态容易丢失；
- 第三方模型无法理解项目历史决策；
- 多账号切换虽然可以保留部分项目，但跨 Provider 的项目连续性不稳定。

### 3.2 多模型开发割裂

不同模型适合不同任务：

- GPT：适合架构设计、复杂推理、核心开发；
- DeepSeek：适合代码实现、批量修改、脚本开发；
- MiniMax：适合文档、总结、格式化、低成本任务；
- Claude：适合长文档理解、代码审查、复杂上下文处理。

但目前缺少一个围绕同一项目统一调度这些模型的开发中枢。

### 3.3 AI 开发缺少长期记忆

AI 经常不知道：

- 为什么当初这么设计；
- 哪些文件不能乱改；
- 哪些接口不能破坏；
- 当前任务进展到哪里；
- 上一次 AI 修改了什么；
- 哪些 Bug 已经修复过；
- 哪些决策不能被轻易推翻。

### 3.4 上下文成本高

直接把整个项目丢给模型会造成：

- Token 浪费；
- 成本高；
- 模型注意力分散；
- 低价模型上下文不够用；
- 多模型之间无法复用统一上下文。

AIOS 要解决的是：

> 根据任务动态生成最小但足够的 Context Pack。

---

## 4. 产品目标

### 4.1 第一阶段目标：本地 CLI MVP

实现一个本地 CLI + 文件系统型 AIOS，可以在项目目录中运行。

主要能力：

1. 初始化项目 AIOS 目录；
2. 扫描项目结构；
3. 生成项目上下文；
4. 管理开发任务；
5. 记录架构决策；
6. 根据任务生成不同模型可用的 Context Pack；
7. 根据模型路由规则推荐执行模型；
8. 执行完成后回写项目状态。

### 4.2 第二阶段目标：Web UI / Desktop UI

增加可视化管理界面。

主要能力：

1. 多项目管理；（已交付：launcher 首页）
2. 多模型 Provider 管理；（已交付：全局模型库 CRUD）
3. 模型成本统计；
4. 任务看板；（已交付：Web UI 任务台）
5. Context Pack 预览；（已交付：Web UI Pack 列表 + 一键复制）
6. AI 开发日志；
7. Git Diff 分析；
8. 模型效果评分。

### 4.3 第三阶段目标：完整 AI 开发操作系统

长期目标：

1. 自动任务拆解；
2. 多模型协作开发；
3. 自动 Code Review；
4. 自动测试；
5. 自动提交 Git；
6. 自动生成 Release Note；
7. 模型自动路由；
8. 成本 / 质量 / 速度三维优化。

---

## 5. 系统总体架构

```text
AIOS
│
├── Project Layer 项目层
│   ├── 项目注册
│   ├── 项目元信息
│   ├── 技术栈识别
│   ├── 目录结构扫描
│   └── 项目状态管理
│
├── Context Layer 上下文层
│   ├── 项目总上下文
│   ├── 架构说明
│   ├── 文件索引
│   ├── 决策记录
│   ├── 当前任务上下文
│   └── 模型专用 Context Pack
│
├── Task Layer 任务层
│   ├── 任务创建
│   ├── 任务拆解
│   ├── 任务状态流转
│   ├── 任务优先级
│   └── 任务验收标准
│
├── Router Layer 模型路由层
│   ├── 任务分类
│   ├── 复杂度判断
│   ├── 模型能力匹配
│   ├── 成本评估
│   └── 推荐执行模型
│
├── Execution Layer 执行层
│   ├── Codex 调用
│   ├── 外部模型调用
│   ├── Shell 命令
│   ├── 测试命令
│   └── Git 操作
│
├── Memory Layer 记忆层
│   ├── 长期项目记忆
│   ├── 开发日志
│   ├── 决策日志
│   ├── 模型表现记录
│   └── 历史任务记录
│
└── Provider Layer 模型供应层
    ├── GPT
    ├── DeepSeek
    ├── Claude
    ├── MiniMax
    ├── Gemini
    └── 本地模型
```

---

## 6. 本地目录结构设计

每个项目根目录下生成：

```text
.aios/
  project.yaml
  context.md
  architecture.md
  decisions.md
  tasks.md
  rules.md
  memory.md
  changelog.md
  file-index.json
  model-routing.yaml
  providers.yaml
  context-packs/
    gpt.md
    deepseek.md
    claude.md
    minimax.md
  logs/
    2026-06-30.md
  reports/
    scan-report.md
```

---

## 7. 核心文件说明

### 7.1 project.yaml

```yaml
project:
  name: "gaokao-admission-ai"
  description: "北京高考志愿推荐系统"
  type: "web-app"
  stage: "development"
  language:
    - "typescript"
    - "python"
  framework:
    frontend: "nextjs"
    backend: "fastapi"
    database: "sqlite"
  owner: "Le Nas"

aios:
  version: "0.1.0"
  initialized_at: "2026-06-30"
  last_scan_at: null
  default_model: "gpt-5.5"
  default_context_pack: "gpt"
```

### 7.2 context.md

项目总上下文。

```md
# 项目上下文

## 项目目标

本项目用于构建一个高考志愿推荐系统，基于考生成绩、排名、历史录取数据、院校专业目录等信息，生成志愿填报建议。

## 当前阶段

当前处于 MVP 开发阶段。

## 技术栈

- 前端：Next.js
- 后端：FastAPI
- 数据库：SQLite
- 数据处理：Python
- 部署：本地 / 云服务器

## 当前重点

完成录取概率计算模块。

## 禁止事项

- 不要随意修改已有数据库字段。
- 不要删除历史数据导入脚本。
- 不要破坏现有 API 返回格式。
```

### 7.3 architecture.md

```md
# 架构说明

## 总体架构

前端负责数据展示与用户交互，后端负责推荐算法、数据查询和报告生成。

## 模块划分

- data-import：导入高考数据
- admission-engine：录取概率计算
- recommendation-engine：志愿推荐
- report-generator：生成 Markdown / PDF 报告
- web-ui：用户界面
```

### 7.4 decisions.md

```md
# 架构决策记录

## 2026-06-30

### 决策

使用 SQLite 作为 MVP 数据库。

### 原因

数据规模可控，方便本地开发和迁移。

### 影响

后续如果数据量扩大，可迁移到 PostgreSQL。
```

### 7.5 tasks.md

```md
# 任务列表

## 正在进行

- [ ] 实现录取概率计算模块
  - 优先级：高
  - 推荐模型：GPT-5.5
  - 验收标准：
    - 可以根据排名、院校、专业生成概率区间
    - 有基础测试用例
    - 输出结果可解释

## 下一步

- [ ] 增加院校筛选功能
- [ ] 增加 PDF 报告导出
- [ ] 增加前端结果页

## 已完成

- [x] 初始化项目结构
- [x] 完成数据导入脚本
```

### 7.6 model-routing.yaml

```yaml
routing_rules:
  architecture:
    preferred_models:
      - gpt-5.5
      - claude
    fallback_models:
      - deepseek-v4-pro
    max_cost_level: high

  complex_coding:
    preferred_models:
      - gpt-5.5
    fallback_models:
      - deepseek-v4-pro
    max_cost_level: high

  simple_coding:
    preferred_models:
      - deepseek-v4-pro
      - gpt-5.4-mini
    fallback_models:
      - minimax-m2.7-highspeed
    max_cost_level: medium

  batch_edit:
    preferred_models:
      - deepseek-v4-flash
      - minimax-m2.7-highspeed
    fallback_models:
      - deepseek-v4-pro
    max_cost_level: low

  documentation:
    preferred_models:
      - minimax-m2.7-highspeed
      - deepseek-v4-flash
    fallback_models:
      - gpt-5.5
    max_cost_level: low

  code_review:
    preferred_models:
      - gpt-5.5
      - claude
    fallback_models:
      - deepseek-v4-pro
    max_cost_level: high
```

---

## 8. 功能模块需求

### 8.1 项目初始化

命令：

```bash
aios init
```

功能：

- 在当前目录创建 `.aios/`；
- 生成默认配置文件；
- 自动识别项目语言和框架；
- 创建初始上下文文件。

输入：

```bash
aios init --name gaokao-admission-ai --type web-app
```

输出：

```text
AIOS project initialized.
Created .aios/
Created project.yaml
Created context.md
Created tasks.md
Created decisions.md
```

### 8.2 项目扫描

命令：

```bash
aios scan
```

功能：

- 扫描目录结构；
- 识别技术栈；
- 读取 README；
- 读取 package.json / pyproject.toml / requirements.txt；
- 生成 file-index.json；
- 更新 context.md；
- 生成 scan-report.md。

需要忽略：

```text
node_modules/
.git/
dist/
build/
coverage/
.venv/
.env
```

file-index.json 示例：

```json
{
  "generated_at": "2026-06-30T22:00:00Z",
  "files": [
    {
      "path": "src/app/page.tsx",
      "type": "frontend",
      "language": "typescript",
      "importance": "high",
      "summary": "首页入口文件"
    },
    {
      "path": "backend/main.py",
      "type": "backend",
      "language": "python",
      "importance": "high",
      "summary": "FastAPI 主入口"
    }
  ]
}
```

### 8.3 任务创建

命令：

```bash
aios task create "实现录取概率计算模块"
```

功能：

- 创建任务；
- 自动判断任务类型；
- 自动判断复杂度；
- 推荐模型；
- 写入 tasks.md；
- 生成任务 ID。

任务结构：

```yaml
task:
  id: "TASK-20260630-001"
  title: "实现录取概率计算模块"
  type: "complex_coding"
  priority: "high"
  status: "todo"
  recommended_model: "gpt-5.5"
  context_requirements:
    - "architecture.md"
    - "file-index.json"
    - "rules.md"
  acceptance_criteria:
    - "实现概率计算函数"
    - "增加测试用例"
    - "输出解释性结果"
```

### 8.4 任务分类

任务类型：

```text
architecture
complex_coding
simple_coding
batch_edit
bug_fix
code_review
testing
documentation
data_processing
ui_design
deployment
```

分类规则：

```text
包含 架构 / 重构 / 模块设计 → architecture
包含 修复 / bug / 报错 → bug_fix
包含 测试 / test / pytest → testing
包含 文档 / README / 说明 → documentation
包含 批量 / 替换 / 格式化 → batch_edit
包含 页面 / UI / 样式 → ui_design
包含 部署 / docker / nginx → deployment
```

### 8.5 模型路由

命令：

```bash
aios route TASK-20260630-001
```

输出：

```text
Task: 实现录取概率计算模块
Type: complex_coding
Complexity: high
Recommended model: gpt-5.5
Fallback model: deepseek-v4-pro
Reason:
- 涉及核心算法
- 需要理解业务规则
- 需要保持项目上下文一致
```

路由判断维度：

| 维度 | 说明 |
|---|---|
| 任务类型 | 架构、代码、文档、测试等 |
| 复杂度 | low / medium / high |
| 上下文依赖 | 是否需要完整项目上下文 |
| 风险等级 | 是否影响核心逻辑 |
| 成本限制 | low / medium / high |
| 模型能力 | 代码、推理、长上下文、速度 |
| Provider 状态 | 是否可用、是否限额 |

### 8.6 Context Pack 生成

命令：

```bash
aios pack TASK-20260630-001 --model gpt-5.5
```

生成：

```text
.aios/context-packs/TASK-20260630-001-gpt.md
```

Context Pack 内容：

```md
# AIOS Context Pack

## 目标任务

实现录取概率计算模块。

## 推荐模型

GPT-5.5

## 项目背景

本项目是北京高考志愿推荐系统，用于根据考生成绩、排名、历史录取数据生成志愿建议。

## 当前开发状态

已完成数据导入脚本，正在开发录取概率计算模块。

## 相关文件

- backend/admission_engine.py
- backend/models.py
- backend/tests/test_admission_engine.py
- .aios/architecture.md
- .aios/rules.md

## 必读规则

- 不要修改数据库字段。
- 不要破坏 API 返回结构。
- 新增逻辑必须包含测试。

## 开发要求

1. 实现 probability_score 函数。
2. 输出 safety / stable / risky 三种区间。
3. 增加测试用例。
4. 更新 changelog。

## 验收标准

- 测试通过。
- 代码结构清晰。
- 结果可解释。
```

不同模型的 Context Pack 策略：

| 模型 | Context Pack 特点 |
|---|---|
| GPT | 完整、包含背景、决策、约束 |
| DeepSeek | 精简、偏代码文件和明确任务 |
| MiniMax | 更短，适合文档/总结 |
| Claude | 长上下文，包含更多设计说明 |

### 8.7 执行结果回写

命令：

```bash
aios complete TASK-20260630-001
```

功能：

- 更新 tasks.md；
- 更新 changelog.md；
- 更新 decisions.md；
- 重新扫描项目；
- 生成任务总结。

输入：

```bash
aios complete TASK-20260630-001 --summary "完成录取概率计算模块，新增测试"
```

回写 changelog.md：

```md
## 2026-06-30

### TASK-20260630-001

完成内容：

- 新增 admission_engine.py
- 实现 probability_score
- 增加 test_admission_engine.py
- 通过基础测试

影响范围：

- backend/admission_engine.py
- backend/tests/test_admission_engine.py
```

---

## 9. CLI 命令设计

```bash
aios init
aios scan
aios status
aios task create "任务名称"
aios task list
aios task show TASK-ID
aios route TASK-ID
aios pack TASK-ID --model gpt-5.5
aios complete TASK-ID
aios log
aios memory update
aios context rebuild
aios provider list
aios provider add
aios config
```

---

## 10. 技术栈建议

### 10.1 MVP 技术栈

```text
语言：Python 3.10+（原建议 3.11+，MVP 代码不依赖 3.11 专属特性，为兼容当前本地环境下调到 3.10+）
CLI：Typer
配置：YAML
Markdown：markdown / frontmatter
文件扫描：pathlib
Git 集成：GitPython
数据库：SQLite（后续阶段）
测试：pytest
终端美化：Rich
```

原因：

- 开发快；
- 跨平台；
- 适合本地 CLI；
- 容易被 Codex 开发；
- 后续可扩展 API 和 Web UI。

### 10.2 后续 Web UI

```text
前端：Next.js
后端：FastAPI
数据库：SQLite / PostgreSQL
桌面端：Tauri / Electron
```

---

## 11. 数据模型

### 11.1 Project

```python
class Project:
    id: str
    name: str
    description: str
    root_path: str
    type: str
    stage: str
    languages: list[str]
    frameworks: dict
    created_at: datetime
    updated_at: datetime
```

### 11.2 Task

```python
class Task:
    id: str
    title: str
    description: str
    type: str
    status: str
    priority: str
    complexity: str
    recommended_model: str
    fallback_models: list[str]
    acceptance_criteria: list[str]
    created_at: datetime
    updated_at: datetime
```

### 11.3 ModelProfile

```python
class ModelProfile:
    name: str
    provider: str
    strengths: list[str]
    weaknesses: list[str]
    cost_level: str
    context_window: int
    best_for: list[str]
```

### 11.4 ContextPack

```python
class ContextPack:
    id: str
    task_id: str
    model: str
    content: str
    token_estimate: int
    files_included: list[str]
    created_at: datetime
```

---

## 12. 模型能力配置

```yaml
models:
  gpt-5.5:
    provider: openai
    cost_level: high
    context_quality: high
    coding: high
    reasoning: high
    documentation: high
    best_for:
      - architecture
      - complex_coding
      - code_review
      - bug_fix

  deepseek-v4-pro:
    provider: deepseek
    cost_level: low
    context_quality: medium
    coding: high
    reasoning: medium
    documentation: medium
    best_for:
      - simple_coding
      - batch_edit
      - testing
      - data_processing

  minimax-m2.7-highspeed:
    provider: minimax
    cost_level: low
    context_quality: medium
    coding: medium
    reasoning: medium
    documentation: high
    best_for:
      - documentation
      - formatting
      - summary

  claude:
    provider: anthropic
    cost_level: high
    context_quality: high
    coding: high
    reasoning: high
    documentation: high
    best_for:
      - long_context
      - code_review
      - architecture
```

---

## 13. 开发流程

### 13.1 标准流程

```text
aios init
↓
aios scan
↓
aios task create "开发功能"
↓
aios route TASK-ID
↓
aios pack TASK-ID --model 推荐模型
↓
复制 Context Pack 给 Codex / GPT / DeepSeek
↓
模型开发
↓
运行测试
↓
aios complete TASK-ID
↓
AIOS 回写上下文
```

### 13.2 未来自动流程

```text
用户输入任务
↓
AIOS 识别任务
↓
AIOS 选择模型
↓
AIOS 生成 Context Pack
↓
AIOS 调用模型
↓
AIOS 执行代码修改
↓
AIOS 运行测试
↓
AIOS 生成总结
↓
AIOS 回写上下文
```

---

## 14. Codex 开发提示词

下面这段可以直接给 Codex：

```text
你现在要开发一个名为 AIOS 的本地 CLI 项目。

项目目标：
构建一个面向 AI 编程的多模型开发中枢。它可以在项目目录中生成 .aios 目录，扫描项目结构，管理任务，记录决策，生成不同模型可用的 Context Pack，并根据任务类型推荐模型。

技术栈：
- Python 3.11+
- Typer 作为 CLI 框架
- PyYAML 处理 YAML
- Rich 美化终端输出
- pytest 做测试
- pathlib 做文件扫描

请按以下阶段开发：

第一阶段：
1. 初始化 Python 项目结构。
2. 实现 aios init。
3. 实现 .aios 目录生成。
4. 生成默认 project.yaml、context.md、tasks.md、decisions.md、rules.md、model-routing.yaml。

第二阶段：
1. 实现 aios scan。
2. 扫描项目文件。
3. 忽略 node_modules、.git、dist、build、.venv 等目录。
4. 生成 file-index.json。
5. 识别 package.json、requirements.txt、pyproject.toml。

第三阶段：
1. 实现 aios task create。
2. 自动生成 TASK-ID。
3. 识别任务类型。
4. 写入 tasks.md 或 tasks.yaml。

第四阶段：
1. 实现 aios route。
2. 根据 model-routing.yaml 推荐模型。
3. 输出推荐原因。

第五阶段：
1. 实现 aios pack。
2. 根据任务和模型生成 context-packs/{task-id}-{model}.md。
3. GPT 版本要更完整。
4. DeepSeek 版本要更精简。
5. MiniMax 版本偏文档和总结。

第六阶段：
1. 实现 aios complete。
2. 更新任务状态。
3. 写入 changelog.md。
4. 更新 memory.md。

代码要求：
- 模块化设计。
- 每个命令独立文件。
- 增加基础测试。
- 所有文件操作要有异常处理。
- 不要引入复杂数据库，第一版只用文件系统。
```

---

## 15. 推荐项目目录

```text
aios/
  pyproject.toml
  README.md
  src/
    aios/
      __init__.py
      main.py
      commands/
        init.py
        scan.py
        task.py
        route.py
        pack.py
        complete.py
      core/
        project.py
        scanner.py
        task_manager.py
        router.py
        context_builder.py
        memory.py
      utils/
        file_utils.py
        yaml_utils.py
        markdown_utils.py
        token_utils.py
      templates/
        project.yaml
        context.md
        tasks.md
        decisions.md
        rules.md
        model-routing.yaml
  tests/
    test_init.py
    test_scan.py
    test_task.py
    test_route.py
    test_pack.py
```

---

## 16. MVP 验收标准

第一版完成后，必须支持：

```bash
aios init
aios scan
aios task create "实现登录功能"
aios route TASK-ID
aios pack TASK-ID --model gpt-5.5
aios complete TASK-ID
```

并且项目中生成：

```text
.aios/
  project.yaml
  context.md
  tasks.md
  decisions.md
  rules.md
  model-routing.yaml
  file-index.json
  context-packs/
  changelog.md
  memory.md
```

---

## 16.1 方案合理性 Review 结论

### 总体判断

方案方向合理，核心价值明确：用本地项目知识层、任务层和 Context Pack 生成能力，把不同 AI 模型的开发协作统一到同一个项目状态中。

### 需要收紧的点

1. **第一版不直接调用真实模型。**
   MVP 的交付目标应是“生成可用上下文和路由建议”，而不是自动执行模型开发。真实 Provider 调用、额度管理和自动改代码放到后续阶段。

2. **任务数据需要机器可读。**
   `tasks.md` 适合人读，但不适合作为稳定状态源。MVP 增加 `tasks.json`，由 CLI 读写；`tasks.md` 作为同步生成的人类视图。

3. **路由配置需要机器可读。**
   `model-routing.yaml` 保留给人编辑；MVP 同时生成 `model-routing.json` 作为无外部依赖的运行配置，避免第一版必须安装 YAML 解析库。

4. **模型名称是配置，不是承诺。**
   `gpt-5.5`、`deepseek-v4-pro` 等先作为路由标签使用，不代表当前系统已经接入对应 Provider。

5. **执行层边界后移。**
   Shell、Git、自动测试和自动提交属于高风险能力。MVP 只记录任务完成总结和项目记忆，不自动修改业务项目。

### 修改后的 MVP 范围

MVP 交付一个本地 Python CLI，并补充一个轻量 Web UI：

- `aios init`：初始化 `.aios/` 目录和默认文件；
- `aios scan`：扫描项目结构，生成 `file-index.json` 和 `reports/scan-report.md`；
- `aios status`：查看 AIOS 项目状态；
- `aios task create/list/show`：创建、查看任务；
- `aios route`：根据任务类型推荐模型；
- `aios pack`：生成模型专用 Context Pack；
- `aios complete`：完成任务并回写 `tasks.md`、`changelog.md`、`memory.md`。
- `aios web`：启动本地浏览器控制台，通过 JSON API 复用同一套文件系统状态。

---

## 16.2 功能审核

### 已纳入本次交付

- 本地 CLI 项目结构；
- 文件系统状态存储；
- 项目初始化；
- 项目扫描和忽略规则；
- 任务分类和任务 ID 生成；
- 模型路由推荐；
- Context Pack 生成；
- 任务完成回写；
- README 使用说明；
- pytest 基础测试。

### 暂不纳入本次交付

- Web UI / Desktop UI；
- 真实模型 API 调用；
- Provider 密钥管理；
- 自动应用代码修改；
- 自动 Git commit / push；
- 成本统计数据库；
- 多项目全局管理。

---

## 16.3 测试计划

### 自动化测试

使用 `pytest` 覆盖：

1. `aios init` 是否生成 `.aios/` 核心文件；
2. `aios scan` 是否忽略 `node_modules/` 等目录；
3. `aios task create` 是否生成任务 ID、任务类型和推荐模型；
4. `aios route` 是否能输出推荐模型；
5. `aios pack` 是否生成 Context Pack 文件；
6. `aios complete` 是否更新任务状态、changelog 和 memory。

运行命令：

```bash
python -m pytest
```

### 手工验收流程

在任意测试项目目录执行：

```bash
aios init --name demo --type web-app
aios scan
aios task create "实现登录功能" --priority high
aios task list
aios route TASK-YYYYMMDD-001
aios pack TASK-YYYYMMDD-001 --model gpt-5.5
aios complete TASK-YYYYMMDD-001 --summary "完成登录功能并通过测试"
aios status
```

验收通过条件：

- 所有命令退出成功；
- `.aios/file-index.json` 存在且包含项目文件；
- `.aios/tasks.json` 中任务状态可读；
- `.aios/tasks.md` 同步展示任务；
- `.aios/context-packs/` 中生成对应任务的 Markdown；
- `.aios/changelog.md` 和 `.aios/memory.md` 写入完成记录；
- 自动化测试全部通过。

---

## 17. 后续增强方向

### 17.1 接入 CC Switch

AIOS 可以输出路由建议给 CC Switch：

```json
{
  "task_id": "TASK-20260630-001",
  "recommended_provider": "openai",
  "recommended_model": "gpt-5.5",
  "fallback_provider": "deepseek",
  "fallback_model": "deepseek-v4-pro",
  "context_pack_path": ".aios/context-packs/TASK-20260630-001-gpt.md"
}
```

### 17.2 自动模型调用

未来支持：

```bash
aios run TASK-ID
```

自动完成：

```text
选择模型 → 生成 Context Pack → 调用模型 → 应用代码修改 → 运行测试 → 回写状态
```

### 17.3 多项目管理

增加全局目录：

```text
~/.aios/
  projects.yaml
  providers.yaml
  usage.db
  model-profiles.yaml
```

### 17.4 成本统计

记录：

- 每次任务用哪个模型；
- 输入 Token；
- 输出 Token；
- 缓存命中；
- 估算成本；
- 是否成功；
- 人工返工次数。

### 17.5 模型效果评分

每次任务完成后给模型打分：

```yaml
model_score:
  model: gpt-5.5
  task_type: complex_coding
  success: true
  quality: 9
  cost: high
  speed: medium
  retry_count: 0
```

---

## 18. 最终产品愿景

AIOS 的最终目标不是“再做一个 AI 聊天工具”。

它要成为：

> **AI 编程时代的项目操作系统。**

未来所有模型都只是执行器：

```text
GPT = 高级架构师
DeepSeek = 高性价比工程师
MiniMax = 文档工程师
Claude = 长上下文审查员
本地模型 = 低成本辅助工
```

而 AIOS 负责：

```text
项目知识
任务状态
上下文构建
模型路由
执行记录
成本控制
质量评估
```

最终实现：

> **一个项目，不依赖单一模型；多个模型，可以围绕同一项目连续协作开发。**
