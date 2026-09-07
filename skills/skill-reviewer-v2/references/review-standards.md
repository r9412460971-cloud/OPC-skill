# 审查标准索引

本文件是 skill-reviewer 知识库的**导航入口**。详细规则按职责拆分到各子文件中，按需加载。

---

## 文件索引

| 文件 | 内容 | 何时加载 |
|------|------|---------|
| `references/blocker-checks.md` | B01-B22 阻断检查完整定义（含 B19 安全、B20 安装引导、B21 包体大小、B22 营销导流/外跳） | review.py 报出 blocker 需要理解详情时 |
| `references/suggestion-checks.md` | S01-S14 优化建议 + 自动补全能力表 | 处理 suggestions/ai_actions 时 |
| `references/deep-quality-review.md` | 深度质量评审 4 层 11 维度标准（仅首次上架执行） | 执行第五步深度评审时 |
| `references/functional-testing.md` | 功能验证标准（skill-tester 子 skill） | 执行第七步功能测试时 |
| `references/templates-and-formats.md` | Frontmatter 模板、marketplace.json 格式、审查报告模板、classify 实操示例、收录经验 | 生成报告/补全字段时 |
| `references/subagent-strategy.md` | 批量审查 subagent 调度规则 | 批量审查 ≥2 个 skill 时 |

---

## 前置规范化（R00）速查


| 步骤 | 操作 | 说明 |
|------|------|------|
| R00-1 | UTF-8 BOM 移除 | BOM 导致 YAML 解析器无法识别首行 `---` |
| R00-2 | 编码归一化 | 非 UTF-8 自动转码 |
| R00-3 | 换行符统一 | CRLF → LF |
| R00-4 | YAML 引号修复 | 降低 B02 误报率 |

---

## B01-B22 快速参考

| ID | Check | Auto-fix |
|----|-------|----------|
| B01 | SKILL.md exists and non-empty | ✗ |
| B02 | Valid YAML frontmatter | ✗ |
| B03 | description exists (50-200 chars) | ✗ |
| B04 | description_zh exists | ✓ |
| B05 | description_en exists | ✓ |
| B06 | name matches directory | ✓ |
| B07 | source matches directory | ✓ |
| B08 | frontmatter field order | ✓ |
| B09 | version format valid | ✓ |
| B10 | Markdown body has substance | ✗ |
| B11 | Icon filename matches source | ✓ |
| B12 | version only increases | ✗ |
| B13 | 3 descriptions consistent | ✓ |
| B14 | allowed-tools documented in body | ✗ |
| B15 | references/ & scripts/ links valid | ✗ |
| B16 | No orphan reference files (warn) | ⚠ |
| B17 | Remote source integrity | ✓ |
| B18 | ClawHub package cleaned | ✓ |
| B19 | Security & universality | ✗ |
| B20 | Install + config guide completeness | ✓ LLM 裁决 |
| B21 | Package size (≤100KB/300KB) | ✗ |
| B22 | Marketing drainage / external redirect (召回→LLM 裁决) | ✗ |

> 详细定义 → `references/blocker-checks.md`

---

## S01-S14 快速参考

| ID | Suggestion |
|----|-----------|
| S01 | description 触发词覆盖度 |
| S02 | description_zh 长度 25-35 字 |
| S03 | description_en 长度 60-80 字符 |
| S04 | SKILL.md body 行数合理 |
| S05 | 有快速开始示例 |
| S06 | 大 reference 文件有 grep 模式 |
| S07 | homepage 字段有效 |
| S08 | 品牌产品有 Logo |
| S09 | License 兼容性 |
| S10 | 内容简洁性 |
| S11 | 渐进式加载 |
| S12 | examples_zh/en 必填 |
| S13 | tags_zh/en 详情页关键词（Listing 草稿建议，不写入包体） |
| S14 | category 字段验证（Listing 字段，reviewer 不验证包体） |

> 详细定义 → `references/suggestion-checks.md`
