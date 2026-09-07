# 模板与格式参考

---

## Frontmatter 完整模板

```yaml
---
name: skill-name
description: "AI-facing detailed description with trigger scenarios (50-200 chars)"
description_zh: "简短中文描述（25-35字）"
description_en: "Short English description (60-80 chars)"
version: 1.0.0
homepage: https://example.com
allowed-tools: Read,Write,Bash
metadata:
  clawdbot:
    emoji: 🔧
    requires:
      bins:
        - required-tool
    install:
      - package-manager: brew
        command: "brew install required-tool"
---
```

字段顺序：`name` → `description` → `description_zh` → `description_en` → `version` → `homepage` → `allowed-tools` → `metadata`

---

## marketplace.json 完整条目格式

```json
{
  "name": "skill-name",
  "description": "AI-facing detailed description (50-200 chars)",
  "description_zh": "简短中文描述（25-35字）",
  "description_en": "Short English description (60-80 chars)",
  "source": "skill-name",
  "version": "1.0.0",
  "examples_zh": ["中文触发示例1", "中文触发示例2"],
  "examples_en": ["English trigger example 1", "English trigger example 2"]
}
```

**8 个包体核心字段**：name, description, description_zh, description_en, source, version, examples_zh, examples_en。`category`、`category_list`、`tags_zh`、`tags_en` 属于平台 Listing 元数据，不要求写入 SKILL.md。

> `version` 仅在有真实来源时填写。

---

## 审查报告模板

```markdown
## 审查报告：<skill-name>

**审查时间**：YYYY-MM-DD HH:mm
**审查对象**：<path>
**来源**：<clawhub|skillhub|git|local>

### 自动补全（共 N 项）
⚠ <field>: <补全操作说明>

### 阻断问题（共 N 项）
❌ B<XX>: <问题描述>

### 优化建议（共 N 项）
💡 S<XX>: <建议说明>

### 安装引导检查
- [x] CLI 安装命令完整
- [ ] API Key 获取方式缺失

### 深度质量评审
| 维度 | 评级 | 判断 |
|------|------|------|
| AI 可执行性 | 优/良/待改进 | <一句话> |
| ... | ... | ... |

**改进建议**：（仅列出待改进项）

### 功能验证
✅/⚠/❌ <测试场景> → <结果>

### 结论
🟢 通过 / 🔴 不通过（N 个阻断问题需修复）
```

---

## Listing 字段草稿建议说明

`category`、`category_list`、`tags_zh`、`tags_en` 不属于 reviewer-v2 的包体检查范围。

如 reviewer 在报告中提供 Listing Profile 建议，应遵循：

- `category` / `category_list`：平台分类字段，只能从 Operation Platform 分类表选择合法 category id。
- `tags_zh` / `tags_en`：详情页关键词字段，围绕核心能力、品牌、场景、用户意图生成；不决定分类，也不要求等同分类名。
- 建议必须标记为 `draft`，不得视为已确认上架字段。

---

## 收录经验

### 旧 /command 模式迁移

部分早期 skill 使用斜杠命令机制（`/bolder`、`/audit`）：
- 移除 `/command` 前缀，改为自然语言触发词写在 `description` 中
- 原 `commands/` 子目录扁平化到 `references/`
- SKILL.md body 改为场景化能力导航表格

### 大型 skill（30+ reference 文件）

超过 10 个 reference 文件时采用三层加载策略：
- **Layer 1**（SKILL.md body）：≤ 300 行，只放导航表格和核心原则
- **Layer 2**（按需加载）：读取用户需求对应的 1-2 个 reference 文件
- **Layer 3**（全量）：仅在深度审查等罕见场景

### GitHub 开源项目收录

- 确认 License 兼容性
- `homepage` 指向原始仓库
- 结构不符合规范时需适配
- `version` 从 GitHub releases tag 获取，无 release 则不写
