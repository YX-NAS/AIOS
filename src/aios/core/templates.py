from __future__ import annotations

from aios.utils.text import today


DEFAULT_ROUTING = {
    "architecture": {
        "preferred_models": ["gpt-5.5", "claude"],
        "fallback_models": ["deepseek-v4-pro"],
        "max_cost_level": "high",
        "reason": ["涉及架构设计", "需要高质量推理", "需要保持长期上下文一致"],
    },
    "complex_coding": {
        "preferred_models": ["gpt-5.5"],
        "fallback_models": ["deepseek-v4-pro"],
        "max_cost_level": "high",
        "reason": ["涉及核心代码", "需要理解业务规则", "需要较强推理能力"],
    },
    "simple_coding": {
        "preferred_models": ["deepseek-v4-pro", "gpt-5.4-mini"],
        "fallback_models": ["minimax-m2.7-highspeed"],
        "max_cost_level": "medium",
        "reason": ["实现边界清晰", "适合高性价比代码模型"],
    },
    "batch_edit": {
        "preferred_models": ["deepseek-v4-flash", "minimax-m2.7-highspeed"],
        "fallback_models": ["deepseek-v4-pro"],
        "max_cost_level": "low",
        "reason": ["批量编辑", "低推理成本优先"],
    },
    "bug_fix": {
        "preferred_models": ["gpt-5.5", "deepseek-v4-pro"],
        "fallback_models": ["claude"],
        "max_cost_level": "high",
        "reason": ["需要定位根因", "需要保护既有行为"],
    },
    "code_review": {
        "preferred_models": ["gpt-5.5", "claude"],
        "fallback_models": ["deepseek-v4-pro"],
        "max_cost_level": "high",
        "reason": ["需要审查风险", "需要发现回归和测试缺口"],
    },
    "testing": {
        "preferred_models": ["deepseek-v4-pro", "gpt-5.5"],
        "fallback_models": ["minimax-m2.7-highspeed"],
        "max_cost_level": "medium",
        "reason": ["需要构造测试覆盖", "实现边界通常明确"],
    },
    "documentation": {
        "preferred_models": ["minimax-m2.7-highspeed", "deepseek-v4-flash"],
        "fallback_models": ["gpt-5.5"],
        "max_cost_level": "low",
        "reason": ["偏文档整理", "低成本优先"],
    },
    "data_processing": {
        "preferred_models": ["deepseek-v4-pro", "gpt-5.5"],
        "fallback_models": ["claude"],
        "max_cost_level": "medium",
        "reason": ["偏脚本和数据处理", "需要稳定实现"],
    },
    "ui_design": {
        "preferred_models": ["gpt-5.5", "claude"],
        "fallback_models": ["deepseek-v4-pro"],
        "max_cost_level": "medium",
        "reason": ["涉及用户体验", "需要兼顾实现和交互"],
    },
    "deployment": {
        "preferred_models": ["gpt-5.5", "deepseek-v4-pro"],
        "fallback_models": ["claude"],
        "max_cost_level": "high",
        "reason": ["涉及部署风险", "需要谨慎验证"],
    },
}


def project_yaml(name: str, project_type: str) -> str:
    return f"""project:
  name: "{name}"
  description: ""
  type: "{project_type}"
  stage: "development"
  language: []
  framework: {{}}
  owner: ""
aios:
  version: "0.31.0"
  initialized_at: "{today()}"
  last_scan_at: null
  default_model: "gpt-5.5"
  default_context_pack: "gpt"
"""


def context_md(name: str) -> str:
    return f"""# 项目上下文

## 项目目标

{name} 的项目目标待补充。

## 当前阶段

MVP 开发阶段。

## 技术栈

待扫描识别。
"""


ARCHITECTURE_MD = """# 架构说明

## 总体架构

待补充。

## 模块划分

待补充。
"""

DECISIONS_MD = """# 架构决策记录

暂无决策。
"""

RULES_MD = """# 项目规则

- 只修改和当前任务直接相关的文件。
- 修改前先确认上下文和验收标准。
- 涉及核心逻辑的修改必须补充测试或说明无法测试的原因。
"""

MEMORY_MD = """# 项目长期记忆

暂无记录。
"""

CHANGELOG_MD = """# AIOS Changelog
"""
