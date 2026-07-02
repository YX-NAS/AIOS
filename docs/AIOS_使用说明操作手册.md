# AIOS 使用说明操作手册

## 1. 文档目的

本手册用于指导你在本地项目中使用 AIOS CLI 和 Web UI。

当前版本是 MVP，本手册只覆盖已经实现的能力：

- 初始化 `.aios/` 项目知识目录；
- 扫描项目文件并生成索引；
- 创建、查看、完成任务；
- 为任务推荐模型；
- 生成可发给模型的 Context Pack；
- 建立任务执行记录并跟踪执行状态；
- 导出 `ccswitch` 适配文件或复制 JSON；
- 复制 Provider Deep Link，导出 Session Handoff；
- 提供本地 Web 控制台；
- 回写任务记录、changelog 和 memory。

当前仍不包含的能力：

- 不直接调用真实模型；
- 不自动修改业务代码；
- 不自动执行 Git 提交；

当前推荐的使用方式仍然是“半自动为主，自动执行原型为辅”：

- AIOS 负责拆分任务、推荐模型、生成执行记录、Context Pack 和交接单；
- 你可以先导出 `ccswitch` 适配文件，再复制 Provider Deep Link 或导出 Session Handoff；
- 再把 Context Pack 交给 Codex 或 Claude Code 执行；
- 完成后回写 AIOS。

当前也已经提供执行器适配层原型：

- 可通过 `aios executor list` 查看全局执行器；
- 可通过 `aios run TASK-ID --executor codex-cli` 直接调起 CLI；
- 自动执行成功后不会直接把任务标记为完成，而是进入待复核状态。

## 2. 运行环境

要求：

- Python 3.10 或更高版本；
- macOS / Linux / Windows 均可，下面示例以 macOS 或 Linux shell 为主。

建议先确认版本：

```bash
python3 --version
```

## 3. 安装方式

### 方式一：本地安装命令

适合长期使用。

```bash
cd /Users/yaxun/SynologyDrive/日常工作/Github/AIOS
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

如果遇到 editable install 相关报错，可先升级安装工具：

```bash
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

安装完成后可直接使用：

```bash
aios status
```

### 方式二：不安装，直接模块运行

适合临时测试。

```bash
cd /Users/yaxun/SynologyDrive/日常工作/Github/AIOS
PYTHONPATH=src python3 -m aios.main status
```

## 4. 命令总览

当前支持的命令：

```bash
aios init
aios executor list
aios scan
aios status
aios ccswitch export TASK-ID
aios ccswitch provider TASK-ID
aios ccswitch session TASK-ID
aios task create "任务名称"
aios task plan "目标描述"
aios task plan "复杂目标描述" --draft
aios task draft list
aios task draft confirm DRAFT-ID
aios task list
aios task show TASK-ID
aios route TASK-ID
aios pack TASK-ID --model gpt-5.5
aios run --manual TASK-ID --start
aios run TASK-ID --executor codex-cli
aios run status TASK-ID
aios run finish TASK-ID --summary "完成说明"
aios handoff TASK-ID --model gpt-5.5
aios complete TASK-ID --summary "完成说明"
aios web --port 8765
aios launcher --port 8755
```

所有命令都支持：

```bash
--root /path/to/your/project
```

作用是指定你要操作的目标项目目录。

## 5. 标准操作流程

建议每个项目按下面流程使用。

### 第 1 步：初始化项目

进入你的业务项目目录后执行：

```bash
aios --root /path/to/project init --name my-project --type web-app
```

说明：

- `--name` 不填时，默认使用目录名；
- `--type` 不填时，默认值为 `software-project`；
- `--force` 可重建缺失的默认文件。

初始化成功后会生成 `.aios/` 目录。

### 第 2 步：扫描项目

```bash
aios --root /path/to/project scan
```

扫描会：

- 递归遍历项目文件；
- 忽略 `.git`、`node_modules`、`dist`、`build`、`.venv`、`.aios` 等目录；
- 生成文件索引和扫描报告。

### 第 3 步：查看当前状态

```bash
aios --root /path/to/project status
```

该命令会显示：

- `.aios` 路径；
- 当前任务总数；
- 未完成任务数；
- 已完成任务数；
- 已索引文件数。

### 第 4 步：创建任务

```bash
aios --root /path/to/project task create "实现登录功能" --priority high
```

可选参数：

- `--priority low`
- `--priority medium`
- `--priority high`
- `--acceptance "新增登录接口"`
- `--acceptance "补充测试"`

如果不传 `--acceptance`，AIOS 会根据任务类型生成默认验收标准。

### 第 4.1 步：按目标自动拆分任务

如果你不想手工一条条建任务，可以直接给 AIOS 一个目标：

```bash
aios --root /path/to/project task plan "完成聊天接口时间上下文修复" --priority high
```

AIOS 会自动生成一组子任务，并且每条子任务都带上：

- 任务类型
- 推荐模型
- 优先级

当前拆分逻辑会优先覆盖这些工程阶段：

- 分析或方案拆解
- 核心实现或修复
- 测试与回归验证
- 文档与记录更新

如果目标本身带有模块信息，例如：

```text
开发会员积分系统，包含积分获取、积分扣减、明细查询和后台管理
```

AIOS 会进一步拆成更具体的功能任务，而不是只有“实现核心功能”这一层。

如果只想先看拆分结果，不落盘：

```bash
aios --root /path/to/project task plan "完成聊天接口时间上下文修复" --preview
```

如果你想把拆分结果先保存成草案，稍后再确认：

```bash
aios --root /path/to/project task plan "开发会员积分系统，包含积分获取、积分扣减、明细查询和后台管理" --draft
```

查看草案：

```bash
aios --root /path/to/project task draft list
aios --root /path/to/project task draft show DRAFT-20260702-001
```

确认草案并正式创建任务：

```bash
aios --root /path/to/project task draft confirm DRAFT-20260702-001
```

删除草案：

```bash
aios --root /path/to/project task draft delete DRAFT-20260702-001
```

现在复杂目标的拆解结果会额外保留：

- 父任务关系
- 依赖任务关系

这样后续自动调度时，系统可以知道“哪条任务必须先做，哪条任务可以后做”。

### 第 5 步：查看任务列表或任务详情

查看列表：

```bash
aios --root /path/to/project task list
```

查看详情：

```bash
aios --root /path/to/project task show TASK-20260701-001
```

### 第 6 步：获取模型路由建议

```bash
aios --root /path/to/project route TASK-20260701-001
```

输出内容包括：

- 任务标题；
- 任务类型；
- 复杂度；
- 推荐模型；
- 兜底模型；
- 推荐原因。

### 第 7 步：生成 Context Pack

```bash
aios --root /path/to/project pack TASK-20260701-001 --model gpt-5.5
```

生成结果默认位于：

```text
.aios/context-packs/TASK-20260701-001-gpt-5.5.md
```

这个文件可以直接复制给对应模型，作为当前任务的上下文材料。

当前 Pack 已经调整为分层结构：

- 任务层
- 项目层
- 文件层

并且生成时会给出：

- token 估算
- 窗口占用比例
- 质量等级
- 相关文件数量

如果项目背景、架构说明还是占位内容，或者没有扫描项目，Pack 会给出提示，帮助你在执行前先补齐上下文。

## 5.1 调度状态怎么看

当前 AIOS 已经能给出“调度前置状态”，帮助你判断下一步先做什么。

单项目页会显示：

- 可执行任务数
- 被阻塞任务数
- 每条任务的调度状态
- 下一步建议动作

launcher 首页会显示：

- 可执行任务
- 被阻塞任务
- 待复核数
- 执行失败数
- 下一条建议任务

这些信息当前主要用于人工判断和半自动执行准备，下一阶段会继续推进为真正的自动调度执行入口。

### 第 7.1 步：开始一次半自动执行

推荐使用统一入口：

```bash
aios --root /path/to/project run --manual TASK-20260701-001 --start
```

这一步会统一完成：

- 读取任务和推荐模型；
- 生成或复用 Context Pack；
- 生成或复用交接单；
- 创建执行记录；
- 把任务状态切到 `running`。

执行记录默认写入：

```text
.aios/executions.json
```

如果你想查看某条任务最近一次执行记录：

```bash
aios --root /path/to/project run status TASK-20260701-001
```

### 第 7.1.1 步：使用执行器原型自动执行

如果你本机已经安装并登录对应 CLI，可以直接让 AIOS 调起执行器：

```bash
aios --root /path/to/project executor list
aios --root /path/to/project run TASK-20260701-001 --executor codex-cli
```

也可以使用：

```bash
aios --root /path/to/project run TASK-20260701-001 --executor claude-code-cli
```

自动执行时，AIOS 会：

- 生成或复用 Context Pack / handoff；
- 创建执行记录；
- 调起目标 CLI；
- 记录执行命令、退出码和日志；
- 成功时把执行状态写成 `review_pending`；
- 失败时把执行状态写成 `failed`。

说明：

- 当前这是自动执行原型，不是最终无人值守交付；
- 默认情况下，自动执行成功后，任务仍需要人工 review；
- 如果你已经准备好完成总结，并且希望让 AIOS 自动收口，可使用：

```bash
aios --root /path/to/project run TASK-20260701-001 --executor codex-cli --auto-finish --summary "完成登录修复" --verify-command "pytest -q"
```

- 如果当前任务已经处于 `review_pending`，也可以直接执行：

```bash
aios --root /path/to/project run approve TASK-20260701-001 --summary "确认交付" --verify-command "pytest -q"
```

- 当 `verify-command` 退出码非 0 时，AIOS 不会把任务错误标记为 `done`，而是继续保持 `review_pending`。
- 如果你希望任务完成后顺手自动生成本地 Git commit，可以继续追加：

```bash
aios --root /path/to/project run approve TASK-20260701-001 --summary "确认交付" --verify-command "pytest -q" --auto-commit
```

- 自动提交只会在“执行开始前非 `.aios/` 工作区是干净的”情况下启用；如果你原本就有未处理的业务代码改动，AIOS 会跳过提交并说明原因。
- 如果当前是特性分支，并且已经配置好远端，也可以继续追加：

```bash
aios --root /path/to/project run approve TASK-20260701-001 --summary "确认交付" --verify-command "pytest -q" --auto-commit --auto-push
```

- `auto-push` 默认跳过 `main` / `master`，这一版只建议用于特性分支远程交付。
- 如果希望 push 成功后继续自动生成 Draft PR，可以继续追加：

```bash
aios --root /path/to/project run approve TASK-20260701-001 --summary "确认交付" --verify-command "pytest -q" --auto-commit --auto-push --auto-pr
```

- `auto-pr` 当前只创建 Draft PR，不会直接创建 Ready PR。

### 第 7.2 步：生成任务交接单

如果你想把“模型建议 + 手动切换步骤 + Context Pack”一次性准备好，直接生成交接单：

```bash
aios --root /path/to/project handoff TASK-20260701-001 --model gpt-5.5
```

可选参数：

- `--refresh-pack`：重新生成 Context Pack 后再出交接单，确保上下文是最新的。

生成结果默认位于：

```text
.aios/handoffs/TASK-20260701-001-gpt-5.5-handoff.md
```

这个文件适合直接作为半自动执行的交接材料。

### 第 7.3 步：导出 `ccswitch` 适配文件

如果你不想再手工抄模型名、Pack 路径和交接单路径，可以导出适配文件：

```bash
aios --root /path/to/project ccswitch export TASK-20260701-001
```

生成结果默认位于：

```text
.aios/ccswitch/TASK-ID-EXECUTION-ID-模型名-ccswitch.json
```

这个 JSON 当前的用途是：

- 告诉你本次要切换的模型是谁；
- 告诉你 fallback 模型有哪些；
- 告诉你当前任务对应的 Context Pack 路径；
- 告诉你当前任务对应的交接单路径；
- 把这些信息和当前执行记录绑定起来。

当前它不是自动切换脚本，不会直接控制 `ccswitch`。

如果你想直接在终端里拿到 JSON 内容：

```bash
aios --root /path/to/project ccswitch export TASK-20260701-001 --stdout
```

### 第 7.4 步：复制 Provider Deep Link

如果你已经在 launcher 里为模型补了 provider 地址，可以直接生成 `ccswitch` 的 provider 导入链接：

```bash
aios --root /path/to/project ccswitch provider TASK-20260701-001 --app codex --stdout
```

这一步会基于全局模型库里的 provider 配置，生成 `resource=provider` 的 Deep Link。

### 第 7.5 步：导出 Session Handoff

如果你希望把 provider、prompt 和恢复提示一起交给执行端：

```bash
aios --root /path/to/project ccswitch session TASK-20260701-001 --app codex
```

它会输出一个 `.aios/ccswitch/*-session-handoff.json`，里面包含：

- provider deeplink
- prompt deeplink
- project root
- session 搜索关键词
- 恢复建议步骤

### 第 8 步：手动切换 `ccswitch` 并执行开发

推荐顺序：

1. 先看 `ccswitch` 导出文件里的 `export_model`
2. 在 `ccswitch` 中手动切换到该模型
3. 打开 Codex 或 Claude Code
4. 使用：
   - `handoff_path` 对应的交接单，或者
   - `context_pack_path` 对应的 Context Pack
5. 完成开发与本地测试

### 第 9 步：完成任务并回写记录

推荐使用统一完成入口：

```bash
aios --root /path/to/project run finish TASK-20260701-001 --summary "完成登录功能并通过测试"
```

可选参数：

- `--actual-model gpt-5.5`
- `--test-command "pytest -q"`
- `--test-result "67 passed in 18.54s"`
- `--score 4`
- `--score-note "一次通过"`

如果你只想做兼容式完成回写，也可以继续使用旧命令：

```bash
aios --root /path/to/project complete TASK-20260701-001 --summary "完成登录功能并通过测试"
```

执行后会更新：

- `.aios/tasks.json`
- `.aios/tasks.md`
- `.aios/changelog.md`
- `.aios/memory.md`

## 6. `.aios/` 目录说明

初始化后会生成如下目录结构：

```text
.aios/
  project.yaml
  context.md
  architecture.md
  decisions.md
  rules.md
  memory.md
  changelog.md
  tasks.md
  tasks.json
  executions.json
  model-routing.yaml
  model-routing.json
  file-index.json
  context-packs/
  handoffs/
  ccswitch/
  logs/
  reports/
```

关键文件说明：

- `project.yaml`：项目基础信息；
- `context.md`：项目背景和当前阶段；
- `architecture.md`：架构说明；
- `decisions.md`：重要决策记录；
- `rules.md`：项目开发规则；
- `tasks.json`：任务机器状态源；
- `task-plans.json`：目标拆解草案；
- `tasks.md`：任务可读视图；
- `executions.json`：任务执行记录；
- `model-routing.json`：运行时路由规则；
- `model-routing.yaml`：人类可读路由配置；
- `file-index.json`：扫描生成的文件索引；
- `reports/scan-report.md`：扫描报告；
- `context-packs/`：每个任务生成的上下文包；
- `handoffs/`：任务交接单。
- `ccswitch/`：导出的 `ccswitch` 适配文件。

## 6.1 Web UI 使用方法

启动本地 Web UI：

```bash
aios --root /path/to/project web --host 127.0.0.1 --port 8765
```

如果希望后台一键启动并自动打开浏览器，直接运行：

```bash
cd /Users/yaxun/SynologyDrive/日常工作/Github/AIOS
./scripts/start_local_webui.sh /path/to/project
```

脚本会自动完成：

- 检查并创建 `.venv`
- 升级 `pip / setuptools / wheel`
- 安装当前项目
- 自动寻找可用端口
- 后台启动 Web UI
- 自动打开浏览器

停止服务：

```bash
./scripts/stop_local_webui.sh /path/to/project
```

macOS 也可以直接使用：

- [AIOS_启动WebUI.command](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/AIOS_启动WebUI.command)
- [AIOS_停止WebUI.command](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/AIOS_停止WebUI.command)

使用方式：

- 直接双击后输入项目目录路径；
- 或把目标项目文件夹拖到 `.command` 文件上。

启动成功后，终端会输出访问地址，默认是：

```text
http://127.0.0.1:8765
```

页面当前支持的操作：

- 在未初始化目录中直接创建 `.aios/`
- 查看项目统计和扫描结果
- 输入目标后一键拆分成多条任务
- 创建任务并选择任务
- 查看推荐模型和路由理由
- 开始一次半自动执行
- 生成 Context Pack
- 导出 `ccswitch` 适配文件
- 复制 `ccswitch` JSON
- 标记任务完成并回写记录

## 6.2 多项目启动器使用方法

如果你同时维护多个项目，建议先启动 launcher 首页：

```bash
aios launcher --host 127.0.0.1 --port 8755
```

打开：

```text
http://127.0.0.1:8755
```

第一版 launcher 支持：

- 手动添加项目目录
- 统一维护全局模型库
- 新增、编辑、删除自定义模型
- 一键恢复默认模型库
- 查看项目是否已初始化
- 查看项目是否运行中
- 查看项目任务统计、索引文件数和最近目标/任务
- 启动或停止项目实例
- 触发项目扫描
- 打开对应项目自己的单项目工作区

页面会自动轮询刷新项目状态和项目摘要数据，不需要每次手动刷新。

注意：

- launcher 首页本身不直接管理任务
- 点击“打开项目”后，才会进入该项目的 AIOS 工作区
- 每个项目仍然保持独立 `.aios/`

在 launcher 首页中可以配置全局模型库：

- 新增模型
- 删除模型
- 修改模型 ID、显示名称和提供方
- 启用或停用模型
- 设置模型适合的任务类型
- 设置模型推荐优先级
- 一键恢复默认模型库

这些配置会影响后续所有项目的任务创建、目标拆解和模型路由推荐。

使用建议：

- 如果你习惯命令行，继续用 CLI；
- 如果你想看任务、状态和 Pack 的可视化视图，用 Web UI 更顺手；
- CLI 和 Web UI 操作的是同一套 `.aios/` 文件，可以混用。

## 7. 任务分类规则

AIOS 会根据任务标题自动分类。

示例：

- 包含“架构、重构、模块设计、设计”会倾向于 `architecture`
- 包含“修复、bug、报错、错误、异常”会倾向于 `bug_fix`
- 包含“登录、认证、权限、支付、核心、算法”会倾向于 `complex_coding`
- 包含“测试、test、pytest”会倾向于 `testing`
- 包含“文档、README、说明、总结”会倾向于 `documentation`
- 包含“页面、UI、样式、前端”会倾向于 `ui_design`

如果没有明显关键词，则会按普通开发任务处理。

## 8. 推荐使用方式

### 场景一：给 Codex 或 GPT 准备开发上下文

```bash
aios --root /path/to/project scan
aios --root /path/to/project task create "修复用户登录报错" --priority high
aios --root /path/to/project route TASK-20260701-001
aios --root /path/to/project pack TASK-20260701-001 --model gpt-5.5
```

然后把生成的 `.md` 文件发给模型。

### 场景二：记录已经完成的开发任务

```bash
aios --root /path/to/project complete TASK-20260701-001 --summary "修复登录报错，补充回归测试"
```

这样 AIOS 会保留任务状态和项目记忆。

### 场景三：先半自动执行，再考虑自动化调度

这是当前最推荐的工作方式，适合先把流程跑通。

```text
目标 → 拆分任务 → 开始执行 → 导出 ccswitch 适配文件 / Provider Deep Link / Session Handoff → 人工切换或恢复 ccswitch 会话 → 在 Codex/Claude Code 中执行 → 本地测试 → AIOS 回写
```

推荐步骤：

1. 先把目标写成一句话。

```bash
aios --root /path/to/project task plan "完成聊天接口时间上下文修复"
```

2. 选择一条最关键的任务，查看路由建议。

```bash
aios --root /path/to/project route TASK-20260701-001
```

3. 开始执行。

```bash
aios --root /path/to/project run --manual TASK-20260701-001 --start
```

4. 导出 `ccswitch` 适配文件。

```bash
aios --root /path/to/project ccswitch export TASK-20260701-001
```

5. 如有需要，也可以单独生成交接单：

```bash
aios --root /path/to/project handoff TASK-20260701-001 --model gpt-5.5
```

6. 手动在 `ccswitch` 里切换到导出文件里的 `export_model`。
7. 打开 Codex 或 Claude Code，把交接单或其中的 Context Pack 作为当前任务上下文。
8. 按任务实现、测试、修复。
9. 完成后回写。

```bash
aios --root /path/to/project run finish TASK-20260701-001 --summary "..."
```

10. 如果希望完成时自动提交 Git，可在回写时追加：

```bash
aios --root /path/to/project run finish TASK-20260701-001 --summary "..." --auto-commit
```

这一阶段的判断标准：

- 任务拆分是清楚的；
- 推荐模型是合理的；
- 人工切换后能顺利执行；
- 结果能回写到 AIOS；
- 下一个任务可以接着跑。

后续自动化阶段：

- 自动调度任务；
- 自动调用模型切换器；
- 自动收集执行结果；
- 自动判断是否进入下一任务；
- 自动回写完成摘要和测试结果；
- 自动提交 Git 变更。

这一阶段再考虑把 `ccswitch` 接进脚本或适配器层，不建议一开始就直接依赖自动切换。

## 9. 测试与验收

运行自动化测试：

```bash
cd /Users/yaxun/SynologyDrive/日常工作/Github/AIOS
python3 -m pytest
```

如果没有安装开发依赖，可先执行：

```bash
pip install -e ".[dev]"
```

最小手工验收流程：

```bash
aios --root /tmp/demo-aios init --name demo --type web-app
aios --root /tmp/demo-aios scan
aios --root /tmp/demo-aios task create "实现登录功能" --priority high
aios --root /tmp/demo-aios task list
aios --root /tmp/demo-aios route TASK-YYYYMMDD-001
aios --root /tmp/demo-aios run --manual TASK-YYYYMMDD-001 --start
aios --root /tmp/demo-aios ccswitch export TASK-YYYYMMDD-001
aios --root /tmp/demo-aios run finish TASK-YYYYMMDD-001 --summary "完成登录功能并通过测试"
aios --root /tmp/demo-aios status
aios --root /tmp/demo-aios web --port 8765
```

验收通过标准：

- 所有命令执行成功；
- `.aios/` 目录生成完整；
- `file-index.json` 存在且有内容；
- `context-packs/` 中有对应任务文件；
- `executions.json` 中有对应执行记录；
- `ccswitch/` 中能看到对应导出文件；
- `tasks.json` 中状态已更新为 `done`；
- `changelog.md` 和 `memory.md` 已写入完成记录。
- Web UI 可正常打开并显示项目状态。

## 10. 常见问题

### 1. 提示 `AIOS project is not initialized`

原因：

当前目标目录下还没有 `.aios/`。

处理：

```bash
aios --root /path/to/project init
```

### 2. `status` 显示 `Files indexed: 0`

原因：

还没有执行扫描。

处理：

```bash
aios --root /path/to/project scan
```

### 3. 为什么生成了 `tasks.json` 和 `tasks.md` 两份任务文件

原因：

- `tasks.json` 用于程序稳定读写；
- `tasks.md` 用于人工查看和审阅。

### 4. 为什么现在 Web UI 里还不能直接让 AIOS 调模型改代码

原因：

当前版本是文件系统型 MVP，重点是项目知识、任务状态、上下文包和路由建议，自动调用模型和执行改代码属于后续阶段。

### 5. `ccswitch` 适配文件怎么使用

当前导出的 `ccswitch` 适配文件，不是自动执行脚本，而是标准化切换信息包。

用法：

1. 先执行：

```bash
aios --root /path/to/project run --manual TASK-ID --start
```

2. 再导出：

```bash
aios --root /path/to/project ccswitch export TASK-ID
```

3. 打开生成的 JSON，重点看：

- `export_model`
- `fallback_models`
- `context_pack_path`
- `handoff_path`

4. 在 `ccswitch` 中手动切换到 `export_model`
5. 按 JSON 里的路径去打开 Context Pack 或交接单继续执行

如果你希望少一步手工复制粘贴，也可以直接生成 Deep Link：

```bash
aios --root /path/to/project ccswitch deeplink TASK-ID --app codex --stdout
```

如果本机已经安装并注册了 CC Switch Deep Link，也可以直接尝试打开：

```bash
aios --root /path/to/project ccswitch deeplink TASK-ID --app codex --open
```

这会生成一个 `ccswitch://v1/import?...` 链接，把当前任务 handoff 作为 prompt 资源导入 CC Switch。

它当前解决的是：

- 不用手抄模型名
- 不用手抄 Pack 路径
- 不用手抄交接单路径

它当前还不能做的是：

- 不能直接自动控制 `ccswitch`
- 目前只是 prompt 级 Deep Link 导入，还不是 provider / 会话级自动切换
- 不能自动打开 Codex 或 Claude Code

## 11. 当前版本边界说明

当前版本已经可以用于：

- 给不同模型准备统一的项目上下文；
- 保留项目任务状态；
- 保留任务执行记录和 `ccswitch` 导出记录；
- 记录开发完成情况；
- 通过浏览器查看和操作本地项目状态；
- 降低跨模型协作时的上下文丢失。

当前版本还不适合用于：

- 完整自动开发流水线；
- 多 Provider 实时调用；
- 自动提交代码；
- 团队级多项目控制台。

## 12. 建议的日常使用习惯

推荐每次开始新任务时：

1. 先 `scan`
2. 再 `task create`
3. 然后 `route`
4. 再 `pack`

推荐每次任务结束时：

1. 手工确认业务代码已经完成
2. 手工运行你的项目测试
3. 再执行 `complete`

这样项目状态会更稳定，后续切换模型也更顺。
