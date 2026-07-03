# AIOS 测试计划 v0.38

生成时间：2026-07-03
对应开发方案：docs/DEV_PLAN_v038.md

---

## 1. 测试策略总览

### 1.1 测试金字塔

```
          ┌─────┐
          │ E2E │  端到端：全自动执行链路
         ┌┴─────┴┐
         │ 集成   │  模块间交互：CLI → Core → Web
        ┌┴───────┴┐
        │  单元    │  纯函数、数据模型、工具函数
       └──────────┘
```

### 1.2 测试原则

1. **每个新模块必须有单元测试**：核心逻辑覆盖 > 80%
2. **每个新 CLI 命令必须有集成测试**：覆盖成功路径和至少 1 个失败路径
3. **每次发布前跑全量回归测试**：`python -m pytest` 全绿
4. **自动化验收优先**：能用脚本验证的不用人工判断

### 1.3 测试环境

- Python 3.10+
- pytest + 标准库 mock
- 临时目录作为测试项目根路径
- 不依赖真实模型 API 调用（模拟响应）

---

## 2. 单元测试计划

### 2.1 P3-36：仓库上下文检索增强

#### 2.1.1 仓库地图生成 (`test_repo_map.py`)

| 用例编号 | 用例名称 | 输入 | 预期输出 |
|----------|----------|------|----------|
| UT-RM-001 | 空项目生成空地图 | 空目录 | modules 为空列表 |
| UT-RM-002 | 单层文件识别 | src/main.py, README.md | 识别为顶层模块 |
| UT-RM-003 | 多层目录结构 | src/aios/core/, src/aios/web/ | 正确嵌套模块层级 |
| UT-RM-004 | 识别入口文件 | 包含 setup.py, __init__.py | entry_points 包含正确文件 |
| UT-RM-005 | 排除构建产物 | dist/, build/, .venv/ | 路径不出现在地图中 |
| UT-RM-006 | 排除 .aios 目录 | .aios/ 任意文件 | 不出现在地图中 |
| UT-RM-007 | 排除 .git 目录 | .git/ 任意文件 | 不出现在地图中 |
| UT-RM-008 | 识别 Python 包 | src/aios/__init__.py | 标记为 package |
| UT-RM-009 | 识别热点文件 | git log 最近变更 | hot_files 包含变更文件 |
| UT-RM-010 | 符号提取 | Python 文件含 def/class | symbols 包含函数/类名 |

#### 2.1.2 有界搜索 (`test_bounded_search.py`)

| 用例编号 | 用例名称 | 输入 | 预期输出 |
|----------|----------|------|----------|
| UT-BS-001 | 空索引搜索 | 空 search_index | 返回空列表 |
| UT-BS-002 | 关键词精确匹配 | "execution" | 返回 executions.py 等匹配文件 |
| UT-BS-003 | 关键词无匹配 | "nonexistent_keyword" | 返回空列表 |
| UT-BS-004 | 多关键词搜索 | "task execution" | 返回两个关键词的并集结果 |
| UT-BS-005 | 结果按相关性排序 | 多个匹配文件 | 按匹配数降序排列 |
| UT-BS-006 | 结果数量限制 | limit=5 | 返回不超过 5 条 |
| UT-BS-007 | 目录范围限定 | subdir="core" | 只返回 core 下文件 |
| UT-BS-008 | 文件类型过滤 | extensions=[".py"] | 只返回 .py 文件 |
| UT-BS-009 | 排除模式支持 | exclude=["test_*.py"] | 不返回 test_ 开头文件 |

#### 2.1.3 智能文件选取 (`test_smart_selection.py`)

| 用例编号 | 用例名称 | 输入 | 预期输出 |
|----------|----------|------|----------|
| UT-SS-001 | 任务标题关联 | 标题含 "execution" | execution 相关文件权重更高 |
| UT-SS-002 | 任务类型关联 | testing 类型 | test 文件权重更高 |
| UT-SS-003 | 手动标注合并 | 标注文件列表 | 手动文件 + 自动选取合并去重 |
| UT-SS-004 | 选取理由生成 | 选取结果 | 每条结果附带选取理由 |
| UT-SS-005 | 选取数量上限 | 大仓库 | 不超过可配置上限（默认 30） |
| UT-SS-006 | 必含核心配置 | 任意任务 | pyproject.toml/setup.py 等优先包含 |

### 2.2 P3-37：执行安全护栏

#### 2.2.1 卡死检测 (`test_stuck_detection.py`)

| 用例编号 | 用例名称 | 输入 | 预期输出 |
|----------|----------|------|----------|
| UT-SD-001 | 正常输出不触发 | 每秒有输出的日志 | stuck=false |
| UT-SD-002 | 超时无输出触发 | 30秒无任何输出 | stuck=true, reason=no_output |
| UT-SD-003 | 循环相同行触发 | 连续5次相同行 | stuck=true, reason=repeated_pattern |
| UT-SD-004 | 不同内容循环不误判 | 交替不同内容的循环 | stuck=false |
| UT-SD-005 | 配置超时阈值 | timeout=10 | 10秒后触发 |
| UT-SD-006 | 空输入处理 | stdout="", stderr="" | 从启动时间算超时 |

#### 2.2.2 执行心跳 (`test_heartbeat.py`)

| 用例编号 | 用例名称 | 输入 | 预期输出 |
|----------|----------|------|----------|
| UT-HB-001 | 心跳正常 | 每秒写入心跳 | alive=true |
| UT-HB-002 | 心跳超时 | 停止写入心跳 | alive=false, reason=timeout |
| UT-HB-003 | 心跳文件格式 | 写入的心跳文件 | JSON 格式，含 timestamp 和 pid |
| UT-HB-004 | 进程已死检测 | 心跳文件存在但 pid 不存在 | alive=false, reason=process_dead |
| UT-HB-005 | 清理过期心跳 | 执行结束 | 心跳文件被删除 |

### 2.3 P3-40：弹性上下文管理

#### 2.3.1 Token 预算 (`test_token_budget.py`)

| 用例编号 | 用例名称 | 输入 | 预期输出 |
|----------|----------|------|----------|
| UT-TB-001 | 预算内不裁剪 | token 总数在预算内 | 原样返回 |
| UT-TB-002 | 超出预算时裁剪 | token 总数超过预算 | 按层裁剪，文件层先裁 |
| UT-TB-003 | 预算太小无法裁剪 | 预算连核心内容都不够 | 保留核心内容 + 警告 |
| UT-TB-004 | 模型窗口默认预算 | model=gpt-5.5 (200k) | 预算取上下文窗口 80% |
| UT-TB-005 | 手动预算优先 | --budget 50000, model=gpt-5.5 | 使用 50000 而非默认 |
| UT-TB-006 | 中文 token 估算 | 中英混合文本 | 估算结果合理（不严重偏差） |

#### 2.3.2 上下文质量 (`test_context_quality.py`)

| 用例编号 | 用例名称 | 输入 | 预期输出 |
|----------|----------|------|----------|
| UT-CQ-001 | 高相关 Pack | 任务标题含关键词 | relevance_score > 0.5 |
| UT-CQ-002 | 低相关 Pack | 任务与文件无关 | relevance_score < 0.3 |
| UT-CQ-003 | 完整性检查 | 含关键模块文件 | completeness 评分 |
| UT-CQ-004 | 冗余度检查 | 包含无关文件 | redundancy 评分 > 0 |
| UT-CQ-005 | 质量报告格式 | 评估结果 | 三项评分 + 改进建议 |

### 2.4 P3-38：跨模型审查工作流

#### 2.4.1 审查任务 (`test_review.py`)

| 用例编号 | 用例名称 | 输入 | 预期输出 |
|----------|----------|------|----------|
| UT-RV-001 | 创建审查任务 | 任务 ID | 审查子任务正确创建 |
| UT-RV-002 | 审查模型路由 | coding 类任务 | 审查模型不同于原任务模型 |
| UT-RV-003 | 审查结论结构化 | 审查结果 | 含 status + issues + suggestions |
| UT-RV-004 | 审查不通过处理 | 审查未通过 | 原任务状态回退 |
| UT-RV-005 | 审查通过处理 | 审查通过 | 原任务保持 done |

### 2.5 P3-41：执行会话续接

#### 2.5.1 会话快照 (`test_session_persist.py`)

| 用例编号 | 用例名称 | 输入 | 预期输出 |
|----------|----------|------|----------|
| UT-SP-001 | 快照保存 | 执行中的任务 | 快照文件正确创建 |
| UT-SP-002 | 快照恢复 | 有效快照文件 | 恢复执行状态和数据 |
| UT-SP-003 | 快照数据完整性 | 多字段执行记录 | 所有关键字段被保存 |
| UT-SP-004 | 无效快照报错 | 损坏的快照文件 | 抛出明确错误 |
| UT-SP-005 | 健康检查通过 | 项目状态干净 | health_status=ok |
| UT-SP-006 | 健康检查失败 | git 有未提交变更 | health_status=warning |

---

## 3. 集成测试计划

### 3.1 CLI 集成测试

| 用例编号 | 用例名称 | 测试步骤 | 预期结果 |
|----------|----------|----------|----------|
| IT-CLI-001 | repo map 完整流程 | init → repo map → 验证输出 | 生成有效 JSON 文件 |
| IT-CLI-002 | repo search 完整流程 | repo map → repo search "task" | 返回匹配文件列表 |
| IT-CLI-003 | smart pack 完整流程 | init → task create → pack --smart | Pack 文件大小 < 默认 Pack |
| IT-CLI-004 | guard 完整流程 | 启动执行 → guard status | 显示安全状态 |
| IT-CLI-005 | workflow 模板定义 | workflow define → list | 模板列表含新模板 |
| IT-CLI-006 | session snapshot 流程 | 执行中任务 → snapshot → restore | 状态正确恢复 |

### 3.2 Web API 集成测试

| 用例编号 | 用例名称 | 测试步骤 | 预期结果 |
|----------|----------|----------|----------|
| IT-WEB-001 | /api/repo-map 端点 | GET 请求 | 返回仓库地图 JSON |
| IT-WEB-002 | /api/repo-search 端点 | GET + query 参数 | 返回搜索结果 |
| IT-WEB-003 | /api/guard/status 端点 | GET 请求 | 返回安全状态 |
| IT-WEB-004 | /api/review/create 端点 | POST 请求 | 创建审查任务成功 |
| IT-WEB-005 | /api/session/snapshot 端点 | POST 请求 | 快照创建成功 |
| IT-WEB-006 | Web API 错误格式 | 各种异常请求 | 返回统一 JSON 错误格式 |

### 3.3 执行链路集成测试

| 用例编号 | 用例名称 | 测试步骤 | 预期结果 |
|----------|----------|----------|----------|
| IT-EXEC-001 | 任务创建到执行 | create → route → run | 执行记录正确创建 |
| IT-EXEC-002 | 护栏保护的执行 | auto --guard → 模拟超时 | 触发卡死告警 |
| IT-EXEC-003 | 审查工作流 | 任务完成 → 自动审查 | 审查任务创建并路由正确 |
| IT-EXEC-004 | 会话快照恢复 | 执行中断 → 快照恢复 | 从断点继续 |
| IT-EXEC-005 | smart pack + 自动完成 | pack --smart → 执行 → finish | 全流程通过 |

---

## 4. 端到端测试计划

### 4.1 全自动执行链路 E2E

```
场景 E2E-001：完整功能开发链路

前置条件：
  - AIOS 环境就绪
  - 执行器就绪（mock 模式）
  - 测试项目已初始化

测试步骤：
  1. aios init --name test-project
  2. aios task plan "开发用户登录功能" --draft
  3. aios task draft confirm DRAFT-ID
  4. aios repo map
  5. aios route TASK-ID
  6. aios pack TASK-ID --smart
  7. aios run TASK-ID --executor mock --auto-finish --summary "完成登录"
  8. aios review create TASK-ID
  9. aios review run REVIEW-TASK-ID
  10. aios workflow run TASK-ID --template dev-review-commit

预期结果：
  - 每个步骤成功执行
  - .aios/ 下所有文件正确更新
  - tasks.json 任务状态流转正确
  - executions.json 执行记录完整
  - 无未捕获异常
```

### 4.2 异常恢复 E2E

```
场景 E2E-002：执行中断恢复链路

前置条件：
  - 任务正在执行
  - 执行器模拟中断

测试步骤：
  1. 启动执行后模拟崩溃
  2. aios guard status TASK-ID -> 检测到异常
  3. aios session snapshot TASK-ID -> 保存快照
  4. 修复问题后 aios session restore TASK-ID
  5. 恢复后继续执行

预期结果：
  - 快照包含完整执行状态
  - 恢复后从断点正确继续
  - 最终执行状态正确
```

---

## 5. 回归测试清单

### 5.1 已有功能回归

| 功能 | 测试命令 | 通过标准 |
|------|----------|----------|
| 项目初始化 | `aios init --name test --force` | 生成 .aios/ 目录 |
| 项目扫描 | `aios scan` | 输出文件统计 |
| 任务创建 | `aios task create "测试"` | 生成 TASK ID |
| 模型路由 | `aios route TASK-ID` | 输出推荐模型 |
| Context Pack | `aios pack TASK-ID` | 生成 Pack 文件 |
| 手动执行 | `aios run --manual TASK-ID --start` | 生成执行记录 |
| 执行回写 | `aios run finish TASK-ID --summary "完成"` | 更新任务状态 |
| Web 服务 | `aios web --port 18765` | 启动后 HTTP 200 |
| Launcher | `aios launcher --port 18755` | 启动后 HTTP 200 |
| Ccswitch 导出 | `aios ccswitch export TASK-ID` | 生成 JSON |
| 执行器管理 | `aios executor list` | 显示执行器列表 |
| 模型管理 | `aios model list` | 显示模型库 |
| 模型探测 | `aios model doctor` | 输出就绪状态 |
| 自动恢复链 | `aios run auto --auto-recover-failures` | 恢复逻辑正确 |

### 5.2 全量回归命令

```bash
python -m pytest tests/ -v
AIOS_SKIP_NETWORK_TESTS=1 python -m pytest tests/ -v
```

---

## 6. 测试数据准备

### 6.1 测试项目模板

在 `tests/fixtures/` 下准备：

```
tests/fixtures/
├── empty_project/           # 空项目
├── minimal_project/         # 最小 Python 项目
│   ├── src/
│   │   └── main.py
│   └── setup.py
├── web_project/             # Web 项目（多目录）
│   ├── src/
│   │   ├── api/
│   │   ├── models/
│   │   └── utils/
│   └── package.json
├── large_project/           # 大仓库模拟（100+ 文件生成）
│   └── (自动生成)
└── dirty_repo/              # 含未提交变动的仓库
    ├── src/
    │   └── main.py (modified)
    └── .git/
```

### 6.2 Mock 执行器

```python
# tests/fixtures/mock_executor.py
# 模拟输出不同模式的日志
# 模拟超时、失败、卡死等场景
# 用于 guard 和 heartbeat 测试
```

---

## 7. 验收标准

### 7.1 自动化验收

| 标准 | 阈值 | 验证方式 |
|------|------|----------|
| 单元测试覆盖率 | 新模块 > 80% | `pytest --cov` |
| 集成测试通过率 | 100% | `pytest tests/integration/` |
| 回归测试通过率 | 100% | `pytest tests/ -m "not slow"` |
| 代码风格 | 无 Error | 手动检查（后续引入 ruff） |

### 7.2 手工验收

| 验收项 | 验收方法 |
|--------|----------|
| 仓库地图准确性 | 对测试项目生成地图，人工验证模块划分 |
| Smart Pack 质量 | 对比默认 Pack 和 smart Pack，确认文件删减合理 |
| 护栏告警时效 | 启动模拟超时执行，确认告警时间在阈值内 |
| 审查工作流完整 | 跑通一遍完整审查→修复→重新审查流程 |
| Web UI 新增功能 | 在浏览器中操作新增的 repo、guard、review 面板 |

### 7.3 性能验收

| 指标 | 阈值 |
|------|------|
| 仓库地图生成（100 文件） | < 1 秒 |
| 仓库地图生成（1000 文件） | < 5 秒 |
| 有界搜索（1000 文件） | < 2 秒 |
| Pack 生成 + 智能选取 | 不增加 50% 以上耗时 |
| Web UI 页面加载 | < 2 秒（不含网络请求） |

---

## 8. 测试执行计划

### 阶段 1：基础测试框架（Day 1-2）
- 搭建测试 fixtures 和 mock 工具
- 确保现有测试全部通过
- 补齐 P0-1 中遗漏的测试

### 阶段 2：新模块单元测试（与开发并行）
- 每完成一个模块，同步完成单元测试
- 优先覆盖：repo_map → bounded_search → guard → context_quality

### 阶段 3：集成测试（模块完成后 1-2 天）
- CLI 集成测试
- Web API 集成测试
- 执行链路集成测试

### 阶段 4：E2E 与验收（开发完成后）
- 端到端测试
- 回归测试
- 手工验收

---

## 9. 已知限制

1. **不测试真实模型 API 调用**：所有模型交互用 mock/stub
2. **不测试 macOS Terminal 启动**：跨平台终端测试在 CI 中跳过
3. **不测试 Git 远程操作**：push/PR 测试在 CI 中用 mock
4. **大仓库测试用自动生成**：不在仓库中存储大型测试 fixture
5. **Web UI 功能测试手动进行**：暂不引入浏览器自动化框架
