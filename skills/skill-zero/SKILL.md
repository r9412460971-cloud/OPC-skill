---
name: skill-zero
description: R9 工作台的元评估 skill（0 号 skill）。用于评判其他 skill 的优劣势，输出结构化评估报告和可执行的改进建议。当用户说"评价一下这个 skill"、"这个 skill 怎么样"、"skill-zero 评估 xxx"、"分析一下某个 skill 的优劣"、"这个 skill 有什么问题和改进空间"时触发。支持对单个 skill 或一组 skill 进行横向对比评估。
---

# Skill-Zero：Skill 优劣评判器

## 作用

像产品经理 + 架构评审委员会一样，系统性地审视 R9 工作台中的任意 skill，给出客观评分、SWOT 分析和优先级改进清单。

## 使用方式

### 单 skill / 小批量评估
1. 用户给出待评估 skill 名称（如 `fund-r9alpha-evaluation`）或一组 skill。
2. 读取对应 skill 的 `SKILL.md` 及目录结构。
3. 按照 [评估框架](references/evaluation-framework.md) 的六个维度打分。
4. 输出评估报告。

### 全量扫描 + PDF 报告
运行配套脚本 `scripts/skill_zero_audit.py`，自动扫描 `.kimi/skills/` 和 `.claude/skills/`，生成 `/Users/r9/Skill_Zero_Audit_Report.pdf`：

```bash
source /Users/r9/.venv_pdf/bin/activate
python3 /Users/r9/.kimi/skills/skill-zero/scripts/skill_zero_audit.py
```

### 指定 skill 深度评估 + PDF 报告
运行 `scripts/skill_zero_deep_eval.py`，对低分或指定 skill 做六维度人工深度评估（含评分标准、SWOT、改进清单）：

```bash
source /Users/r9/.venv_pdf/bin/activate
python3 /Users/r9/.kimi/skills/skill-zero/scripts/skill_zero_deep_eval.py
```

当前脚本内置对 `roll-forward`、`fund-advisor-assistant`、`r9-channel-router`、`variance-commentary`、`grill-me` 的评估数据，输出 `/Users/r9/Skill_Zero_Deep_Evaluation_Report.pdf`。

## 工作流程

### 1. 确认评估对象
- 单 skill：明确 skill 名称和路径 `.kimi/skills/{skill-name}/SKILL.md`
- 多 skill：确认评估目标（横向对比、体系盘点、找短板等）

### 2. 读取材料
- 必读：`SKILL.md`（frontmatter + body）
- 选读：`references/`、`scripts/`、`assets/` 目录结构

### 3. 执行评估
参照 [references/evaluation-framework.md](references/evaluation-framework.md) 的六个维度：

| 维度 | 权重 | 关注点 |
|------|------|--------|
| 触发设计 | 20% | 触发词、description 清晰度、路由准确性 |
| 功能价值 | 25% | 问题明确性、独特价值、与体系契合度 |
| 内容质量 | 25% | 指令可执行性、示例充分性、边界清晰 |
| 结构规范 | 15% | skill-creator 规范、渐进式披露 |
| 依赖与可维护性 | 10% | 外部依赖、脚本测试、更新成本 |
| 体系协同 | 5% | 与上下游 skill 衔接、基础设施引用 |

### 4. 输出报告

使用以下结构输出：

```markdown
# Skill-Zero 评估报告：{skill-name}

## 总体评分
| 维度 | 得分 | 权重 | 加权得分 |
|------|------|------|----------|
| ... | ... | ... | ... |
| **总分** | — | — | **x/5** |

## 优势
- ...

## 劣势
- ...

## 机会
- ...

## 风险
- ...

## 优先级改进清单
1. 【高】...
2. 【中】...
3. 【低】...
```

## 全量评估脚本说明

`scripts/skill_zero_audit.py` 的评分逻辑：
- 读取每个 skill 的 `SKILL.md` frontmatter 与正文结构。
- 基于 description 长度、触发词数量、workflow/示例/引用完整性、基础设施引用、冗余文件等指标进行客观打分。
- 输出包含执行摘要、完整评分表、Top/Bottom 排名、问题清单的 PDF。

**注意**：全量扫描评分基于静态内容，不做深度功能测试，主要用于批量筛查与优先级排序；对单个 skill 的深度诊断仍需人工阅读 SKILL.md 后按 [评估框架](references/evaluation-framework.md) 逐项评判。

## 特别说明

- 评分基于 SKILL.md 和实际文件内容，不依赖假设。
- 若发现某个 skill 存在严重触发重叠或功能真空，需在报告中明确指出。
- 评估应保持建设性，所有劣势都必须对应可执行的改进建议。
