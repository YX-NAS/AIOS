# AIOS 多模型开发中枢 v0.41.0

AIOS 是一个本地文件系统型本地开发中枢，当前同时提供 CLI 和 Web UI，用来为软件项目生成 `.aios/` 知识目录、扫描项目结构、管理开发任务、推荐模型路由，并生成可复制给不同 AI 模型的 Context Pack。

## v0.41.0 总控台强化更新

本轮把 launcher 从“项目入口页”继续推进为“总控台首页”：

- **行动队列**：新增“立即执行 / 待接管 / 待验收 / 执行中”四个跨项目队列
- **基础设施状态**：首页直接显示路径失效、待初始化、待扫描、模型未就绪、执行器未就绪、Provider 握手失败、API 权限失败
- **最近活动**：新增跨项目最近任务、执行、接管事件流
- **实时刷新**：总控台与项目摘要继续自动轮询刷新，适合日常值守和监控
- **回归通过**：launcher 新增总控台聚合测试，相关测试通过

## v0.40.1 补丁更新

本轮是 launcher 生产工作台和项目接入体验补丁：

- **添加项目双入口**：支持“手动填写项目路径”与“系统文件夹选择器”两种方式
- **目录选择接口**：新增 `/api/projects/pick-folder`，由本地后端拉起系统目录选择框并返回真实绝对路径
- **Launcher 工作台增强**：补齐今日总览、真实项目接入清单、项目健康摘要等入口与状态展示
- **回归通过**：launcher 新增目录选择测试，全量 **158 passed**

## v0.38.1 更新

本轮为 v0.38 系的稳定修复：

- 修复 3 个测试失败：bridge 阻塞调度检测、调度器状态汇总、预算策略阻塞路径
- 增强 `build_dispatch_block_reason`：增加 bridge 待确认状态检测
- 测试隔离改进：使用 `AIOS_STATE_DIR` 避免全局模型握手缓存污染
- 全量 140 测试通过

## v0.40 新增能力

本轮完成 P4 全自动调度闭环的端到端落地：

- **多任务串行 pipeline**：`aios run pipeline --full-pipeline` 自动依次执行所有 ready 任务
- **人工接管队列**：不可恢复错误（auth 失败、binary 缺失等）写入 takeover 队列，不再无声失败
- **takeover 摘要 API**：`GET /api/run/takeover` 接管状态 + `POST /api/run/takeover/{id}/resolve` 解除
- **Web UI 完整集成**：`/api/run/full-pipeline` 端点 + 接管队列管理
- **8 个新测试**，全量 156 通过

## Launcher 生产工作台

Launcher 已升级为日常第一入口，默认访问 `http://127.0.0.1:8755`：

- **今日总览**：集中展示项目数、生产接入进度、今日任务、可执行任务、阻塞、失败、执行中和待接管数量。
- **行动队列**：直接列出立即执行、待接管、待验收、执行中四类任务。
- **真实项目接入清单**：内置第一批生产项目候选，可一键接入存在于本机的项目目录。
- **项目健康摘要**：每个项目显示健康状态、阻塞原因、最近任务、下一条任务、执行状态、模型/执行器就绪情况。
- **基础设施状态**：直接汇总路径、索引、模型、执行器和 provider 风险。
- **最近活动**：跨项目查看最近任务、执行和接管变化。

推荐日常工作先打开 Launcher，再从工作台进入具体项目。

## v0.39 新增能力

本轮实现 P4 全自动调度闭环的关键突破：

- **auto_switch 自动切换**：`aios run pipeline` 通过 ccswitch Deep Link API 自动完成 provider + prompt 导入
- **executor 命令构建**：`build_auto_executor_command` 自动将 Context Pack 注入执行器命令行
- **pipeline 步骤编排**：`run_auto_pipeline_step` 串联 switch → build → execute 三步
- **CLI 入口**：`aios run pipeline --auto-switch` 一键触发全自动 pipeline
- **Web API**：`POST /api/run/pipeline` 端点支持远程触发
- **8 个新测试**，全量 148 通过

## v0.38 新增能力

本轮迭代核心是强化"仓库上下文检索"、"执行安全护栏"和"跨模型审查"三大能力：

- **仓库上下文检索增强**：`aios repo map` 生成结构化仓库地图，`aios repo search` 提供有界上下文文件搜索，`aios pack TASK-ID --smart` 智能选取相关文件
- **执行安全护栏**：`aios guard status` 监控执行卡死和 doom-loop，`aios guard heartbeat` 提供心跳存活检测
- **跨模型审查工作流**：`aios review create` 自动创建跨模型审查任务，`aios review complete` 结构化审查结论回写
- **弹性上下文管理**：token 预算控制、上下文质量评分、分层裁剪策略
- **会话智能续接**：`aios session snapshot` / `aios session restore` / `aios session resume` 提供执行中断后的智能恢复

详细中文操作说明见 [docs/AIOS_使用说明操作手册.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/AIOS_使用说明操作手册.md)。  
当前版本价值说明见 [docs/AIOS_当前版本价值说明.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/AIOS_当前版本价值说明.md)。  
同类项目对比与借鉴分析见 [docs/AIOS_同类项目对比与借鉴分析.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/AIOS_同类项目对比与借鉴分析.md)。  
当前半自动执行层设计见 [docs/P3_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_DESIGN.md)。  
P4 全自动调度闭环方案见 [docs/P4_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P4_DESIGN.md)。
第一生产力与系统管理核心落地规划见 [docs/plans/aios-production-core-rollout.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/plans/aios-production-core-rollout.md)。
总控台强化方案见 [docs/plans/aios-control-tower-v041.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/plans/aios-control-tower-v041.md)。
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
执行会话自动识别方案见 [docs/P3_17_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_17_DESIGN.md)。
终端继续执行方案见 [docs/P3_18_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_18_DESIGN.md)。
`ccswitch` 桥接层方案见 [docs/P3_19_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_19_DESIGN.md)。
桥接结果可观测层方案见 [docs/P3_20_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_20_DESIGN.md)。
bridge 确认闭环方案见 [docs/P3_21_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_21_DESIGN.md)。
bridge 确认安全门方案见 [docs/P3_22_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_22_DESIGN.md)。
bridge 恢复信号方案见 [docs/P3_23_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_23_DESIGN.md)。
bridge 恢复信号自动确认方案见 [docs/P3_24_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_24_DESIGN.md)。
历史会话候选与恢复建议方案见 [docs/P3_26_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_26_DESIGN.md)。
执行器真实 CLI 可用性探测方案见 [docs/P3_27_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_27_DESIGN.md)。
验证失败后的自动二次派发方案见 [docs/P3_28_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_28_DESIGN.md)。
成本与执行统计方案见 [docs/P3_9_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_9_DESIGN.md)。
Provider / 鉴权就绪探测方案见 [docs/P3_29_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_29_DESIGN.md)。
失败分类与重试策略方案见 [docs/P3_30_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_30_DESIGN.md)。
预算阈值与调度策略方案见 [docs/P3_31_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_31_DESIGN.md)。
Provider API 深度权限验证方案见 [docs/P3_32_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_32_DESIGN.md)。
差异化自动恢复策略方案见 [docs/P3_33_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_33_DESIGN.md)。
多轮自动恢复护栏方案见 [docs/P3_34_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_34_DESIGN.md)。
分类级恢复上限与冷却方案见 [docs/P3_35_DESIGN.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/P3_35_DESIGN.md)。

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
- `aios run ... --retry-on-verify-fail` 可在验证失败后自动切到下一候选模型并重试一次
- `aios run ... --auto-commit` 可在受控条件下自动生成本地 Git commit
- `aios run ... --auto-push` 可在特性分支上继续自动 push 到远端
- `aios run ... --auto-pr` 可在 push 成功后继续自动创建 Draft PR
- `aios ccswitch deeplink TASK-ID` 可直接生成 `ccswitch://` Deep Link，把 handoff 导入 CC Switch
- `aios ccswitch provider TASK-ID` 可直接生成 `resource=provider` Deep Link，把模型对应的 provider 配置导入 CC Switch
- `aios ccswitch session TASK-ID` 可导出包含 provider/prompt deeplink 和恢复提示的 Session Handoff
- `aios run attach TASK-ID` / `aios run resume TASK-ID` 可把真实执行会话挂接到任务上，并生成恢复命令
- `aios run resume TASK-ID --open-terminal` 可直接在 macOS Terminal 打开恢复命令
- `aios ccswitch bridge TASK-ID --open` 可在 macOS 上把 provider 导入、prompt 导入和终端恢复串成一条桥接动作
- bridge 现在会记录每一步的状态、失败步骤和错误信息，便于后续重试和自动化确认
- bridge 现在还支持显式确认结果，把外部切换收口成 `confirmed_ready` 或 `confirmed_failed`
- 自动派发现在会尊重 bridge 确认状态；未确认前不会继续推进任务
- bridge 终端恢复步骤现在会自动写本地 signal 文件，给外部切换增加一条自动证据
- `aios run auto --auto-confirm-bridge-signal` 可在检测到本地恢复 signal 后自动确认 bridge 已就绪
- `aios run sessions TASK-ID` 可列出当前任务最相关的历史会话候选
- `aios run resume TASK-ID --history-fallback` 可在没有当前挂接会话时显式使用最佳历史候选恢复
- `aios executor doctor` 可检查执行器二进制与基础 healthcheck，避免自动派发到不可用 CLI
- `aios model doctor` 可检查全局模型的 provider 配置和鉴权环境变量是否就绪
- 全局模型库现在还能维护输入/输出单价，执行记录会按 Context Pack 和执行输出估算 token、成本与耗时
- 单项目 Web UI 现在还能配置项目级预算策略，自动派发会在预算超限或模型未定价时主动停下
- 全局模型库现在还能主动探测 provider 可达性，把“已配置”继续推进到“最近一次握手正常”
- `aios model probe` 现在还能继续验证 provider API 权限，而不是只看网络是否可达
- `aios run ... --auto-recover-failures` 现在还能按失败类型自动恢复一次，而不是只支持验证失败 fallback
- 自动恢复现在还能按项目策略连续恢复多轮，并受上限控制
- 自动恢复现在还能按失败类别分别限制恢复次数，并支持恢复冷却时间
- 执行记录现在还能结构化区分失败类型，并给出下一步建议动作
- 执行器运行后可按规则自动提取 session 引用，减少一次人工挂接
- 自动化仍然不会自己理解业务验收结论，`summary` 仍需由操作者或上层系统提供
- 自动重试当前只做“一次受控 fallback 重试”，不会无限循环切模型
- 现在还能按预算策略切换 `default / cheapest_first` 两种 ready 任务调度顺序

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
aios executor doctor
aios model list
aios model doctor
aios model doctor gpt-5.5
aios model probe
aios model probe gpt-5.5
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
aios run auto --auto-confirm-bridge-signal
aios run auto --executor codex-cli --auto-finish --summary "完成登录功能并通过测试" --verify-command "pytest -q"
aios run auto --executor codex-cli --auto-finish --summary "完成登录功能并通过测试" --verify-command "pytest -q" --retry-on-verify-fail
aios run auto --executor codex-cli --auto-finish --summary "完成登录功能并通过测试" --verify-command "pytest -q" --auto-recover-failures
aios run auto --executor codex-cli --auto-finish --summary "完成登录功能并通过测试" --verify-command "pytest -q" --auto-commit
aios run auto --executor codex-cli --auto-finish --summary "完成登录功能并通过测试" --verify-command "pytest -q" --auto-commit --auto-push
aios run auto --executor codex-cli --auto-finish --summary "完成登录功能并通过测试" --verify-command "pytest -q" --auto-commit --auto-push --auto-pr
aios run approve TASK-20260630-001 --summary "确认交付" --verify-command "pytest -q"
aios run finish TASK-20260630-001 --summary "完成登录功能并通过测试" --auto-commit
aios run finish TASK-20260630-001 --summary "完成登录功能并通过测试" --auto-commit --auto-push
aios run finish TASK-20260630-001 --summary "完成登录功能并通过测试" --auto-commit --auto-push --auto-pr
aios run status TASK-20260630-001
aios run attach TASK-20260630-001 --executor codex-cli --session-id session-123
aios run sessions TASK-20260630-001
aios run resume TASK-20260630-001
aios run resume TASK-20260630-001 --history-fallback
aios run resume TASK-20260630-001 --latest-session
aios run resume TASK-20260630-001 --open-terminal
aios run resume TASK-20260630-001 --latest-session --open-terminal
aios ccswitch bridge TASK-20260630-001 --open
aios ccswitch confirm TASK-20260630-001 --status confirmed_ready
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
- 在检测到 bridge 恢复 signal 时自动确认 bridge 已就绪
- 自动推进 `review_pending -> done`
- 自动完成后本地 Git 提交
- 自动 push 当前特性分支
- 自动创建 Draft PR
- 在全局模型库维护模型单价，并在项目页 / launcher 查看 token、估算成本和执行时长
- 在全局模型库一键探测 provider 可达性，并把握手结果同步到 launcher、项目页和 CLI
- 生成并复制 ccswitch Deep Link
- 生成并复制 Provider Deep Link
- 导出并复制 Session Handoff
- 一键桥接到 CC Switch 与终端
- 挂接任务执行会话并复制恢复命令
- 查看历史会话候选并一键挂接
- 在 macOS Terminal 中直接继续当前会话或最近会话
- 在没有当前挂接会话时显式继续最佳历史候选会话
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
- 查看每个项目启用的模型数量与 provider 就绪数
- 查看每个项目的活跃执行数和最近执行状态
- 启动或停止单项目实例
- 触发项目扫描
- 跳转到对应项目自己的 Web UI

launcher 首页会自动轮询刷新项目状态和摘要数据。

模型库编辑统一在 launcher 首页进行。你可以修改模型 ID、显示名称、提供方、适合任务类型、优先级，以及与 `ccswitch` Provider Deep Link 相关的 provider 地址、配置 URL、鉴权环境变量、说明；也可以新增模型、删除模型，或恢复默认模型库。表格里会直接显示每个模型当前是否已具备 provider 配置和本机鉴权变量，便于在开始执行前先排除“模型推荐正确但本地根本无法调用”的情况。后续所有项目的新建任务、目标拆解、路由推荐和 provider handoff 都会按这套全局模型库生效。

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
