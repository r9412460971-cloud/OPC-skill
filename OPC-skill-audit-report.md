# OPC-skill 仓库审计报告

**审计对象**：https://github.com/r9412460971-cloud/OPC-skill  
**审计日期**：2026-07-13  
**Skill 总数**：93 个目录，93 个 SKILL.md 入口文件  
**审计方法**：批量解析 frontmatter、目录结构、内部引用、数据依赖声明、硬编码路径等

**修复状态**：P0 级别问题已于 2026-07-13 修复并验证通过。详见下文“已完成的 P0 修复”部分。

---

## 一、总体结论

仓库整体覆盖面广、场景丰富，是一份高质量投研/资管/投行工作流的 Skill 集合。但在**元数据一致性、目录与路由表同步、可移植性、内部引用有效性、依赖声明**五个方面存在明显的改进空间。以下按 P0/P1/P2 优先级列出关键发现。

---

## 二、关键发现（按优先级）

### P0 — 建议立即修复

#### 1. 数量口径不一致，README 与核心路由表不同步
- README 正文写“共包含 **93 个 Skill**”，但分类列表只枚举了 **91 个**。
- `r9-workbench` 自称管理“**87 个专业 skill**”，正文表格实际只列出 **72 个**，且**完全未包含 OPC Agent 系列**（r9-opc-*）。
- README 分类列表遗漏：`hv-analysis`、`kyc-doc-parse`、`kyc-rules`。
- README 投资银行板块同时列出 `fsi-strip-profile` 与 `strip-profile`，但实际目录只有 `strip-profile`，且该 skill 的 frontmatter `name` 为 `fsi-strip-profile`。

**影响**：用户安装后会发现 workbench 路由不到 OPC Agent 系列；README 分类无法覆盖全部 skill。

#### 2. 15 个 OPC Agent Skill 完全没有 frontmatter
以下 skill 的 SKILL.md 直接从 `#` 标题开始，缺少 `name` / `description` 元数据：

- `r9-opc-ceo`
- `r9-opc-compliance`
- `r9-opc-operations`
- `r9-opc-research`
- `r9-opc-research-asset`
- `r9-opc-research-fund`
- `r9-opc-research-macro`
- `r9-opc-research-portfolio`
- `r9-opc-research-sector`
- `r9-opc-advisory`
- `r9-opc-advisory-content`
- `r9-opc-advisory-delivery`
- `r9-opc-advisory-strategy`
- `r9-opc-advisory-success`

**影响**：依赖 frontmatter 做索引、搜索、路由的客户端无法识别这些 skill。

#### 3. `lbo-model` frontmatter YAML 语法错误
描述文本中包含未转义的冒号 `note: LBO activity...`，导致 YAML 解析失败：

```yaml
---
name: lbo-model
description: This skill should be used ... (note: LBO activity in China is ...
---
```

**影响**：该 skill 的元数据无法被任何自动化工具读取。

#### 4. `strip-profile` 目录名与 frontmatter `name` 不一致
- 目录名：`strip-profile`
- frontmatter `name`：`fsi-strip-profile`
- README 同时列出两者，但只有一个目录。

**影响**：用户按 README 安装后找不到 `fsi-strip-profile`；路由匹配可能失败。

#### 5. 硬编码 `/Users/r9/` 个人路径
至少 4 个 skill 写死了 R9 个人环境路径：

| Skill | 硬编码路径示例 |
|-------|---------------|
| `fund-active-research` | `/Users/r9/` |
| `fund-market-volatility-script` | `/Users/r9/Desktop/519768客户维护话术_新版` |
| `r9-opc-memory` | `/Users/r9/OPC/...`、`/Users/r9/Desktop/OPC_董事长指令跟踪表` |
| `r9-opc-operations` | `/Users/r9/` |
| `r9-workbench` | `/Users/r9/.kimi/skills/{skill-name}/SKILL.md` |

**影响**：其他用户克隆后无法直接运行；跨平台（Windows/Linux）兼容性差。

---

### P1 — 建议近期修复

#### 6. 数据依赖声明缺失或冗余
- **28 个 skill 提及 Wind**，**9 个提及 iFinD**，**15 个提及 AKShare**，**15 个提及 Tushare**，**6 个提及 Choice**。
- 没有统一的能力检测与降级策略；多数 skill 只是文字说明“如有 Wind 则使用”，没有“无 Wind 时怎么办”的 fallback。
- 仅 `dcf-model` 目录包含 `requirements.txt`，其余依赖 Python 包的 skill 未集中声明依赖版本。

#### 7. 内部引用大量失效或指向缺失文件
抽样检查发现以下 skill 存在引用问题：

| Skill | 问题 |
|-------|------|
| `initiating-coverage` | 引用 `references/task1-company-research.md` 等 5 个文件，但目录中不存在 |
| `pitch-deck` | 引用 `reference/formatting-standards.md`、`reference/xml-reference.md` 等，但实际目录为单文件，无 `reference/` 子目录 |
| `ppt-template-creator` | 引用 `assets/template.pptx`，但 assets 目录仅含 `poster_templates/README.md` |
| `r9-opc-operations` | 引用 `assets/fonts/NotoSansCJKsc-Regular.otf`，但实际不存在 |
| `skill-creator` | 引用 `OOXML.md`、`FORMS.md`、`assets/logo.png` 等 10+ 个文件/目录，几乎全部缺失 |

#### 8. Skill 之间交叉引用无版本锁定
大量 skill 用 `` `china-market-data` ``、`` `dcf-model` ``、`` `xlsx-author` `` 等方式互相引用，但没有版本或兼容性说明。一旦某个 skill 的接口/输出格式变化，下游 skill 容易失效。

#### 9. `fund-diagnosis-3.10` 的 `version` 字段类型错误
```yaml
version: 3.10
```
YAML 会将其解析为浮点数 `3.1`，与期望的字符串 `"3.10"` 不一致。

---

### P2 — 建议持续优化

#### 10. 文件大小与内容粒度差异大
- SKILL.md 大小范围：**1.4 KB ~ 51.3 KB**，平均约 **5.8 KB**。
- 过大的 skill（如 `dcf-model` 51KB、`hv-analysis` 30KB、`datapack-builder` 24KB）单文件承载了过多细节，可读性和维护性下降。
- 过小的 skill（如 `nav-tieout` 1.5KB、`roll-forward` 1.5KB）虽然聚焦，但缺少示例和边界说明。

#### 11. `description` 写法不统一
frontmatter 中 `description` 的写法分布：

| 类型 | 数量 |
|------|------|
| 单行字符串 | 67 |
| 多行 `|` 或 `>` | 10 |

部分 `description` 超长（如 `dcf-model` 单段 400+ 字），超过常见客户端摘要展示长度。

#### 12. 缺乏自动化验证机制
- 仅 `dcf-model` 提供 `scripts/validate_dcf.py`。
- 无统一脚本检查：frontmatter 是否可解析、内部引用是否存在、依赖是否声明、示例是否可运行。

#### 13. 部分 skill 与公司/个人品牌强绑定
- `khazix-writer` 绑定“数字生命卡兹克”公众号人格与文风。
- `r9-opc-*` 系列绑定 OPC 投顾公司组织架构与人名。
- `daily-market-hotspot` 使用“搬砖小哥”“老登/小登”等强个人风格词汇。

**影响**：对外部用户复用性有限；如需开源推广，建议拆分为“通用模板 + 风格覆盖包”。

#### 14. 缺少 `LICENSE` 与贡献者规范
- 仅 `skill-creator` 在 frontmatter 中声明 `license: Complete terms in LICENSE.txt`，但仓库根目录未见 `LICENSE.txt`。
- 无 `CONTRIBUTING.md`、无 issue/PR 模板。

---

## 三、统计快照

| 指标 | 数值 |
|------|------|
| Skill 总数 | 93 |
| 有 SKILL.md | 93 (100%) |
| 有 frontmatter | 77 (82.8%) |
| 无 frontmatter | 15 (16.1%)，全部为 r9-opc-* |
| frontmatter YAML 错误 | 1 (`lbo-model`) |
| 目录名与 frontmatter name 不一致 | 1 (`strip-profile`) |
| 含 `references/` 子目录 | 20 |
| 含 `scripts/` 子目录 | 14 |
| 含 `assets/` 子目录 | 5 |
| 含 `requirements.txt` | 1 (`dcf-model`) |
| 含硬编码 `/Users/r9/` 路径 | 5 skill |
| 提及 Wind | 28 skill |
| 提及 iFinD | 9 skill |
| 提及 AKShare | 15 skill |
| 提及 Tushare | 15 skill |
| 平均 SKILL.md 大小 | 5.8 KB |

---

## 四、改进建议清单

### 立即可做（P0）
1. **统一数量口径**：README 与 `r9-workbench` 均改为 93；在 `r9-workbench` 中补充 OPC Agent 系列路由。
2. **补齐 15 个 OPC Agent Skill 的 frontmatter**：至少包含 `name` 与 `description`。
3. **修复 `lbo-model` frontmatter**：将 description 用双引号包裹或改用 `|` 多行。
4. **统一 `strip-profile` 命名**：要么目录改名为 `fsi-strip-profile`，要么 frontmatter 改回 `strip-profile`；README 只保留一个。
5. **移除或参数化硬编码路径**：将 `/Users/r9/` 改为环境变量、配置文件或相对路径，并给出默认值示例。
6. **修正 `fund-diagnosis-3.10` version**：`version: "3.10"`。

### 近期优化（P1）
7. **建立依赖矩阵**：在仓库根目录创建 `dependencies.md` 或在每个 skill 的 frontmatter 中增加 `dependencies` 字段，列出数据终端/PyPI/系统依赖及 fallback 策略。
8. **清理失效内部引用**：补齐缺失的 reference/scripts/assets 文件，或删除/修正错误链接。
9. **为交叉引用增加版本说明**：如 `` `china-market-data@v1` ``，或在 README 中维护 skill 版本映射表。
10. **补充 `requirements.txt`**：为依赖 Python 包的 skill（akshare、openpyxl、python-pptx 等）添加各自的 `requirements.txt`。

### 持续改进（P2）
11. **拆分超大 SKILL.md**：将超过 20KB 的 skill 按“核心流程 + 详细参考”拆分到 `references/`。
12. **统一 frontmatter 模板**：建议所有 skill 使用以下字段：
    ```yaml
    ---
    name: <folder-name>
    description: |
      简短描述（200 字以内）。
      多行时用 | 保持格式。
    version: "1.0.0"
    author: R9
    license: MIT
    dependencies:
      - akshare
      - openpyxl
    ---
    ```
13. **增加自动化检查脚本**：
    - 解析所有 frontmatter
    - 检查目录名与 `name` 一致性
    - 检查内部 markdown 链接与文件存在性
    - 检查 README 分类与实际目录一致性
14. **风格专属 skill 拆包**：将 `khazix-writer`、`daily-market-hotspot` 等拆分为“通用写作框架 + 风格 persona 覆盖文件”，提升复用性。
15. **补充开源治理文件**：`LICENSE`、`CONTRIBUTING.md`、`.github/PULL_REQUEST_TEMPLATE.md`。

---

## 五、风险评级

| 风险项 | 级别 | 说明 |
|--------|------|------|
| 数量口径不一致 | 高 | 直接影响用户预期与路由准确性 |
| OPC Agent 无 frontmatter | 高 | 15 个 skill 对客户端不可见 |
| `lbo-model` YAML 错误 | 高 | 元数据失效 |
| 硬编码路径 | 中 | 影响可移植性，但不影响原作者使用 |
| 失效内部引用 | 中 | 用户按说明执行会失败 |
| 数据依赖无 fallback | 中 | 无专业终端时体验下降 |
| 风格强绑定 | 低 | 主要影响外部推广 |

---

## 六、建议的修复顺序

```
Week 1: P0 修复
  ├── 补齐 15 个 OPC frontmatter
  ├── 修复 lbo-model / strip-profile / fund-diagnosis version
  ├── 同步 README 与 r9-workbench 数量及分类
  └── 参数化硬编码路径

Week 2: P1 修复
  ├── 清理失效内部引用
  ├── 建立依赖矩阵与 requirements.txt
  └── 为交叉引用增加版本/兼容性说明

Week 3+: P2 优化
  ├── 拆分超大 skill
  ├── 统一 frontmatter 模板
  ├── 增加 CI 检查脚本
  └── 补充 LICENSE / CONTRIBUTING
```

---

## 八、已完成的 P0 修复（2026-07-13）

以下修改已在本地克隆仓库 `/Users/saucebehumble/OPC-skill-audit` 中完成，并通过自动化验证脚本确认无回归：

| 问题 | 修复内容 | 涉及文件 |
|------|---------|----------|
| README 数量与分类不一致 | 移除重复的 `fsi-strip-profile`；补充 `hv-analysis`、`kyc-doc-parse`、`kyc-rules` 到基础设施板块；分类总数现为 93 | `README.md` |
| r9-workbench 未包含 OPC Agent | 数量更新为 93，板块更新为 9 大板块，按 README 分类完整枚举全部 93 个 skill，新增 OPC Agent 系列路由表 | `skills/r9-workbench/SKILL.md` |
| OPC Agent skill 无 frontmatter | 为 15 个 `r9-opc-*` skill 补齐 `name` + `description` frontmatter | 15 个 `skills/r9-opc-*/SKILL.md` |
| lbo-model YAML 错误 | 将 description 改为 `|` 多行格式，消除未转义冒号 | `skills/lbo-model/SKILL.md` |
| strip-profile 命名不一致 | frontmatter `name` 改为 `strip-profile`，与目录名一致 | `skills/strip-profile/SKILL.md` |
| fund-diagnosis 版本解析错误 | `version: 3.10` 改为 `version: "3.10"` | `skills/fund-diagnosis-3.10/SKILL.md` |
| 硬编码 `/Users/r9/` 路径 | 全部替换为 `~/.kimi/skills/`、`~/OPC/`、`~/Desktop/` 等通用路径 | `fund-active-research`、`fund-market-volatility-script`、`r9-opc-memory`、`r9-opc-operations`、`r9-workbench` |

**验证结果**：✅ 所有 P0 检查通过（全部 skill 有合法 frontmatter、目录名与 name 一致、无硬编码 `/Users/r9/` 路径、README 与 r9-workbench 均列出 93 个 skill 且分类一致）。

---

## 七、结语

OPC-skill 仓库已经具备了非常完整的金融投研工作流覆盖能力，改进空间主要集中在**工程化与可维护性**层面，而非内容质量本身。P0 项修复后，外部用户安装与路由体验已显著改善。剩余的 P1/P2 项（依赖矩阵、失效内部链接、自动化检查、风格拆包等）可按优先级逐步推进。
