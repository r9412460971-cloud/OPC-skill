# R9 投研工作台 · Skill 分享仓库

> 本仓库收录了 R9（资产配置研习社）投研工作台的 Skill 集合，覆盖基金投研、权益研究、财务建模、投资银行、私募股权、财富管理、基金运营、内容创作 8 大板块。

## 目录结构

```
r9-skills-share/
├── README.md          # 本文件
├── .gitignore         # Git 忽略规则
└── skills/            # 全部 Skill 目录
    ├── r9-workbench/
    ├── china-market-data/
    ├── dcf-model/
    ├── hv-analysis/
    └── ...
```

每个 Skill 都是一个独立目录，目录内必须包含 `SKILL.md` 作为入口文件。

## 包含的 Skill

本仓库共包含 **93 个 Skill**，按板块分类如下：

### 1. 基金投研
- bond-plus-fund-evaluation
- bond-plus-tracker
- cmb-fyf-companion-service
- community-voc-analysis
- fund-active-research
- fund-advisor-strategy
- fund-diagnosis-3.10
- fund-manager-deep-research
- fund-market-volatility-script
- fund-phone-sales
- fund-portfolio-rebalancing-launch
- fund-r9alpha-evaluation
- fund-sales-rookie
- optical-module-tracker
- post-investment-companion
- r9-fund-deep-research

### 2. 权益研究
- catalyst-calendar
- earnings-analysis
- earnings-preview
- idea-generation
- initiating-coverage
- model-update
- morning-note
- sector-overview
- thesis-tracker

### 3. 财务建模
- 3-statement-model
- comps-analysis
- dcf-model
- lbo-model

### 4. 投资银行
- buyer-list
- cim-builder
- datapack-builder
- deal-tracker
- deck-refresh
- fsi-strip-profile
- ib-check-deck
- merger-model
- pitch-deck
- process-letter
- strip-profile
- teaser

### 5. 私募股权
- ai-readiness
- dd-checklist
- dd-meeting-prep
- deal-screening
- deal-sourcing
- ic-memo
- portfolio-monitoring
- returns-analysis
- unit-economics
- value-creation-plan

### 6. 财富管理
- client-report
- client-review
- financial-plan
- investment-proposal
- portfolio-rebalance
- tax-loss-harvesting

### 7. 基金运营
- accrual-schedule
- break-trace
- gl-recon
- nav-tieout
- roll-forward
- variance-commentary

### 8. 基础设施 / 内容创作
- audit-xls
- china-market-data
- clean-data-xls
- competitive-analysis
- daily-market-hotspot
- khazix-writer
- ppt-template-creator
- pptx-author
- r9-opc-memory
- r9-workbench
- skill-creator
- static-page-builder
- weibo-finance-daily
- xlsx-author

### 9. OPC 投顾公司 Agent 系列
- r9-opc-ceo
- r9-opc-compliance
- r9-opc-operations
- r9-opc-research
- r9-opc-research-asset
- r9-opc-research-fund
- r9-opc-research-macro
- r9-opc-research-portfolio
- r9-opc-research-sector
- r9-opc-advisory
- r9-opc-advisory-content
- r9-opc-advisory-delivery
- r9-opc-advisory-strategy
- r9-opc-advisory-success

## 安装方式

### 方案 A：手动复制（最简单）

```bash
# 1. 克隆仓库
git clone https://github.com/your-github-username/r9-skills.git

# 2. 进入仓库目录
cd r9-skills

# 3. 复制所有 skill 到 Kimi 的 skill 目录
cp -R skills/* ~/.kimi/skills/

# 4. 验证安装
ls ~/.kimi/skills/ | wc -l
```

### 方案 B：使用安装脚本

仓库根目录提供 `install.sh`：

```bash
git clone https://github.com/your-github-username/r9-skills.git
cd r9-skills
./install.sh
```

> 安装脚本会自动将 `skills/` 下的所有目录复制到 `~/.kimi/skills/`。

## 使用方式

安装完成后，打开 Kimi Code CLI 或任何支持 Kimi Skill 的客户端，直接描述你的投研需求即可。例如：

- "研究一下贵州茅台" → 自动调用 `initiating-coverage`
- "给宁德时代做 DCF" → 自动调用 `dcf-model`
- "评价这只基金" → 自动调用 `fund-r9alpha-evaluation`
- "客户回撤了怎么安抚" → 自动调用 `fund-market-volatility-script`

## 分享给他人

1. 将本仓库推送到你的 GitHub 账号
2. 把仓库地址分享给朋友
3. 对方执行上面的安装命令即可

## 贡献与更新

- 新增 Skill：在 `skills/` 下创建新的目录，并放入 `SKILL.md`
- 修改 Skill：直接编辑对应目录下的 `SKILL.md`
- 建议不要上传敏感信息（Token、密码、私钥等）

## 注意事项

- 部分 Skill 依赖 Python 包（如 `akshare`、`tushare`、`openpyxl` 等），请根据 `SKILL.md` 中的说明自行安装
- 部分 Skill 依赖 Wind、iFinD 等专业终端账号，没有账号时可能无法获取全部数据
- 所有 Skill 仅供学习和研究使用，不构成投资建议

---

*本仓库基于 R9 投研工作台整理，更新日期：2026-06-21*
