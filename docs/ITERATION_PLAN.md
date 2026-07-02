# AIOS 后续迭代方案

生成时间：2026-07-01

## 当前状态

当前版本已交付到 `P3-26` 的历史会话候选与恢复建议，核心功能包括：

- CLI：init / scan / task / route / pack / run / ccswitch / handoff / complete / status / web / launcher
- 单项目 Web UI：项目状态、任务台、路由、执行状态、Context Pack、ccswitch 导出、完成回写
- 多项目 Launcher：项目登记、全局模型库（表格 + 勾选框）、一键启停、执行摘要
- 暗黑科技风 UI 主题

当前开发中：

- `P3-3` 执行器适配层原型已落地首版 CLI / API 能力
- `P3-4` 任务树与拆解草案已落地首版 CLI / API / Web 预览能力
- `P3-5` Context Engine 补强已落地首版分层 Pack 与质量校验
- `P3-6` 执行总览增强已落地首版调度摘要与下一步动作提示
- `P3-7` 自动调度执行链路原型已落地首版 CLI / API / Web 派发能力
- `P3-8` 自动完成收口已落地首版 CLI / API / Web 自动回写能力
- `P3-10` 自动 Git 提交已落地首版 CLI / API / Web 自动本地提交能力
- `P3-11` 外部模型切换接管已落地首版 Deep Link 导入能力
- `P3-12` 自动 Push 已落地首版特性分支远端交付能力
- `P3-14` 自动 PR 草案已落地首版 Draft PR 创建能力
- `P3-16` 执行会话恢复入口已落地首版 attach / resume / continue-latest 能力
- `P3-17` 执行会话自动识别已落地首版 stdout/stderr regex 提取能力
- `P3-18` 终端继续执行已落地首版 macOS Terminal 一键继续能力
- `P3-19` `ccswitch` 桥接层已落地首版 provider/prompt/resume 顺序桥接能力
- `P3-20` 桥接结果可观测层已落地首版步骤状态、失败定位和错误回写能力
- `P3-21` bridge 确认闭环已落地首版 `pending_confirmation -> confirmed_ready/failed` 状态收口
- `P3-22` bridge 确认安全门已落地首版调度阻塞与自动派发保护
- `P3-23` bridge 恢复信号已落地首版本地 signal 文件与 API 自动证据补充
- `P3-24` bridge 恢复信号自动确认已落地首版受控自动确认能力
- `P3-26` 历史会话候选与恢复建议已落地首版候选排序、历史恢复命令和 Web 挂接入口

已知短板：

- 仍需人工切换 `ccswitch`
- 尚未自动调用 Codex / Claude Code CLI
- 任务拆解仍偏平面，缺少草案确认和依赖表达
- Context Pack 还缺分层与质量校验
- 自动化还没有接管 `ccswitch` 和真实会话切换
- 还不会自动识别或提取真实 session id
- 已经能把 `ccswitch -> 会话恢复 -> 终端继续` 串起来，也能定位桥接失败步骤，并显式确认 bridge 结果；系统还能自动看到终端恢复是否启动，但还不能自动读取 `ccswitch` 内部状态，也不能自动选择历史会话
- 现在已经能基于已知执行记录给出历史会话候选，并显式使用最佳候选恢复
- 现在还能在检测到本地恢复 signal 后受控自动确认 bridge，但默认仍不开启
- 自动收口仍依赖显式 `summary`，还不会自动生成可审计的交付结论
- 只支持本地自动 commit，还没有自动 push / PR
- 当前只接通 `ccswitch` prompt Deep Link，provider / session 级接管仍处于数据层补齐阶段
- 还没有自动创建 PR，远端交付还停在分支 push
- Draft PR 已支持，但还没有 reviewer / label / merge 策略

---

## 迭代优先级

按"先稳后快、先窄后宽"排：

### P0 — 质量 & 稳定性

| 编号 | 任务 | 完成标准 |
|------|------|---------|
| P0-1 | pytest 补齐 | init/scan/task/route/pack/complete 各至少 1 个集成测试，`python -m pytest` 全绿 |
| P0-2 | 文档同步 | README、操作手册、需求设计方案三份与代码实际行为一致 |
| P0-3 | 错误处理 | CLI 命令在异常路径下返回清晰错误而非 traceback；Web API 非 200 有 JSON error |
| P0-4 | 模型库持久化验证 | launcher 增删改模型后重启服务，确认改动保留 |

### P1 — 流程提效

| 编号 | 任务 | 完成标准 |
|------|------|---------|
| P1-1 | Context Pack 一键复制 | Web UI 中点击即复制到剪贴板，不需要手动找文件 |
| P1-2 | 任务状态筛选 | 任务台支持按 todo / in_progress / done 筛选 |
| P1-3 | 模型路由日志 | 每次路由推荐记录原因到 `.aios/routing-log.json`，可追溯 |
| P1-4 | 目标拆解结果可编辑 | `task plan` 生成后可在 Web UI 微调再确认，而非直接写入 |
| P1-5 | Launcher 项目卡片折叠 | 项目列表超 3 个时，信息折叠为一行摘要，展开看详情 |

### P2 — 智能化

| 编号 | 任务 | 完成标准 |
|------|------|---------|
| P2-1 | 模型效果评分 | 任务完成后可对模型打分（1-5），数据写入 `.aios/model-scores.json` |
| P2-2 | 路由策略学习 | 根据历史评分自动调整 `model-routing.json` 中的推荐权重 |
| P2-3 | Git diff 分析 | `aios scan` 可读取最近 git diff，自动识别变更文件并关联任务 |
| P2-4 | 上下文窗口预估 | pack 生成时预估 token 数，超出模型上下文窗口时警告 |

### P3 — 执行中枢化

| 编号 | 任务 | 完成标准 |
|------|------|---------|
| P3-0 | 半自动执行稳定层 | `.aios/executions.json` 可追踪 prepared / running / finished；单项目 Web UI 和 launcher 可查看执行摘要 |
| P3-1 | 统一手动执行入口 | `aios run --manual` / `run finish` 跑通一条完整半自动执行链路 |
| P3-2 | CC Switch 集成 | 输出 `ccswitch` 兼容 JSON，可追溯到任务和执行记录 |
| P3-3 | Executor Adapter 原型 | 定义统一执行器接口，并至少接通 1 个稳定 CLI 执行器；失败时可回退到 `run --manual` |
| P3-4 | 任务树与拆解草案 | 支持父子任务、依赖关系、拆解草案确认；Web UI 可修改后再写入 |
| P3-5 | Context Engine 补强 | Pack 分层、token 预估、相关文件筛选和 Pack 质量校验落地 |
| P3-6 | 执行总览增强 | launcher 和单项目页可显示执行器、最近测试、失败摘要、最近交付时间 |
| P3-7 | 自动调度执行链路原型 | `aios run auto` / `/api/run/dispatch` 能按调度结果自动派发下一条 `ready` 任务 |
| P3-8 | 自动完成收口 | `run auto --auto-finish` / `run approve` / Web 自动推进支持验证通过后自动 finish |
| P3-9 | 成本统计 | 记录每次调用的模型、token 数、估算费用，Web UI 可查看 |
| P3-10 | 自动 Git 提交 | `run finish --auto-commit` / `run auto --auto-commit` 支持受控本地提交 |
| P3-11 | 外部模型切换接管 | `ccswitch deeplink` / `/api/ccswitch/deeplink` 支持导入 handoff prompt |
| P3-12 | 自动 Push / 远程交付 | `run ... --auto-push` 支持特性分支自动 push |
| P3-13 | Provider / Session 接管 | 补 provider deep link、Session Handoff 和恢复继续执行策略 |
| P3-14 | 自动 PR 草案 | `run ... --auto-pr` 支持在 push 成功后生成 Draft PR |
| P3-15 | PR 元数据增强 | reviewer / label / 交付模板增强 |
| P3-16 | 执行会话恢复入口 | 执行器支持任务级 session attach / resume / continue-latest |
| P3-17 | 执行会话自动识别 | 执行器运行后自动从输出提取 session 引用并生成恢复命令 |
| P3-18 | 终端继续执行 | `run resume --open-terminal` / Web 按钮可直接在 macOS Terminal 打开恢复命令 |
| P3-19 | `ccswitch` 桥接层 | `ccswitch bridge` 把 provider/prompt/resume 串成一条受控桥接链路 |
| P3-20 | 桥接结果可观测层 | bridge 记录步骤状态、失败位置和错误信息，便于后续自动重试与确认 |
| P3-21 | bridge 确认闭环 | bridge 结果进入 `pending_confirmation / confirmed_ready / confirmed_failed` 收口状态 |
| P3-22 | bridge 确认安全门 | 调度器和自动派发在 bridge 未确认时停止推进，避免误自动化 |
| P3-23 | bridge 恢复信号 | 终端恢复步骤自动写本地 signal，补强外部切换的自动证据链 |
| P3-24 | bridge 恢复信号自动确认 | 检测到本地 signal 后可显式启用自动确认，减少一次重复人工收口 |
| P3-26 | 历史会话候选与恢复建议 | 从执行记录整理历史会话候选，并支持显式使用最佳候选恢复 |

### P4 — 平台化

| 编号 | 任务 | 完成标准 |
|------|------|---------|
| P4-1 | 多人协作 | `~/.aios/` 全局配置支持共享项目状态到 Git 远程 |
| P4-2 | Provider 密钥管理 | 加密存储 API Key，不暴露明文 |
| P4-3 | 插件系统 | 支持自定义路由策略、Context Pack 模板、执行器 |
| P4-4 | 桌面端 | Tauri / Electron 打包，脱离终端使用 |

---

## 近期重点（接下来 2 周）

1. P3-25：评估 `ccswitch` 内部状态读取或外部确认替代方案
2. P3-9：补齐成本与执行统计
3. P3-27：评估执行器真实 CLI 接管面
4. P3-28：评估验证失败后的自动二次派发策略
5. P0-2：持续同步操作手册与规划文档

## 下一阶段实施目标

下一阶段默认进入“执行适配 + 拆解增强 + Context 补强”三件套，目标是：

- 在不破坏现有半自动流程的前提下，把自动派发与自动收口逐步接上
- 继续解决复杂目标拆解过浅的问题，而不是只堆执行入口
- 继续补齐成本、模型切换、远程交付这三块，才能接近完整自动交付链

专项规划见 [docs/plans/aios-system-improvement-roadmap.md](/Users/yaxun/SynologyDrive/日常工作/Github/AIOS/docs/plans/aios-system-improvement-roadmap.md)。

---

## 设计决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-07-01 | 模型库改为表格 + 勾选框 | 卡片表单占空间大、信息密度低，表格更适合配置类数据 |
| 2026-07-01 | 暗黑科技风主题 | 与"AI 开发中枢"定位匹配，区别于普通管理后台 |
| 2026-07-01 | 添加项目与项目列表上下排列 | 表单宽度不够且双列布局不对称，单列更整洁 |
| 2026-07-01 | 框体平铺去掉 max-width | 大屏幕上留白过多，信息密度优先 |
| 2026-07-01 | `run` 成为半自动执行主入口 | `handoff` 只适合生成交接文档，不适合承载执行状态机 |
| 2026-07-01 | `ccswitch` 先做适配输出，不直接做自动控制 | 先标准化导出，再评估稳定 CLI 或自动切换能力 |
| 2026-07-02 | 下一阶段优先补执行器适配、任务树、Context Engine | 这三项直接对应当前最大痛点，也最能放大 AIOS 的管理价值 |
| 2026-07-02 | 自动调度先只派发 `ready` 任务，不自动 finish | 先把调度决策接入执行链路，再逐步扩到 review 收口 |
| 2026-07-02 | 自动收口要求显式 `summary`，验证失败时保持 `review_pending` | 先保证收口可控、可审计，避免误把失败任务标记为完成 |
| 2026-07-02 | 自动 Git 提交只在执行开始前非 `.aios/` 工作区干净时生效 | 避免把用户已有脏改动误一起提交，同时不让 `.aios/` 元数据阻塞自动化 |
| 2026-07-02 | `ccswitch` 先接官方 Deep Link 的 prompt 导入，不直接假设稳定 CLI | 先用已公开且可验证的入口缩短人工切换路径，再逐步扩大自动化范围 |
| 2026-07-02 | Provider / Session 先做全局模型库元数据、provider deeplink 和 session handoff，不直接做桌面静默恢复 | 当前缺的是稳定交接数据，不是更多脆弱自动点击 |
| 2026-07-02 | 执行器会话恢复先做 attach / resume / continue-latest，不直接做 session 自动探测 | 先把恢复入口和审计链固定住，再逐步尝试自动恢复 |
| 2026-07-02 | 执行器会话自动识别先做 regex 提取，不直接承诺所有执行器都能稳定给出 session id | 先落地最小可用自动识别，再逐步提升准确率 |
| 2026-07-02 | 终端继续执行先只支持 macOS Terminal.app | 先补最稳定、最小依赖的一跳，把“复制命令再粘贴”收口，再扩终端和桌面接管 |
| 2026-07-02 | `ccswitch` 桥接层先做 provider/prompt/resume 顺序编排，不做 UI 状态确认 | 先把离散动作收成一条可追踪链路，再评估更脆弱的桌面观察与控制 |
| 2026-07-02 | bridge 先做步骤级状态和错误留痕，不直接声称导入成功 | 先让系统知道失败在哪一步，再决定是否继续接桌面确认能力 |
| 2026-07-02 | bridge 确认先用显式状态回写，不伪装成自动读取外部 App 状态 | 先把“系统观察结果”和“操作者确认结果”分离建模，再决定是否补桌面观测能力 |
| 2026-07-02 | 自动派发先尊重 bridge 确认状态，不在未确认时继续推进 | 先把自动化安全门补齐，避免系统自己跨过外部切换确认环节 |
| 2026-07-02 | bridge 终端恢复先补本地 signal 证据，不直接声称外部切换已完全成功 | 先增加一条可自动采集的证据链，再逐步接近更强的外部状态确认 |
| 2026-07-02 | bridge 恢复 signal 自动确认默认关闭，必须显式启用 | signal 只能证明恢复命令已拉起，不能替代对外部会话正确性的最终判断 |
| 2026-07-02 | 历史会话恢复先从 `.aios/executions.json` 派生候选，不新增独立会话库 | 先复用已有审计数据源，把恢复建议做稳，再决定是否拆出专门 registry |
| 2026-07-02 | 自动 Push 默认跳过 main/master，只处理特性分支 | 先降低远程破坏面，再逐步扩到受保护分支和 PR 流程 |
| 2026-07-02 | 自动 PR 只创建 Draft PR，不直接生成 Ready PR | 先让远程交付进入可审查状态，不越过人工审核门槛 |
