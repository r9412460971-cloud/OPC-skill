---
name: china-market-data
description: |
  中国市场统一数据接口层。为所有金融分析 skill 提供标准化的国内数据获取指南、术语对照和代码模板。
  
  当任何 skill 需要获取 A 股、港股、中概股数据时，优先引用此 skill 的数据接口规范。
  覆盖行情数据、财务报表、估值指标、宏观经济等全品类数据。
---

# 中国市场统一数据接口层 (China Market Data Layer)

## 概述

本 skill 为所有金融分析工具提供标准化的中国市场数据获取规范。所有涉及中国（A 股、港股、中概股）市场的 skill 在获取数据时，应遵循本层的接口优先级和代码模板。

## 数据接口优先级

### 通用优先级（默认）

#### P0 — 默认首选（零成本、免注册）

| 数据源 | 安装 | 覆盖 | 最佳场景 |
|--------|------|------|---------|
| **AKShare** | `pip install akshare` | A股/港股/美股/基金/期货/宏观 | 默认全能数据源 |
| **Baostock** | `pip install baostock` | A股历史数据 | 批量下载本地建仓 |

#### P1 — 补充增强（需注册 Token）

| 数据源 | 安装 | Token | 覆盖 | 最佳场景 |
|--------|------|-------|------|---------|
| **Tushare Pro** | `pip install tushare` | 注册免费获取 | A股/港股/美股/基金/宏观 | 结构化财务指标、高质量财报 |

#### P2 — 专业终端（需付费账号）

| 数据源 | 安装 | 费用 | 最佳场景 |
|--------|------|------|---------|
| **Wind (万得)** | 随终端安装 | ¥4-8万/年 | 机构级全品类数据 |
| **iFinD (同花顺)** | 随终端安装 | 有免费版 | 专业终端替代方案 |

#### P3 — 权威原始披露

| 数据源 | 访问方式 | 用途 |
|--------|---------|------|
| **巨潮资讯网 (cninfo)** | AKShare 封装 / WebAPI | 最权威的年报/季报/公告 |
| **交易所公告** | 上交所/深交所/北交所官网 | IPO、定增、重大事件 |

### 基金数据专用优先级

> **顶层规则**：所有涉及公募基金、投顾组合、基金经理的数据获取，按以下顺序优先尝试，前者失败或数据缺失时再降级到后者。

| 优先级 | 数据源 | 接入方式 | 稳定性 | 最佳场景 |
|--------|--------|---------|--------|---------|
| **P0** | **且慢(盈米) MCP** | `https://stargate.yingmi.com/mcp/sse?apiKey=...` | ⭐⭐⭐⭐ 稳定 | 基金信息、净值、持仓、组合分析、策略推荐、定投计划 |
| **P1** | **天天基金网** | `fundgz.1234567.com.cn`、`api.fund.eastmoney.com`、`fundf10.eastmoney.com` | ⭐⭐⭐ 一般 | 实时估值、历史净值、F10 概况、十大重仓、行业/资产配置 |
| **P2** | **AKShare 基金接口** | `ak.fund_*` 系列 | ⭐⭐⭐⭐ 稳定 | 基金列表、净值、持仓、行业配置、业绩排名、费率 |
| **P3** | **Wind / iFinD / Choice** | 终端 API | 需付费 | 机构级补全、全持仓、风格归因、独家指标 |

#### 基金数据获取流程

```
开始获取基金数据
    ↓
尝试 且慢 MCP（P0）
    ↓ 成功 → 使用且慢数据
    ↓ 失败/无权限
尝试 天天基金网（P1）
    ↓ 成功 → 使用天天基金数据
    ↓ 失败/被反爬
尝试 AKShare 基金接口（P2）
    ↓ 成功 → 使用 AKShare 数据
    ↓ 失败
使用 Wind / iFinD / Choice 终端（P3）或提示用户补充数据
```

#### 基金数据接口速查

```python
import akshare as ak

# 基金全市场列表
ak.fund_name_em()

# 开放式基金历史净值
ak.fund_open_fund_info_em(symbol="000001", indicator="单位净值走势")

# 基金业绩排名
ak.fund_em_performance_rank()

# 基金费率
ak.fund_em_fee()

# 季报重仓股
ak.fund_portfolio_hold_em(symbol="000001", date="2024")

# 行业配置
ak.fund_portfolio_industry_allocation_em(symbol="000001", date="2024")

# 资产配置
ak.fund_portfolio_asset_allocation_em(symbol="000001", date="2024")
```

## 术语对照表

### 报表与披露

| 海外术语 | 国内对应 | 说明 |
|----------|---------|------|
| 10-K | 年度报告 / 年报 | 上市公司年度财务报告 |
| 10-Q | 季度报告 / 季报 | 上市公司季度财务报告 |
| 8-K | 临时公告 / 重大事项公告 | 突发披露 |
| SEC EDGAR | 巨潮资讯网 / cninfo | 中国证监会指定信息披露平台 |
| SEC Filing | 交易所公告 / 监管披露 | 沪深北交易所披露 |
| S-1 / IPO Filing | 招股说明书 | IPO 申报稿/注册稿 |
| Proxy Statement | 股东大会决议公告 | 投票相关 |
| Earnings Release | 业绩快报 / 业绩预告 | 季度/年度业绩披露 |
| Earnings Call | 业绩说明会 / 投资者交流会 | 公司管理层与投资者沟通 |

### 财务指标

| 海外术语 | 国内对应 | 备注 |
|----------|---------|------|
| Revenue | 营业收入 / 营业总收入 | |
| Gross Profit | 毛利润 / 营业毛利 | |
| Gross Margin | 毛利率 | 通用 |
| EBITDA | 息税折旧摊销前利润 | 通用 |
| EBIT / Operating Income | 营业利润 / 息税前利润 | 注意：国内营业利润 ≠ EBIT（含财务费用） |
| Net Income | 净利润 / 归母净利润 | 国内常用"归母净利润" |
| EPS | 每股收益 / EPS | 通用 |
| Diluted EPS | 稀释每股收益 | |
| Free Cash Flow (FCF) | 自由现金流 | 通用 |
| CapEx | 资本开支 / 购建固定资产支出 | |
| D&A | 折旧与摊销 | 通用 |
| NWC / Working Capital | 营运资金 / 营运资本 | |
| Total Debt | 有息负债 / 总负债 | 注意区分 |
| Net Debt | 净负债 = 有息负债 - 货币资金 | |
| Book Value | 账面价值 / 净资产 | |
| Retained Earnings | 未分配利润 | |
| Shareholders' Equity | 股东权益 / 所有者权益 | |

### 估值指标

| 海外术语 | 国内对应 | 备注 |
|----------|---------|------|
| Market Cap | 市值 / 总市值 | 通用 |
| Enterprise Value (EV) | 企业价值 | 通用 |
| P/E Ratio | 市盈率 / P/E | 通用 |
| P/B Ratio | 市净率 / P/B | 通用 |
| EV/EBITDA | 企业价值倍数 | 通用 |
| EV/Revenue | 市销率（企业版） | |
| PEG Ratio | PEG 比率 | 通用 |
| Dividend Yield | 股息率 | 通用 |
| Beta | Beta 系数 / 贝塔 | 通用 |
| WACC | 加权平均资本成本 | 通用 |
| Cost of Equity | 股权成本 | 通用 |
| Terminal Value | 终值 | 通用 |
| Implied Price | 隐含股价 / 目标价 | |
| Price Target | 目标价 | 国内券商常用 |
| Consensus Estimates | 一致预期 / 盈利预测 | Wind/同花顺/东方财富 |
| LTM / TTM | 最近 12 个月 / 滚动 12 月 | 通用 |
| FY2024E | 2024 财年预测 | 国内常用"2024E" |

### 市场与交易

| 海外术语 | 国内对应 | 备注 |
|----------|---------|------|
| Ticker / Symbol | 股票代码 | 如：600519.SH, 00700.HK |
| Share Price | 股价 / 收盘价 | |
| Shares Outstanding | 总股本 / 流通股数 | 注意区分总股本和流通股本 |
| Float | 流通股本 / 自由流通股本 | |
| ADR | 不适用 / 中概股 | 部分港股通标的 |
| Volume | 成交量 / 成交额 | |
| 52-Week High/Low | 52 周最高/最低 | 或 250 日最高/最低 |
| VIX | 不适用 | 国内无直接对应波动率指数 |
| S&P 500 | 沪深 300 / 中证 500 / 上证指数 | 根据分析场景选择对标指数 |
| Nasdaq | 创业板指 / 科创 50 | 成长股对标 |
| Russell 2000 | 中证 1000 | 小盘股对标 |
| Treasury Yield | 国债收益率 | 中国 10 年期国债收益率 |
| Fed Funds Rate | LPR / MLF / 政策利率 | 贷款市场报价利率 |

### 行业与研究

| 海外术语 | 国内对应 | 备注 |
|----------|---------|------|
| Sell-Side Research | 卖方研究 / 券商研报 | |
| Buy-Side Research | 买方研究 / 投研 | |
| Initiating Coverage | 首次覆盖报告 | 国内券商常用 |
| Earnings Note | 业绩点评 / 季报点评 | |
| Sector Report | 行业深度报告 | |
| Company Note | 公司点评 / 个股点评 | |
| Morning Note | 晨会纪要 / 早盘点评 | |
| Investment Thesis | 投资逻辑 / 核心观点 | |
| Catalyst | 催化剂 / 事件驱动 | |
| Moat / Competitive Advantage | 护城河 / 竞争优势 | |
| TAM / SAM / SOM | 市场空间 / 可触达市场 | |
| Guidance | 业绩指引 / 管理层预期 | |
| Beat / Miss | 超预期 / 低于预期 | |
| YoY / QoQ | 同比 / 环比 | 通用 |

## 标准化 Python 数据获取模板

### 模板 1：获取股票基本信息

```python
import akshare as ak

# A 股基本信息
stock_info = ak.stock_individual_info_em(symbol="600519")
# 返回：股票代码、股票简称、总市值、流通市值、总股本、流通股本等

# 港股基本信息
stock_info_hk = ak.stock_hk_ggt_components_em()  # 港股通成分
# 或
stock_hk = ak.stock_hk_hist(symbol="00700", period="daily", start_date="20240101", end_date="20251231")
```

### 模板 2：获取历史行情数据

```python
import akshare as ak

# A 股历史日线（前复权）
df = ak.stock_zh_a_hist(symbol="600519", period="daily", start_date="20200101", end_date="20251231", adjust="qfq")
# 列：日期、开盘、收盘、最高、最低、成交量、成交额、振幅、涨跌幅、涨跌额、换手率

# 港股历史日线
df_hk = ak.stock_hk_hist(symbol="00700", period="daily", start_date="20200101", end_date="20251231")

# 美股中概历史日线
df_us = ak.stock_us_hist(symbol="105.BABA", period="daily", start_date="20200101", end_date="20251231")
```

### 模板 3：获取财务报表（三张表）

```python
import akshare as ak

# 利润表
income = ak.stock_yjbb_em(date="20241231")  # 年度
# 或按股票代码
income_single = ak.stock_financial_report_sina(stock="600519", symbol="利润表")

# 资产负债表
balance = ak.stock_financial_report_sina(stock="600519", symbol="资产负债表")

# 现金流量表
cashflow = ak.stock_financial_report_sina(stock="600519", symbol="现金流量表")

# 主要财务指标（已计算好比率）
indicators = ak.stock_yjbb_em(date="20241231")
# 包含：营收、净利润、毛利率、净利率、ROE 等
```

### 模板 4：使用 Tushare Pro（需 Token）

```python
import tushare as ts

# 设置 Token（注册后获取）
ts.set_token('your_token_here')
pro = ts.pro_api()

# 日线行情
df = pro.daily(ts_code='600519.SH', start_date='20200101', end_date='20251231')

# 利润表
income = pro.income(ts_code='600519.SH', start_date='20200101', end_date='20251231')

# 资产负债表
balance = pro.balancesheet(ts_code='600519.SH', start_date='20200101', end_date='20251231')

# 现金流量表
cashflow = pro.cashflow(ts_code='600519.SH', start_date='20200101', end_date='20251231')

# 财务指标（已计算）
indicators = pro.fina_indicator(ts_code='600519.SH')
# 包含：ROE、毛利率、净利率、资产负债率、营收增长率等

# 每日指标（估值指标）
daily_basic = pro.daily_basic(ts_code='600519.SH')
# 包含：PE、PB、PS、总股本、流通股本、总市值等
```

### 模板 5：获取实时行情与估值

```python
import akshare as ak

# A 股实时行情（全部）
df_realtime = ak.stock_zh_a_spot_em()
# 筛选特定股票
stock_realtime = df_realtime[df_realtime['代码'] == '600519']

# 获取含估值数据的实时行情
# PE、PB、总市值、流通市值等
```

### 模板 6：批量获取多只股票数据

```python
import akshare as ak
import pandas as pd

# 获取全部 A 股列表
stock_list = ak.stock_zh_a_spot_em()

# 获取特定板块成分股
# 沪深 300
hs300 = ak.index_stock_cons_weight_csindex(symbol="000300")

# 中证 500
zz500 = ak.index_stock_cons_weight_csindex(symbol="000905")

# 行业板块
industry_stocks = ak.stock_board_industry_name_em()
```

### 模板 7：获取宏观与市场数据

```python
import akshare as ak

# 中国 10 年期国债收益率
bond_yield = ak.bond_china_yield(start_date="20200101", end_date="20251231")

# LPR 利率
lpr = ak.macro_china_lpr()

# 上证指数历史
sh_index = ak.index_zh_a_hist(symbol="000001", period="daily")

# 沪深 300 历史
hs300 = ak.index_zh_a_hist(symbol="000300", period="daily")
```

### 模板 8：获取公告与原始披露

```python
import akshare as ak

# 巨潮资讯网公告查询
announcements = ak.stock_zh_a_disclosure_report_cninfo(
    stock="600519",
    category="年度报告",  # 或 "季度报告", "临时公告"
    start_date="20240101",
    end_date="20251231"
)

# 获取最新公告
latest = ak.stock_notice_report(
    symbol="600519",
    date="2025"
)
```

## 数据质量与验证规范

### 时间口径一致性
- 所有分析必须统一时间口径（全部使用年度、全部使用 LTM、或全部使用同一季度）
- A 股年报披露截止日：次年 4 月 30 日
- A 股季报披露截止日：季度结束后 1 个月内

### 币种统一
- A 股分析：统一使用人民币（元/亿元）
- 港股分析：可使用港币或折算人民币（需标注汇率和日期）
- 跨市场对比：需统一币种并标注汇率

### 会计准则说明
- A 股：中国企业会计准则（CAS）
- 港股：IFRS / HKFRS
- 中概股：US GAAP（注意与中国准则的差异）

### 常见差异点
| 项目 | CAS | US GAAP | 说明 |
|------|-----|---------|------|
| 营业利润 | 含财务费用 | Operating Income（不含利息） | 国内营业利润 ≠ EBIT |
| 研发费用 | 可资本化条件严格 | 更灵活 | 注意软件/药企差异 |
| 资产减值 | 不可转回（长期） | 部分可转回 | 商誉、固定资产 |
| 政府补助 | 与收益相关/与资产相关 | 多种分类 | 注意非经常性损益 |

## 数据获取最佳实践

1. **优先 AKShare**：零门槛、覆盖广，作为默认数据源
2. **Tushare 补充**：需要高质量结构化财务指标时启用
3. **本地缓存**：用 Baostock 一次性下载全市场历史数据，避免重复调用
4. **交叉验证**：关键数据（如净利润、市值）至少用 2 个来源验证
5. **标注来源**：每个硬编码数据必须标注来源（系统、日期、URL）
6. **异常处理**：AKShare 偶有不稳定，捕获异常并提示用户换用 Tushare

## 环境依赖

```bash
pip install akshare tushare baostock pandas numpy openpyxl
```

```python
# 推荐导入顺序
import akshare as ak      # 默认数据源
import tushare as ts      # 补充数据源（需 Token）
import baostock as bs     # 批量历史数据
import pandas as pd
import numpy as np
```
