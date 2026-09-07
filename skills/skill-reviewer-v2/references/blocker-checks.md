# 阻断检查详细定义（B01-B21）

**任何 B 类问题未解决前，skill 不允许上架。**

---

## Unified Handling Policy

Entries in this file may mention auto-fixability. AI should resolve pass/warning/blocker decisions from package evidence whenever possible and write the result to handling records. High-confidence tiny mechanical fixes may run by default, including false-positive classification and metadata/format repairs. Version bumping is excluded from reviewer fixes and must be handled by skill-fetcher-v2 before pending-review. Semantic content, external links, dependency behavior, security-sensitive instructions, and business/legal positioning are handled through verdicts and findings, not silent edits. Escalate to the user only when AI lacks required external information, required configuration is missing, or AI has confirmed a real issue that needs an owner decision.

## B01：SKILL.md 存在且非空

- `skills/<name>/SKILL.md` 文件必须存在
- 文件内容不为空（去除空白后 >10 字符）
- 自动修复：不可（缺失 SKILL.md 需人工创建）

## B02：YAML frontmatter 格式有效

- 以 `---` 开头和结尾，中间为有效 YAML
- **使用标准 YAML 解析器**（`yaml.safe_load`）解析，支持多行值（`>-`/`|`）、引号转义、嵌套对象
- 解析失败时降级到逐行 key:value parser 并记录 warning
- 经过 R00 前置规范化后，此项的误报率大幅降低
- 自动修复：不可（降级 parser 仅用于兼容，不视为修复）

## B03：`description` 字段存在

- 必须存在，50-200 字符
- 给 AI 看的详细描述，包含触发场景、CLI 工具名、使用条件
- 自动修复：不可（核心字段，需人工撰写）

## B04：`description_zh` 字段存在

- 必须存在，中文，25-35 字
- 给人看的简短描述，核心功能优先
- **候选生成**：从 `description` AI 翻译生成；作为 uploader Listing Profile 候选，不在 reviewer 阶段停下确认

## B05：`description_en` 字段存在

- 必须存在，英文，60-80 字符
- 给人看的简短描述
- **自动补全**：从 `description` 截取精简

## B06：`name` 字段与目录名一致

- `name` 字段值必须等于 `skills/` 下的目录名
- 品牌产品可用中文展示名（如"滴滴打车"），但 `source` 必须是目录名
- **自动修复**：设为目录名

## B07：已删除（平台模式不适用）

- v2 不再依赖 marketplace.json / registry source 字段
- 不执行该检查，不作为 blocker

## B08：frontmatter 字段顺序正确

- 顺序：`name` → `description` → `description_zh` → `description_en` → `version` → `homepage` → `allowed-tools` → `metadata`
- **自动修复**：重排字段顺序

## B09：`version` 格式合法

- 仅允许纯数字 semver：`1.0.0`、`2.3.1`、`10.0.0`
- 禁止：`1.0.0-alpha`、`2.0.0-beta.1`、`1.0.0+build.123`
- **自动修复**：清理非数字后缀（如 `1.0.0-beta` → `1.0.0`）
- 无来源时不写 version（禁止凭空捏造）

## B10：Markdown body 非空且有实质内容

- frontmatter `---` 之后的内容必须有实质（>50 字符的非空白文本）
- 应包含标题结构和使用说明

## B11：已删除（平台模式不适用）

- icon 通过 Operation Platform API 上传，不再要求包内 icon 文件名匹配 source
- 不执行该检查，不作为 blocker

## B12：`version` 只升不降

- 新版本号必须大于 Operation Platform 已发布版本
- 通过 Platform API 查询同名 published skill，不再读取 skill-registry.csv
- 当版本号 ≤ 已发布版本时，判定为阻断；版本递增应回到 skill-fetcher-v2 阶段处理，不生成 ai_action，不在 review 阶段改包

## B13：三个 description 字段一致性

- v2 仅检查 SKILL.md frontmatter 内部的 `description`、`description_zh`、`description_en` 是否齐全
- 不再对比 marketplace.json
- 缺失时给出 warning / ai_action，不直接阻断

## B14：`allowed-tools` 中列出的工具在文档中有说明

- 列出的每个工具（Read/Write/Bash 等）在 SKILL.md body 中应有使用说明

## B15：references/ 和 scripts/ 文件引用无断链

- SKILL.md 中引用的 `references/*.md` 文件必须存在
- SKILL.md 中引用的 `scripts/*.py`、`scripts/*.sh` 等脚本文件必须存在（v3.6.0+）
- 支持多种引用格式：纯路径（`scripts/xxx.py`）、反引号包裹（`` `scripts/xxx` ``）、Markdown 链接（`[文字](scripts/xxx.py)`）
- 路径大小写必须完全匹配

## B16：无孤儿 reference 文件（警告级别）

- `references/` 目录中的文件应在 SKILL.md 中被引用
- VCS 占位文件（`.gitkeep`、`.gitignore`、`.keep`）自动跳过，不参与检查
- 孤儿文件**仅警告不阻断**（保证源文件完整性优先），通过 `ai_action` 提醒 LLM 审查
- LLM 收到提醒后逐个判断：是否需要添加引用 / 是否为无用文件 / 是否为脚本依赖

## B17：首次上架来源元数据完整性

- 仅 `workflow` / 上架审查路径执行；`review-only` 纯审查路径跳过，不作为 blocker 或 warning
- 新上架 skill 必须有明确的数据渠道：`source_type` 或 `data_channel`，取值为 `clawhub` / `skillhub` / `git`
- 同时必须提供以下来源标识至少一个：
  - `clawhub_slug`
  - `skillhub_slug`
  - `git_url`
- reviewer 从 `pending-review.json`、`_fetch-meta.json` 或 SKILL.md frontmatter 中读取这些字段
- 对新上架包：缺少数据渠道或三选一来源标识 → **BLOCKER**
- 对版本更新包：缺失时降级为 warning，建议补齐以便追溯
- 自动修复：不可。必须由 fetcher / 人工补齐来源后重新 review

## B18：ClawHub 包体已清洗

- 无 `.clawhub/` 目录
- 无 `clawhub.json`、`_meta.json`、`_skillhub_meta.json`
- metadata 块中无 `openclaw` 键（应为 `clawdbot`）
- 无 Unicode Cf 控制字符
- **自动修复**：执行清洗

---

## B19：安全性与通用性检查

### 检查范围

扫描 skill 目录中所有文本文件（`.md`、`.py`、`.js`、`.ts`、`.json`、`.yaml`、`.yml`、`.sh`、`.html`、`.css`、`.txt`、`.toml`、`.cfg`、`.ini`）。

### 阻断项

#### 1. 硬编码内网域名

**检查规则**：匹配 URL 或 Git 地址中包含以下内网根域名的引用：
- `*.woa.com`（腾讯内网）
- `*.oa.com`（腾讯 OA）
- `*.woa.net`
- `*.oa.tencent.com`

**排除条件**（不报告）：
- 在 Markdown 标题行（`# ...`）中
- 在 Markdown 引用块（`> ...`）或表格行（`| ...`）中
- 包含明显占位符（`<token>`、`<your_`、`${...}`）的行

**判定**：若发现内网域名且行内无公网降级说明 → **BLOCKER**

**修复建议**：将内网域名替换为公网可访问的等价资源，或提供降级逻辑。仅限内网的 skill 不予上架。

#### 2. 凭据硬编码

**检查规则**：匹配以下模式中赋值的实际值（非占位符）：
- `password/passwd/pwd = "..."`（≥6字符值）
- `secret/secret_key = "..."`（≥6字符值）
- `api_key/apikey/api-key = "..."`（≥10字符值）
- `PRIVATE-TOKEN: <actual_value>`（≥10字符值）

**排除条件**：值以 `<`、`{`、`$`、`xxx`、`placeholder`、`your_`、`example`、`changeme` 开头的占位符。

**判定**：若发现实际凭据值 → **BLOCKER**

### 警告项（不阻断）

#### 3. 仅内网软件源

**检查规则**：匹配以下内部 npm/pip 等软件源：
- `npm.woa.com`、`mirrors.woa.com`、`mirrors.tencent.com/npm`、`pypi.woa.com`

**判定**：→ **WARNING**，建议提供公网替代安装命令

#### 4. 开发者个人路径泄露

**检查规则**：匹配以下个人目录路径模式：
- `/Users/<username>/`（macOS）、`/home/<username>/`（Linux）、`C:\Users\<username>\`（Windows）

**排除条件**：通用系统路径（`/Users/shared/`、`/Users/Public/`、`C:\Users\Public\`、`C:\Users\Default\`）

**判定**：→ **WARNING** + `ai_action` type="verify"

**修复建议**：替换为相对路径或通用占位符（如 `<user_home>/`）

#### 5. 其他平台路径残留

**检查规则**：匹配非当前平台的 IDE 路径：`.cursor/`、`.vscode/`、`.windsurf/`、`.copilot/`、`.cline/`

**注意**：`.workbuddy/` 路径**不报告**

**判定**：→ **WARNING** + `ai_action` type="review"

#### 6. CDN @latest 无版本锁定

**检查规则**：匹配 CDN 引用中使用 `@latest` 的模式

**判定**：→ **WARNING** + `ai_action` type="review"，建议锁定具体版本号

### 背景

当前 CodeBuddy 不区分司内与司外环境，所有上架技能对全体用户可见，必须保证公网可用性。此检查由 `review.py` 中的 `check_b19()` 函数自动执行。

---

### High-risk capability combination gate

B19 also scans for combinations that are unsafe even when each capability might
look explainable in isolation. The following families are recalled with
file/line evidence: code obfuscation or packing, LLM traffic proxying or
interception, conversation/prompt capture, device fingerprinting or keychain
access, self-modifying or forced rollback behavior, autonomous purchase/payment,
and external telemetry/reporting.

The check becomes a blocker when these signals combine in ways that commonly
hide malicious behavior:

- multiple obfuscated files plus sensitive capability signals;
- obfuscation plus four or more sensitive capability families;
- LLM API proxy/interception plus conversation capture or external reporting;
- obfuscated self-modifying behavior;
- autonomous purchase/payment plus network proxying or external reporting.

Semantic review must reconcile these B19 details explicitly. A model verdict may
confirm a false positive only with line-specific evidence or unobfuscated source;
otherwise the package remains blocked.

## B20：安装引导 + 环境配置引导完整性检查

由 `deterministic_checks.py` 中的 `check_b20()` 执行信号召回，最终由 LLM 在 Stage 02 语义审查中裁决。

### 检查逻辑

**环境配置引导（第一部分）—— LLM 语义裁决**

1. **信号召回**：扫描 frontmatter `compatibility` 字段和 SKILL.md body，用关键词模式召回外部服务依赖信号（MCP/API Key/Token/OAuth/凭证/授权/密钥 等）
2. **LLM 裁决**：命中信号后，由 LLM 基于语义理解判断 SKILL.md 是否包含充分的【环境配置引导】内容：
   - 用户如何获取凭证（注册账号、申请 API Key 等）
   - 如何在运行环境中启用服务（设置环境变量、调用绑定脚本等）
   - 如何验证配置是否生效
3. **重要**：配置引导可能写在任意章节中（如「用户认证机制」「注册流程」「绑定流程」「快速开始」等），**不要求**独立 `## 环境配置` 命名章节。只看内容是否充分覆盖，不按标题名称机械匹配。

**安装引导（第二部分）—— 确定性检查**

1. **提取依赖列表**：`metadata.clawdbot.requires.bins` → 必须有安装命令；body 中提到的外部 CLI；body 中提到的 API Key/Token/Secret/环境变量
2. **对比安装引导**：每个 CLI 依赖是否有安装命令？每个 API Key 是否有获取和设置说明？是否有验证命令？
3. **输出判定**：完全缺失 → BLOCKER；部分缺失 → WARNING；完整 → PASS

### 依赖类型要求

| 依赖类型 | 必须包含 | 示例 |
|----------|---------|------|
| CLI 工具 | 安装命令（brew/npm/pip/apt 等） | `brew install weather` |
| API Key | 变量名 + 获取方式 + 设置方式 | `export OPENAI_API_KEY=xxx` |
| 系统依赖 | 版本要求 + 验证命令 | `node --version` (>= 18.0) |

### LLM 裁决标准（环境配置引导）

| 判定 | 条件 |
|------|------|
| pass | 凭证获取 + 启用方式 + 验证方式均有覆盖（可在任意章节中） |
| warning | 部分覆盖（如只提了获取方式未提启用方式） |
| blocker | 完全缺少配置引导，仅有 compatibility 声明 |

### 跳过条件

- 纯 AI prompt 型（无 `metadata.clawdbot.requires`，body 中无外部工具引用）
- `allowed-tools` 仅含 `Read,Write`（无 Bash 执行能力）
- 结构检查阶段未召回外部服务依赖信号

### 自动修复

安装段落引用文件缺失：WARNING（不阻断）。环境配置引导缺失：由 LLM 在语义审查中裁决，脚本不自动修复。

---

## B21：包体大小检查

遍历 skill 目录下所有文件（排除 `_fetch-meta.json`），累加文件大小。

| 阈值 | 处理 | 说明 |
|------|------|------|
| ≤ 100 KB | ✅ 通过 | 正常范围 |
| 100 KB ~ 300 KB | ⚠ 警告 | 建议精简 |
| > 300 KB | ❌ 阻断 | 必须缩减包体后才能上架 |

**缩减建议**：大型参考文档移至远端；拆分过长 references；删除非必要文件；压缩冗余注释和空行。

**检查报告输出**：列出占用 >20KB 的大文件 Top 5。

## B21-ext：嵌套 skill 检测

检查 skill 目录子目录中是否存在 `SKILL.md` 文件（通常意味着误打包）。

| 发现 | 处理 |
|------|------|
| 无嵌套 | ✅ 通过 |
| 有嵌套 | ⚠ 警告 + `ai_action` type="review" |

---

## B22：营销导流 / 外跳引导检测

由 `review.py` 中的 `check_b22()` 做**确定性召回**（warning 级，永不直接阻断），命中信号交 LLM 在深度评审后基于 `b22_context.flagged_lines` 做语义裁决。这与平台治理白皮书「禁止引导外跳、禁止营销导流（区分功能跳转与导流）」口径对齐。

### 检查范围

扫描 skill 目录文本文件（`.md`、`.txt`、`.py`、`.js`、`.ts`、`.json`、`.yaml`、`.yml`），逐行匹配；跳过空行、引用块（`> `）与 HTML 注释行。

### 召回信号

**1. 营销导流信号**（高可疑，通常与 skill 功能无关）

- 关注公众号 / 官方账号、扫码关注 / 加群 / 进群
- 加私人微信 / VX / QQ群 / 企业微信、私信私聊客服或作者
- 点赞 / 转发 / 三连 / 求好评 / 给好评 / 一键三连
- 领红包 / 福利 / 优惠券、限时优惠 / 折扣、充值
- 开通会员 / VIP / 付费解锁 / 赞赏 / 打赏

**2. 外跳引导信号**（需 LLM 判断是否为功能性跳转）

- 下载并安装 App / 客户端 / 手机端 / 小程序
- 前往 / 打开 / 跳转 应用商店 / 应用市场 / App Store / Google Play / 小程序
- 扫码下载 / 安装 / 体验、长按识别二维码

### LLM 裁决边界（关键）

脚本只负责召回，**最终判定由 LLM 完成**，区分两类：

| 类型 | 判定 | 示例 |
|------|------|------|
| 营销导流 / 非功能性外跳 | ❌ **升级为 BLOCKER**，删除导流内容后重新 review | 引导关注公众号、加私人微信、求好评充值、引导跳出 WorkBuddy 去 App/官网/小程序完成本可在对话内完成的操作 |
| 功能性必要跳转 | ✅ 标记 false_positive 放行 | 获取 API Key 必须访问官方控制台、下载运行所需依赖 CLI、查看官方 API 文档 |

判定核心：**该跳转是否为完成 skill 功能所必需**。必需 → 放行；纯为引流 / 推广 / 把用户带离平台 → 阻断。

### 输出

- 命中时：`warning=True` + `ai_action`（field=`B22_drainage_review`, priority=`required`），`context.flagged_lines` 携带文件、行号、原文。
- LLM 逐行给出 `false_positive` / `blocker` 判定及理由；任一行被判 blocker 则整体阻断上架。
- 自动修复：不可。导流内容须人工或 LLM 在确认后删除。

### 背景

WorkBuddy 平台治理要求所有上架 skill 不得借 skill 内容做营销导流，也不得在非必要场景引导用户跳出平台。此前该红线只在 fetcher normalize 阶段清理 SKILL.md 开头的社媒信息，缺乏上架准入校验，B22 补齐这一空档。
