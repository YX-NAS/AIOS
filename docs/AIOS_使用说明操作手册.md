# AIOS 使用说明操作手册

> 版本：v0.38.0 | 更新日期：2026-07-03

---

## 1. 文档目的

本手册覆盖 AIOS 多模型开发中枢的完整使用流程，包括：

- 安装与启动
- 多项目管理
- 项目初始化与扫描
- 任务创建与智能拆解
- 模型路由与 Context Pack 生成
- 半自动执行流程（人工切换模型）
- CLI 命令参考
- ccswitch 适配文件使用
- 模型库管理

**当前版本范围：** 半自动执行（人工切换 ccswitch，AIOS 负责任务管理、路由推荐、Pack 生成、执行记录），自动执行层已具备原型能力但仍在迭代中。

**未包含能力：** 本版本不会自动切换 ccswitch、不会自动调用 Codex/Claude Code CLI。

---

## 2. 运行环境

- Python 3.10+
- macOS / Linux / Windows
- Node.js 20+（仅教程视频渲染需要）

验证环境：

```bash
python3 --version
```

---

## 3. 安装

```bash
git clone https://github.com/YX-NAS/AIOS.git
cd AIOS
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

如果 editable install 报错（旧版 pip），先升级安装工具：

```bash
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

安装后验证：

```bash
aios status
```

若看到 `AIOS project is not initialized`，说明安装成功，只是当前目录还没有项目。

---

## 4. 启动方式

### 4.1 多项目启动器（推荐）

```bash
aios launcher --port 8755
```

浏览器访问 `http://127.0.0.1:8755`。

启动器首页可以：
- 登记多个项目目录
- 查看项目运行状态
- 一键启停单项目实例
- 管理全局模型库
- 跳转到各项目自己的工作区

### 4.2 单项目 Web UI

```bash
aios web --port 8765 --root /path/to/your-project
```

浏览器访问 `http://127.0.0.1:8765`。

单项目 Web UI 可以：
- 查看项目状态和文件索引
- 创建/管理任务
- 目标拆解
- 查看模型推荐
- 开始半自动执行
- 完成回写

### 4.3 快速启动脚本

macOS 用户可以直接双击项目根目录下的：
- `AIOS_启动WebUI.command`
- `AIOS_停止WebUI.command`

---

## 5. 核心工作流

### 步骤 1：注册项目

在启动器首页（`http://127.0.0.1:8755`）点击「添加项目」，输入项目根目录的绝对路径（例如 `/Users/yaxun/SynologyDrive/日常工作/Github/xiazhi-ai.git`）。

### 步骤 2：初始化 + 扫描

进入项目控制台，点击「初始化」按钮创建 `.aios/` 知识目录，然后点击「扫描」分析项目结构。

或者 CLI：

```bash
aios init --root /path/to/project
aios scan --root /path/to/project
```

### 步骤 3：创建任务 / 目标拆解

**创建单个任务：**

```bash
aios task create "修复用户登录超时问题" --root /path/to/project
```

**目标拆解（自动拆分多个子任务）：**

```bash
aios task plan "添加用户画像模块，包含数据采集、存储、分析、前端展示" --root /path/to/project
```

系统会根据目标类型（bug 修复 / 功能开发 / 系统构建）自动按不同策略拆解子任务。

Web UI 中直接输入目标描述，点击「目标拆解」即可。

### 步骤 4：查看路由推荐

```bash
aios route TASK-ID --root /path/to/project
```

系统会根据任务复杂度、类型、技术栈，从全局模型库中推荐最合适的模型。

### 步骤 5：开始执行

在 Web UI 中，进入任务详情，点击「开始执行」。系统会：

1. 为任务生成一条执行记录
2. 生成 Context Pack（包含项目背景、规则、相关文件）
3. 生成任务交接单
4. 显示推荐模型和兜底模型

### 步骤 6：人工切换模型并执行

1. **复制 Context Pack**（点击复制按钮）
2. **人工在 ccswitch 中切换到推荐模型**（当前仍需手动操作）
3. **打开 Codex 或 Claude Code**，粘贴 Context Pack 到对话框
4. 按交接单中的验收标准完成开发

### 步骤 7：完成回写

回到 AIOS 项目控制台，在任务详情中填写：
- 实际使用的模型
- 测试命令和测试结果
- 完成总结

点击「完成执行」，系统自动更新：
- 任务状态 → `done`
- 执行记录 → `finished`
- `changelog.md` 追加完成记录
- `memory.md` 追加经验备忘

---

## 6. CLI 命令参考

| 命令 | 功能 |
|------|------|
| `aios init` | 初始化 `.aios/` 知识目录 |
| `aios scan` | 扫描项目文件结构 |
| `aios status` | 查看项目状态 |
| `aios task create "标题"` | 创建新任务 |
| `aios task plan "目标"` | 按目标拆解子任务 |
| `aios task list` | 列出所有任务 |
| `aios task show TASK-ID` | 查看任务详情 |
| `aios route TASK-ID` | 查看模型推荐 |
| `aios pack TASK-ID` | 生成 Context Pack |
| `aios handoff TASK-ID` | 生成任务交接单 |
| `aios run --manual TASK-ID` | 手动开始执行 |
| `aios run status TASK-ID` | 查看执行状态 |
| `aios run finish TASK-ID --summary "..."` | 完成执行回写 |
| `aios ccswitch export TASK-ID` | 导出 ccswitch 适配文件 |
| `aios ccswitch provider TASK-ID` | 导出 Provider Deep Link |
| `aios ccswitch session TASK-ID` | 导出 Session Handoff |
| `aios model probe MODEL-ID` | 探测模型 Provider 可用性 |
| `aios model list` | 查看所有模型 |
| `aios web` | 启动单项目 Web UI |
| `aios launcher` | 启动多项目管理首页 |

---

## 7. ccswitch 适配文件使用

AIOS 可以导出 ccswitch 适配文件：

```bash
aios ccswitch export TASK-ID
```

生成的文件保存为 `.aios/ccswitch/TASK-ID.json`。

**使用方法（当前人工流程）：**

1. 在 AIOS 中点击「复制 ccswitch Deep Link」或运行 CLI 导出
2. 打开 ccswitch 应用
3. 通过其界面切换到推荐模型（当前仍需手动操作）
4. 重新启动 Codex 或 Claude Code
5. 在 AI 对话中粘贴 Context Pack 开始执行

**注意：** AIOS v0.38 已实现 `ccswitch` 桥接层原型（`P3-19`），能够按 provider → prompt → resume 顺序编排桥接动作，但目前自动切换仍需人工确认和操作。全自动切换将在后续版本实现。

---

## 8. 全局模型库管理

模型库维护入口在启动器首页（`http://127.0.0.1:8755`）。

能力：
- 查看所有内置模型（含 provider、适用任务类型、优先级）
- 新增自定义模型
- 编辑模型信息（ID、名称、provider 配置）
- 删除模型
- 恢复默认模型库
- 一键探测模型 Provider 可达性
- 设置模型单价（用于成本估算）

模型库影响范围：
- 任务创建时的模型路由推荐
- 目标拆解时的模型建议
- Context Pack 中的模型信息
- 项目控制台的成本统计

---

## 9. 当前项目状态与能力矩阵

### 已完成

| 能力 | 状态 | 说明 |
|------|------|------|
| 项目初始化 | ✅ 稳定 | `aios init` 生成 `.aios/` 目录 |
| 项目扫描 | ✅ 稳定 | 自动索引项目文件 |
| 任务管理 | ✅ 稳定 | 创建 / 查看 / 完成任务 |
| 目标拆解 | ✅ 稳定 | bug/功能/系统三类拆解策略 |
| 模型路由 | ✅ 稳定 | 任务特征匹配模型推荐 |
| Context Pack | ✅ 稳定 | 分层 Pack + 质量校验 |
| 半自动执行 | ✅ 稳定 | 执行记录 + Pack + 交接单 |
| 多项目启动器 | ✅ 稳定 | 统一首页管理多项目 |
| 全局模型库 | ✅ 稳定 | 增删改查 + Provider 探测 |
| ccswitch 导出 | ✅ 稳定 | 适配文件 / Deep Link / Handoff |
| 执行回写 | ✅ 稳定 | changelog + memory 自动更新 |
| 成本统计 | ✅ 原型 | 模型单价 + Token 估算 |
| 自动 Git 提交 | ✅ 原型 | 本地提交 + 自动 Push |
| 自动 PR | ✅ 原型 | Draft PR 创建 |
| 失败分类恢复 | ✅ 原型 | 分类级重试 + 冷却护栏 |
| Provider 就绪探测 | ✅ 原型 | 鉴权变量 + API 握手探测 |
| 终端续接 | ✅ 原型 | macOS Terminal 一键继续 |
| 会话恢复 | ✅ 原型 | attach / resume / 历史候选 |

### 进行中 / 待开发

| 能力 | 状态 | 说明 |
|------|------|------|
| ccswitch 自动切换 | 🔄 设计中 | P3-11 桥接层已落地，待全自动 |
| Codex/Claude Code 自动调用 | 🔄 设计中 | 执行器适配层已有原型 |
| 全自动调度闭环 | 📋 规划中 | 目标 → 拆解 → 分发 → 执行 → 验证 → 回写 |

---

## 10. 教程视频

项目附带 Remotion 制作的教程视频，位于：

`docs/aios-tutorial/out/aios-tutorial-v0.38.mp4`

视频时长 3 分钟，覆盖：
1. AIOS 概述
2. 安装与启动
3. 初始化与扫描
4. 任务管理与拆解
5. 模型路由与 Context Pack
6. 半自动执行流程
7. 多项目启动器
8. 完整能力矩阵
9. 推荐工作流
10. CLI 命令速览
11. 核心价值说明

如需重新渲染视频：

```bash
cd docs/aios-tutorial
npm install
npx remotion render AIOSTutorial out/aios-tutorial.mp4
```

---

## 11. 常见问题

**Q: 启动 launcher 后页面空白？**
A: 确保 `.aios-local/projects.json` 存在（至少一个项目已登记）。如果文件不存在，手动在启动器首页点击「添加项目」注册一个。

**Q: 如何同时管理多个项目？**
A: 使用 `aios launcher` 启动多项目首页，每个项目独立运行和独立 `.aios/` 数据，互不串扰。不需要手动管理端口。

**Q: 目标拆解后得到的子任务太粗糙？**
A: 尝试在目标描述中更具体地说明模块划分和期望的拆解粒度。例如「开发用户系统」vs「开发用户系统，包含注册、登录、权限管理、个人中心四个模块」。

**Q: Tensorflow 任务应该推荐哪个模型？**
A: 系统会根据任务类型（`simple_coding` / `complex_coding` / `debug`）从模型库中匹配。你可以在模型库里为特定模型标记适用任务类型来影响推荐结果。

**Q: 切换到新模型后上下文丢失？**
A: AIOS 的 Context Pack 就是为解决这个问题设计的。每次执行前生成一份完整的 Pack（包含项目背景、规则、相关文件），粘贴给新模型即可无缝续接。

---

> 📁 仓库：[YX-NAS/AIOS](https://github.com/YX-NAS/AIOS) · 📄 许可证：Apache-2.0 · 🔖 版本：v0.38.0
