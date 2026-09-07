---
name: fund-advisor-strategy
description: 基金投顾策略分析与组合管理工具。适用于资产配置方案制定、基金筛选评价、投资组合诊断、定投策略设计、组合再平衡等投顾场景。当用户需要制定投资策略、筛选基金产品、分析组合风险收益、或进行组合优化时触发此skill。
---

# 基金投顾策略

本skill提供基金投顾业务所需的核心策略工具和分析方法。

## 核心功能

1. **资产配置策略**：战略资产配置(SAA)和战术资产配置(TAA)方案
2. **基金筛选分析**：多维度基金评价与筛选
3. **投资组合诊断**：组合风险收益分析
4. **定投策略**：定投计划设计与优化
5. **组合再平衡**：再平衡触发机制与方案

## 快速使用

### 资产配置

根据客户风险等级制定配置方案：

```python
# 示例：保守型客户配置
allocation = {
    "货币基金": 30,
    "短债基金": 25,
    "中长债基金": 25,
    "混合基金": 15,
    "股票基金": 5
}
```

### 基金筛选

筛选标准参考：

| 指标 | 优秀标准 | 权重建议 |
|------|----------|----------|
| 年化收益率 | 同类前30% | 20% |
| 夏普比率 | >1.0 | 25% |
| 最大回撤 | 同类前30% | 25% |
| 基金经理年限 | >3年 | 15% |
| 管理规模 | 适中(10-100亿) | 15% |

### 组合诊断

诊断维度：
- 收益率分析（年化、累计、超额）
- 风险分析（波动率、最大回撤、VaR）
- 风险调整后收益（夏普比率、卡玛比率）
- 分散度分析（集中度、相关性）
- 风格分析（市值、价值/成长）

## 参考文档

- [投资策略方法](references/strategies.md)：资产配置模型和方法论
- [基金评价指标](references/metrics.md)：完整指标体系说明
- [Python分析工具](scripts/fund_analysis.py)：组合分析计算脚本
- [且慢API客户端](scripts/qieman_api.py)：且慢(盈米)基金数据API接入
- [且慢API接入指南](references/qieman_api_guide.md)：完整的API接入文档

## 且慢API接入

> **数据优先级**：本 skill 默认优先使用且慢(盈米) MCP 获取基金数据。当且慢接口不可用时，按「天天基金网 → AKShare 基金接口 → Wind/iFinD/Choice」顺序降级。

### 获取API权限

1. 访问 [盈米且慢开放平台](https://www.yingmi.cn) 申请开发者账号
2. 创建应用获取 `API_KEY` 和 `API_SECRET`
3. 配置环境变量或直接在代码中使用

### 快速开始（MCP 优先）

```python
from qieman_mcp_client import create_mcp_client
import os

# 从环境变量读取 API Key（推荐）
client = create_mcp_client(os.getenv('QIEMAN_MCP_API_KEY'))

if client.connect():
    # 获取基金信息
    info = client.get_fund_info('000001')
    
    # 获取基金净值
    nav = client.get_fund_nav('000001', limit=252)
    
    # 搜索基金
    funds = client.search_funds('沪深300', fund_type='index')
    
    # 分析组合
    analysis = client.analyze_portfolio([
        {"code": "000001", "weight": 0.3},
        {"code": "110020", "weight": 0.7}
    ])
```

### 环境变量配置

```bash
export QIEMAN_API_KEY="your_api_key"
export QIEMAN_API_SECRET="your_api_secret"
export QIEMAN_BASE_URL="https://api.qieman.com"  # 可选
```

### 与本地分析工具结合

```python
from qieman_api import create_client_from_env, batch_fetch_funds
from fund_analysis import portfolio_analysis

# 获取且慢数据
client = create_client_from_env()
fund_codes = ['000001', '110020', '260108']
fund_navs = batch_fetch_funds(client, fund_codes)

# 使用本地工具分析
weights = {'000001': 0.3, '110020': 0.4, '260108': 0.3}
result = portfolio_analysis(fund_navs, weights)
```

### 完整示例

参见 [且慢API集成示例](scripts/example_qieman_integration.py)，包含：
- 基础基金数据查询
- 组合分析与风险评估
- 策略推荐与定投计划
- 再平衡分析
- 市场数据获取

### MCP SSE接入 (推荐)

且慢提供MCP SSE (Server-Sent Events) 端点，支持实时双向通信：

**端点地址**: `https://stargate.yingmi.com/mcp/sse?apiKey=YOUR_API_KEY`

#### 方式1: 使用MCP客户端

```python
from qieman_mcp_client import create_mcp_client

# 创建并连接
client = create_mcp_client('your_api_key')
if client.connect():
    # 获取基金信息
    info = client.get_fund_info('000001')
    
    # 搜索基金
    funds = client.search_funds('沪深300', fund_type='index')
    
    # 分析组合
    result = client.analyze_portfolio([
        {"code": "000001", "weight": 0.3},
        {"code": "110020", "weight": 0.7}
    ])
```

#### 方式2: Kimi CLI MCP配置

在 `~/.kimi/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "qieman": {
      "command": "npx",
      "args": [
        "-y",
        "@yingmi/mcp-server",
        "--apiKey",
        "YOUR_API_KEY"
      ],
      "env": {
        "QIEMAN_API_KEY": "YOUR_API_KEY"
      }
    }
  }
}
```

或使用SSE直连模式：

```json
{
  "mcpServers": {
    "qieman": {
      "url": "https://stargate.yingmi.com/mcp/sse?apiKey=YOUR_API_KEY"
    }
  }
}
```

#### 方式3: 接入第三方MCP平台

- **阿里云百炼**: 在「工具管理」添加MCP服务，填入SSE端点
- **扣子空间**: 在「插件」中添加自定义MCP服务
- **火山引擎**: 在「大模型生态广场」搜索且慢MCP

### 可用MCP工具

连接成功后，可使用以下工具：

| 工具名 | 功能 | 示例 |
|-------|------|------|
| `get_fund_info` | 基金信息查询 | `{"code": "000001"}` |
| `get_fund_nav` | 净值数据获取 | `{"code": "000001", "limit": 252}` |
| `search_funds` | 基金搜索 | `{"keyword": "沪深300"}` |
| `analyze_portfolio` | 组合分析 | `{"holdings": [{"code": "", "weight": 0.3}]}` |
| `get_strategy_recommendation` | 策略推荐 | `{"risk_profile": "balanced", "amount": 100000}` |
| `get_investment_plan` | 定投计划 | `{"fund_codes": [], "amount": 2000}` |
| `get_market_overview` | 市场概览 | `{}` |
| `get_fund_performance` | 业绩指标 | `{"code": "000001", "period": "1y"}` |

## 工作流程

### 新客户方案

1. **需求分析** → 确定风险等级和投资目标
2. **资产配置** → 选择SAA模型确定各类资产比例
3. **基金筛选** → 在各类资产中筛选优质基金
4. **组合构建** → 形成初始投资组合
5. **风险评估** → 测算组合风险收益特征
6. **方案输出** → 生成投顾方案文档

### 存量组合诊断

1. **数据采集** → 获取持仓基金数据
2. **组合分析** → 使用分析脚本计算各项指标
3. **问题识别** → 找出风险点或优化空间
4. **调整建议** → 提出调仓方案

### 组合再平衡

1. **偏离度检测** → 对比当前配置与目标配置
2. **触发判断** → 阈值法/定期法/事件法
3. **再平衡方案** → 确定买卖计划
4. **执行建议** → 给出调仓时机和顺序建议