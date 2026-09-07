# 优化建议（S01-S14）与自动补全

**非阻断，仅建议改进。**

---

## S01：`description` 触发词覆盖度

检查 `description` 是否包含具体使用场景和触发词。好的 description 应该：
- 包含具体的动词和名词组合（如"create notes"、"search papers"）
- 提及 CLI 工具名（如"via the `memo` CLI"）
- 列出使用条件（如"on macOS"）

## S02：`description_zh` 长度适中（25-35 字）

## S03：`description_en` 长度适中（60-80 字）

## S04：SKILL.md body 行数合理

| 复杂度 | 推荐行数 |
|--------|----------|
| 简单（仅 SKILL.md） | ≤ 200 行 |
| 中等（+ references） | ≤ 400 行 |
| 复杂（+ scripts） | ≤ 500 行 |

超出时建议拆分到 references/。

## S05：有快速开始示例

SKILL.md body 应包含至少一个实际使用示例或代码块。

## S06：大 reference 文件有 grep 搜索模式

当 references/ 中单个文件超过 10,000 words 时，建议在 SKILL.md 中提供 grep 搜索模式。

## S07：`homepage` 字段有效

如果有 homepage，应该是可访问的 URL。

## S08：品牌产品有 Logo

有品牌归属的产品应在 `icons/` 有对应图标。Logo 必须来自官方渠道。

## S09：License 兼容性

开源项目应确认 License 兼容性（Apache 2.0、MIT 等）。

## S10：内容简洁性

避免重复、冗余内容。Reference 中的内容不应在 SKILL.md 中重复。

## S11：渐进式披露（Progressive Disclosure）

检查 skill 是否合理拆分内容，避免将所有内容平铺在 SKILL.md body 中一次性注入上下文。

**审查要点**：
- SKILL.md body 是否只包含 AI 立即需要的内容（流程、核心规则、导航索引）？
- 详细标准、模板、长篇示例等是否拆分到辅助文件中按需加载？
- 辅助文件是否职责单一，能被精准加载？
- body 中是否提供了清晰的导航结构（表格/链接），让 AI 知道去哪找详情？

## S12：`examples_zh`/`examples_en` 必填

marketplace.json 条目必须包含：
- `examples_zh`：2-4 条中文自然语言触发示例
- `examples_en`：2-4 条英文自然语言触发示例

**写作原则**：
- 以普通用户的真实口吻写，不露出技术名称
- 覆盖该 skill 最核心的 1-2 个功能
- 中英文各自独立写，不要直译

**好的示例**：
```json
"examples_zh": ["北京今天天气怎么样", "帮我查下这周上海的天气预报"],
"examples_en": ["What's the weather like in London today?", "Give me a 7-day forecast for New York"]
```

```json
"examples_zh": ["帮我记一下明天开会要带的材料", "搜索上周关于项目方案的笔记"],
"examples_en": ["Jot down the key points from today's meeting", "Search my notes about the Q2 budget"]
```

**不好的示例**：
```json
// ❌ 露出工具名
"examples_zh": ["用 weather skill 查询北京天气", "使用 wttr.in 获取天气数据"]
// ❌ 太技术，普通用户不会这样说
"examples_zh": ["调用天气API获取实时气温数据", "查询JSON格式的天气预报"]
// ❌ 中英文直译
"examples_zh": ["今天伦敦天气怎么样"],
"examples_en": ["How is the weather in London today"]   // 完全直译，应各自独立写
// ❌ 太泛，没有具体场景
"examples_zh": ["帮我做点什么", "用一下这个功能"]
```

## S13：`tags_zh`/`tags_en` 详情页关键词（平台 Listing 字段）

`tags_zh` / `tags_en` 属于平台 Listing 元数据，用于详情页关键词与后续检索召回，不决定 Skill 分类。分类只由 `category` / `category_list` 决定。

reviewer-v2 不检查、不补全、不要求 SKILL.md 包体包含 tags。若报告中需要提供参考，只能作为 Listing Profile 建议，并标记为 `draft`。

## S14：Category 字段验证（平台 Listing 字段）

`category` / `category_list` 属于平台 Listing 元数据，应基于 Listing Profile 与平台分类表处理。reviewer-v2 不验证 SKILL.md 中的 category，也不把 tags 当分类使用。

---

## 自动补全能力表

| 字段 | 缺失时策略 | 更新时策略 |
|------|-----------|-----------|
| `name` | 使用目录名 | 不变 |
| `description` | **不补全**，要求人工撰写 | 不变 |
| `description_zh` | AI 翻译 description → Listing Profile 候选 | 沿用远程仓库值（如有） |
| `description_en` | 截取精简 description → Listing Profile 候选 | 沿用远程仓库值（如有） |
| `version` | 有真实来源填写，否则不写 | 仅升不降 |
| `tags_zh`/`tags_en` | 不写入 SKILL.md；如需提供，仅作为 Listing Profile 关键词草稿 | 保留 Listing Profile / 平台值 |
| `examples_zh`/`examples_en` | AI 生成 2-4 条 → Listing Profile 候选 | 保留原值 |
| `source` | 使用目录名 | 不变 |

**远程回退逻辑**：更新场景中，如果新版本缺少 description_zh/en，沿用本地已有值或远程仓库旧版值，不留空。
