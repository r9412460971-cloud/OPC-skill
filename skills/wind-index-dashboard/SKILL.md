---
name: wind-index-dashboard
description: 用 Wind 数据构建并部署"静态金融数据看板"的完整流水线。当用户需要"做一个指数监控网页/Dashboard"、"用 Wind 数据做个市场全景看板"、"做一个每日自动更新的指数仪表盘"、"把行业指数/基金组合做成可交互网页"、"部署金融看板到 Cloudflare Pages"、"做组合回测可视化网页"、"风险回报散点图"时触发。覆盖：Python 数据管道（Wind MCP CLI）→ data.json → 单文件交互网页（走势图/弹窗深度视图/卡通形象/组合回测/散点图）→ Cloudflare Pages 部署 → 每日刷新。不使用场景：需要后端/数据库的实时系统、纯写报告不做网页。
---

# Wind 指数看板构建器

把一组指数（或基金/股票）做成一个可交互的静态看板网页：每日从 Wind 拉数生成 `data.json`，单文件 `index.html` 渲染，`wrangler pages deploy` 上线。成品参照 `/Users/r9/day-xiaodeng-dashboard/`（登指数 Dashboard）。

## 架构

```
指数清单（Excel/配置）
   → scripts/build_data.py（Wind MCP CLI 拉数 + 缓存 + 重试）
   → data.json（行情、K线、重仓、估值、series 序列）
   → index.html（Tailwind CDN + 原生 JS + 手绘 SVG，无构建）
   → Cloudflare Pages（wrangler pages deploy）
```

## 工作流程

### 1. 数据管道（scripts/build_data.py）

模板在 `scripts/build_data.py`，复制到项目目录后改三处：`MODULES`（模块名→Excel/清单→tag→颜色）、指数清单读取方式、`OUT_FILE`。

核心约定：

- **Wind 调用**：`cd ~/.claude/skills/wind-mcp-skill && node scripts/cli.mjs call <server> <tool> '<json>'`，常用 `index_data get_index_price_indicators`（行情估值）、`index_data get_index_kline`（日K，period=10）、`index_data get_index_fundamentals`（成分权重）、`stock_data get_stock_fundamentals`（个股基本面）。
- **缓存**：`wind_cache.json` 按 `server|tool|params` 缓存；支持 `--fresh` 强制全量重拉。
- **重试（必做）**：Wind 在并发下会限流**截断** K 线（一年 243 行只给 15 行）。K 线响应行数 < 50 视为失败，串行重试至多 4 次（间隔 2/4/6s）。
- **series 字段**：每个指数输出 `[{d:"YYYY-MM-DD", c:收盘}, ...]` 全量日序列（约 243 点），前端火花线/走势图/回测都靠它。
- **并发**：`ThreadPoolExecutor(max_workers=3)`，别更高（限流）。
- **as_of 带时分**：`%Y-%m-%d %H:%M`，交易时段是盘中快照，页脚注明。

### 2. 前端（index.html）

所有组件模式见 `references/frontend-patterns.md`（设计 tokens、格式化、SVG 图表、弹窗、卡通形象、回测、散点图、验证循环），按需读取。硬性要求：

- 涨跌幅字段**本身已是百分数，严禁 ×100**（本项目首个大 bug）。
- 数字 `tabular-nums`；红涨绿跌（A 股惯例）；图表零依赖手绘 SVG。
- 卡通形象：每模块一个手绘 SVG + CSS keyframes 动画，`prefers-reduced-motion` 降级。
- 策略实验室（如需要）：3 槽选指数 + 权重滑杆 + 按日再平衡回测 + 风险回报散点（组合黑色菱形）。

### 3. 验证（必做，不许跳过）

按 `references/frontend-patterns.md` 的「本地验证循环」：`node --check` 查 JS → `python3 -m http.server` 起服 → headless Chrome 截图 → **自己看图** → 迭代。数据正确性抽查：挑 2-3 个指数，直接调 Wind CLI 比对 `data.json` 里的值。

### 4. 部署与每日更新

```bash
cd <项目目录>
wrangler pages deploy . --project-name <项目名> --commit-dirty=true
# 每日刷新（数据 + 上线）：
python3 build_data.py && wrangler pages deploy . --project-name <项目名>
```

`.wrangler/cache/pages.json` 里存 `account_id/project_name`；`wrangler` 已全局安装则直接用，无需 npx。

## 踩坑清单（本项目实战）

| 坑 | 症状 | 解法 |
|---|---|---|
| 涨跌幅 ×100 | -2.47% 显示成 -247% | Wind 字段已是百分数，直接格式化 |
| 并发限流截断 K 线 | 白酒一年回撤显示 -5.9%（实际 -41.9%） | 行数 <50 判失败，串行重试 |
| Wind 超窗只给最旧 100 行 | “近一年”日频数据停在 7 个月前 | >100 行的窗口只返回最旧 100 行；用多个重叠短窗口（近一年/近8月/近3月）拼接 |
| 当日份额是前向填充占位 | 所有 ETF 最新 flow 恰好全为 0 | 份额 T+1 才发布；尾部与前一日相同的点要丢弃 |
| 拆分配置单复数不一致 | 拆分调整静默失效，出现假赎回 | `split`/`splits` 两种键都兼容读取 |
| 缓存陈旧 | 页面数据停在昨天 | `--fresh`；as_of 显示到分钟 |
| file:// 截图白屏 | fetch 被 CORS 拦 | 验证必须 `http://localhost` |
| headless 最小宽度 | 390px 截图右侧被裁 | 工具伪影（min ~485px），用 DOM 检测真实溢出 |
| SVG 子元素动画不生效 | 眨眼/挥手没反应 | `transform-box: fill-box; transform-origin: center` |
