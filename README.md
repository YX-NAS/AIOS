# AIOS 多模型开发中枢

AIOS 是一个本地文件系统型本地开发中枢，当前同时提供 CLI 和 Web UI，用来为软件项目生成 `.aios/` 知识目录、扫描项目结构、管理开发任务、推荐模型路由，并生成可复制给不同 AI 模型的 Context Pack。

详细中文操作说明见 [docs/AIOS_使用说明操作手册.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/AIOS_使用说明操作手册.md)。  
当前版本价值说明见 [docs/AIOS_当前版本价值说明.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/AIOS_当前版本价值说明.md)。  
同类项目对比与借鉴分析见 [docs/AIOS_同类项目对比与借鉴分析.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/AIOS_同类项目对比与借鉴分析.md)。  
当前半自动执行层设计见 [docs/P3_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_DESIGN.md)，下一阶段 `ccswitch` 适配层方案见 [docs/P3_2_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_2_DESIGN.md)。
执行器适配层方案见 [docs/P3_3_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_3_DESIGN.md)。
任务树与拆解草案方案见 [docs/P3_4_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_4_DESIGN.md)。
Context Engine 补强方案见 [docs/P3_5_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_5_DESIGN.md)。
执行总览与调度前置状态方案见 [docs/P3_6_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_6_DESIGN.md)。
自动调度执行链路原型方案见 [docs/P3_7_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_7_DESIGN.md)。
自动完成收口方案见 [docs/P3_8_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_8_DESIGN.md)。
自动 Git 提交方案见 [docs/P3_10_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_10_DESIGN.md)。
外部模型切换接管方案见 [docs/P3_11_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_11_DESIGN.md)。
自动 Push 方案见 [docs/P3_12_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_12_DESIGN.md)。
Provider / Session 接管方案见 [docs/P3_13_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_13_DESIGN.md)。
自动 PR 草案方案见 [docs/P3_14_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_14_DESIGN.md)。
执行会话恢复入口方案见 [docs/P3_16_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_16_DESIGN.md)。

## MVP 边界

当前版本专注可交付的本地 CLI + Web UI：

- 初始化 `.aios/` 项目记忆目录；
- 扫描项目文件并生成 `file-index.json` 和扫描报告；
- 创建、查看、完成任务；
- 根据任务类型和 `model-routing.yaml` 推荐模型；
- 生成模型专用 Context Pack；
- 提供本地浏览器可视化控制台；
- 用文件系统保存状态，不直接调用真实模型、不自动改业务代码。

当前推荐的执行方式是半自动流程：

1. 先把目标拆成任务；
2. 用 `aios run --manual TASK-ID --start` 统一生成执行记录、Context Pack 和交接单；
3. 如需标准化切换信息，可先用 `aios ccswitch export TASK-ID` 导出 `ccswitch` 适配 JSON；
4. 用 `aios ccswitch provider TASK-ID` 或 Web UI 复制 Provider Deep Link，把推荐模型的 provider 配置导入 `ccswitch`；
5. 用 `aios ccswitch deeplink TASK-ID` 导入 handoff prompt；如需恢复会话，可导出 `aios ccswitch session TASK-ID` 生成 Session Handoff；
6. 在 `ccswitch` 中切换或恢复到目标会话；
7. 在 Codex 或 Claude Code 中执行；
8. 用 `aios run finish TASK-ID --summary "..."` 或 Web UI 回写 AIOS。

当前已经支持导出 `ccswitch` 适配 JSON、Provider Deep Link、Prompt Deep Link 和 Session Handoff，但仍然不会静默切换 `ccswitch`，也不会自动恢复指定桌面会话。后续会在这个流程稳定之后，再补自动调度和自动切换。

当前版本已增加执行器适配层原型：

- `aios executor` 管理全局执行器库
- `aios run TASK-ID --executor EXECUTOR-ID` 可直接调起受控 CLI 执行器
- `aios run auto [--executor ...]` 可自动选择下一条 `ready` 任务并派发到执行器
- `aios run ... --auto-finish --summary "..." --verify-command "..."` 可在验证通过后自动完成任务回写
- `aios run ... --auto-commit` 可在受控条件下自动生成本地 Git commit
- `aios run ... --auto-push` 可在特性分支上继续自动 push 到远端
- `aios run ... --auto-pr` 可在 push 成功后继续自动创建 Draft PR
- `aios ccswitch deeplink TASK-ID` 可直接生成 `ccswitch://` Deep Link，把 handoff 导入 CC Switch
- `aios ccswitch provider TASK-ID` 可直接生成 `resource=provider` Deep Link，把模型对应的 provider 配置导入 CC Switch
- `aios ccswitch session TASK-ID` 可导出包含 provider/prompt deeplink 和恢复提示的 Session Handoff
- `aios run attach TASK-ID` / `aios run resume TASK-ID` 可把真实执行会话挂接到任务上，并生成恢复命令
- 自动化仍然不会自己理解业务验收结论，`summary` 仍需由操作者或上层系统提供

## 安装与运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

如果本地 `pip` 较老，建议先升级：

```bash
python -m pip install --upgrade pip setuptools wheel
```

也可以不安装，直接用模块方式运行：

```bash
PYTHONPATH=src python -m aios.main status
```

## 常用命令

```bash
aios init --name my-project --type web-app
aios executor list
aios scan
aios task create "实现登录功能"
aios task plan "完成聊天接口时间上下文修复"
aios task plan "开发会员积分系统，包含积分获取、积分扣减、明细查询和后台管理" --draft
aios task draft list
aios task list
aios task show TASK-20260630-001
aios route TASK-20260630-001
aios pack TASK-20260630-001 --model gpt-5.5
aios run --manual TASK-20260630-001 --start
aios run TASK-20260630-001 --executor codex-cli
aios run auto --executor codex-cli
aios run auto --executor codex-cli --auto-finish --summary "完成登录功能并通过测试" --verify-command "pytest -q"
aios run auto --executor codex-cli --auto-finish --summary "完成登录功能并通过测试" --verify-command "pytest -q" --auto-commit
aios run auto --executor codex-cli --auto-finish --summary "完成登录功能并通过测试" --verify-command "pytest -q" --auto-commit --auto-push
aios run auto --executor codex-cli --auto-finish --summary "完成登录功能并通过测试" --verify-command "pytest -q" --auto-commit --auto-push --auto-pr
aios run approve TASK-20260630-001 --summary "确认交付" --verify-command "pytest -q"
aios run finish TASK-20260630-001 --summary "完成登录功能并通过测试" --auto-commit
aios run finish TASK-20260630-001 --summary "完成登录功能并通过测试" --auto-commit --auto-push
aios run finish TASK-20260630-001 --summary "完成登录功能并通过测试" --auto-commit --auto-push --auto-pr
aios run status TASK-20260630-001
aios run attach TASK-20260630-001 --executor codex-cli --session-id session-123
aios run resume TASK-20260630-001
aios run resume TASK-20260630-001 --latest-session
aios ccswitch export TASK-20260630-001
aios ccswitch deeplink TASK-20260630-001 --app codex --stdout
aios ccswitch provider TASK-20260630-001 --app codex --stdout
aios ccswitch session TASK-20260630-001 --app codex --stdout
aios run finish TASK-20260630-001 --summary "完成登录功能并通过测试"
aios handoff TASK-20260630-001 --model gpt-5.5
aios complete TASK-20260630-001 --summary "完成登录功能并通过测试"
aios status
aios web --port 8765
aios launcher --port 8755
```

## Web UI

如果你只操作一个项目，继续使用单项目 Web UI：

启动本地 Web UI：

```bash
aios --root /path/to/project web --port 8765
```

如果希望一条命令后台启动并自动打开浏览器：

```bash
./scripts/start_local_webui.sh /path/to/project
```

在 macOS 上也可以直接双击或拖拽项目文件夹到 [AIOS_启动WebUI.command](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/AIOS_启动WebUI.command)。

停止本地服务：

```bash
./scripts/stop_local_webui.sh /path/to/project
```

打开浏览器访问：

```text
http://127.0.0.1:8765
```

当前 Web UI 支持：

- 初始化 `.aios/`
- 扫描项目
- 按目标自动拆分任务
- 创建任务
- 查看任务和路由建议
- 开始一次半自动执行并记录执行状态
- 通过执行器适配层调起 CLI 自动执行
- 自动派发下一条可执行任务
- 自动推进 `review_pending -> done`
- 自动完成后本地 Git 提交
- 自动 push 当前特性分支
- 自动创建 Draft PR
- 生成并复制 ccswitch Deep Link
- 生成并复制 Provider Deep Link
- 导出并复制 Session Handoff
- 挂接任务执行会话并复制恢复命令
- 生成 Context Pack
- 导出 `ccswitch` 适配文件或复制 JSON
- 生成并复制任务交接单
- 填写实际模型、测试结果并完成回写

## Multi-Project Launcher

如果你要同时管理多个项目，使用 launcher 首页：

```bash
aios launcher --port 8755
```

打开浏览器访问：

```text
http://127.0.0.1:8755
```

launcher 首页负责：

- 手动登记多个项目目录
- 维护全局模型库
- 新增、编辑、删除自定义模型
- 一键恢复默认模型库
- 查看每个项目是否已初始化、是否正在运行
- 查看每个项目的任务数、文件索引数和最近目标/任务
- 查看每个项目启用的模型数量
- 查看每个项目的活跃执行数和最近执行状态
- 启动或停止单项目实例
- 触发项目扫描
- 跳转到对应项目自己的 Web UI

launcher 首页会自动轮询刷新项目状态和摘要数据。

模型库编辑统一在 launcher 首页进行。你可以修改模型 ID、显示名称、提供方、适合任务类型、优先级，以及与 `ccswitch` Provider Deep Link 相关的 provider 地址、配置 URL、说明；也可以新增模型、删除模型，或恢复默认模型库。后续所有项目的新建任务、目标拆解、路由推荐和 provider handoff 都会按这套全局模型库生效。

每个项目仍然保持独立 `.aios/`，互不串扰。

`aios task plan` 现在支持两类更实用的拆解：

- 对 bug 类目标，按定位、修复、回归、记录拆解；
- 对“开发某系统，包含模块 A/B/C”类目标，按系统边界、接口设计、模块实现、测试、文档拆解。

此外，复杂目标现在支持“拆解草案 -> 确认创建”的路径，并在正式任务中保留父任务和依赖关系。

Context Pack 现在也已经升级为分层结构，并返回质量提示与相关文件数量，便于后续自动执行前做质量判断。

当前单项目页和 launcher 首页也已经能显示调度前置状态，例如：

- 可执行任务数
- 被阻塞任务数
- 待复核任务数
- 下一步建议动作

## 测试

```bash
python -m pytest
```

## 交付验收

第一版验收通过条件：

- `aios init` 能生成 `.aios/`、配置、上下文、任务、执行记录、规则和路由文件；
- `aios scan` 能忽略常见构建目录并输出文件索引；
- `aios task create` 能生成稳定任务 ID、分类、推荐模型和验收标准；
- `aios route` 能说明推荐模型和兜底模型；
- `aios pack` 能生成可读 Context Pack；
- `aios run --manual` 能生成执行记录、Context Pack 和交接单；
- `aios run TASK-ID --executor ...` 能调起受控 CLI 执行器，并记录命令、退出状态和日志；
- `aios run auto` 能按调度状态自动选择下一条 `ready` 任务并派发执行；
- `aios run ... --auto-finish` 能在验证命令通过后自动完成回写；
- `aios run ... --auto-commit` 能在执行开始前工作区干净时自动提交本地 Git 变更；
- `aios ccswitch export` 能导出可追溯的 `ccswitch` 适配 JSON；
- `aios ccswitch provider` 能导出可追溯的 provider Deep Link；
- `aios ccswitch session` 能导出可追溯的 Session Handoff；
- `aios run attach` / `aios run resume` 能为任务生成可追溯的会话恢复入口；
- `aios run finish` 能更新执行记录、任务状态、`changelog.md` 和 `memory.md`；
- `aios complete` 能更新任务状态、`changelog.md` 和 `memory.md`；
- `aios web` 能启动本地可视化控制台；
- `python -m pytest` 通过。
