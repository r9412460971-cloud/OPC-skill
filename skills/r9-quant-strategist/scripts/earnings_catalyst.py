#!/usr/bin/env python3
"""
财报催化剂研究员脚本
用法：
    python earnings_catalyst.py <股票代码> [--event Q3_2026] [--horizon 90] [--output-dir .]
示例：
    python earnings_catalyst.py 000001 --event Q3_2026 --horizon 90 --output-dir ./output
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(description="财报催化剂研究员")
    parser.add_argument("stock_code", help="股票代码，如 000001")
    parser.add_argument("--event", default="Q3_2026", help="即将发生的事件，如 Q3_2026")
    parser.add_argument("--horizon", type=int, default=90, help="前瞻时间窗口，默认 90 天")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    return parser.parse_args()


def get_stock_info(stock_code: str) -> dict:
    """获取股票基本信息"""
    try:
        df = ak.stock_info_a_code_name()
        row = df[df["code"] == stock_code]
        if row.empty:
            return {"代码": stock_code, "名称": "未知"}
        return {"代码": stock_code, "名称": row.iloc[0]["name"]}
    except Exception as e:
        print(f"获取股票信息失败: {e}")
        return {"代码": stock_code, "名称": "未知"}


def get_recent_notices(stock_code: str, days: int = 90) -> pd.DataFrame:
    """获取近期公告"""
    end = datetime.now()
    start = end - timedelta(days=days)
    try:
        df = ak.stock_individual_notice_report(
            security=stock_code,
            begin_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        return df.sort_values("公告日期", ascending=False).head(20)
    except Exception as e:
        print(f"获取公告失败: {e}")
        return pd.DataFrame()


def get_earnings_preview(stock_code: str, report_date: str = None) -> pd.DataFrame:
    """获取业绩预告数据"""
    try:
        # 尝试获取最新一期业绩预告
        df = ak.stock_yjbb_em(date=report_date)
        row = df[df["股票代码"] == stock_code]
        return row
    except Exception as e:
        print(f"获取业绩预告失败: {e}")
        return pd.DataFrame()


def get_shareholder_changes(stock_code: str, days: int = 90) -> pd.DataFrame:
    """获取股东增减持数据"""
    try:
        # AKShare 增减持接口
        df = ak.stock_ggcg_em()
        # 过滤目标股票
        if "股票代码" in df.columns:
            df = df[df["股票代码"] == stock_code]
        elif "代码" in df.columns:
            df = df[df["代码"] == stock_code]
        return df.head(10)
    except Exception as e:
        print(f"获取股东增减持失败: {e}")
        return pd.DataFrame()


def get_margin_data(stock_code: str) -> dict:
    """获取融资融券数据（最近一日）"""
    try:
        # 判断交易所
        if stock_code.startswith("6"):
            df = ak.stock_margin_detail_sse()
        else:
            df = ak.stock_margin_detail_szse()
        row = df[df["股票代码"] == stock_code]
        if row.empty:
            return {}
        return {
            "融资余额": row.iloc[0].get("融资余额", "待补"),
            "融券余额": row.iloc[0].get("融券余额", "待补"),
            "融资融券余额": row.iloc[0].get("融资融券余额", "待补"),
        }
    except Exception as e:
        print(f"获取融资融券失败: {e}")
        return {}


def get_price_data(stock_code: str, days: int = 90) -> pd.DataFrame:
    """获取近期股价数据"""
    try:
        if stock_code.startswith("6"):
            symbol = f"{stock_code}.SH"
        elif stock_code.startswith("0") or stock_code.startswith("3"):
            symbol = f"{stock_code}.SZ"
        else:
            symbol = stock_code
        df = ak.stock_zh_a_hist(symbol=stock_code, period="daily")
        df = df.rename(columns={"日期": "date", "收盘": "close", "成交量": "volume"})
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        return df.tail(days)
    except Exception as e:
        print(f"获取股价数据失败: {e}")
        return pd.DataFrame()


def generate_report(stock_code: str, event: str, horizon: int, output_dir: str):
    """生成催化剂研究备忘录"""
    info = get_stock_info(stock_code)
    name = info["名称"]

    end = datetime.now()
    start = end - timedelta(days=horizon)

    notices = get_recent_notices(stock_code, days=horizon)
    earnings = get_earnings_preview(stock_code)
    shareholders = get_shareholder_changes(stock_code, days=horizon)
    margin = get_margin_data(stock_code)
    price_df = get_price_data(stock_code, days=horizon)

    lines = []
    lines.append(f"# {name} ({stock_code}) {event} 催化剂研究备忘录")
    lines.append("")
    lines.append("## 一、执行摘要")
    lines.append("")
    lines.append(f"- **公司名称**：{name}")
    lines.append(f"- **股票代码**：{stock_code}")
    lines.append(f"- **关注事件**：{event}")
    lines.append(f"- **前瞻窗口**：未来 {horizon} 天")
    lines.append(f"- **当前看法**：待用户补充 / 中性偏多 / 中性偏空")
    lines.append(f"- **核心结论**：待分析完成后填写")
    lines.append("")
    lines.append("### 数据声明")
    lines.append(f"- 数据来源：AKShare / 东方财富 / 公开市场数据")
    lines.append(f"- 报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("- 事件预测、概率加权为分析推断，非确定性结论")
    lines.append("")

    # 近期股价表现
    lines.append("## 二、近期股价表现")
    lines.append("")
    if not price_df.empty:
        latest = price_df.iloc[-1]
        first = price_df.iloc[0]
        ret = latest["close"] / first["close"] - 1
        lines.append(f"- 近 {horizon} 个交易日涨跌幅：{ret * 100:.2f}%")
        lines.append(f"- 最新收盘价：{latest['close']:.2f}")
        lines.append(f"- 区间最高：{price_df['close'].max():.2f}")
        lines.append(f"- 区间最低：{price_df['close'].min():.2f}")
        lines.append(f"- 区间日均成交量：{price_df['volume'].mean():.0f}")
    else:
        lines.append("股价数据待补")
    lines.append("")

    # 催化剂事件时间线
    lines.append("## 三、催化剂事件时间线")
    lines.append("")
    lines.append("| 日期 | 事件 | 类型 | 影响方向 | 概率 | 备注 |")
    lines.append("|------|------|------|----------|------|------|")
    # 自动填充已知的财报/公告事件
    if not notices.empty:
        for _, row in notices.head(10).iterrows():
            title = row.get("公告标题", "")
            date = row.get("公告日期", "")
            ntype = row.get("公告类型", "")
            lines.append(f"| {date} | {title} | {ntype} | 待判断 | 待估 | 已发布公告 |")
    lines.append(f"| {event} | {event} 财报/事件 | 财报/事件 | 双向 | 100% | 核心关注 |")
    lines.append("")

    # 盈利预测与预期差
    lines.append("## 四、盈利预测与预期差")
    lines.append("")
    lines.append("| 指标 | 共识预期 | 渠道检查暗示 | 预期差 | 方向 |")
    lines.append("|------|----------|--------------|--------|------|")
    if not earnings.empty:
        row = earnings.iloc[0]
        lines.append(f"| 营业总收入(亿元) | 待补 | {row.get('营业总收入-营业总收入', '待补')} | 待计算 | 待判断 |")
        lines.append(f"| 净利润(亿元) | 待补 | {row.get('净利润-净利润', '待补')} | 待计算 | 待判断 |")
        lines.append(f"| 净利润同比增长(%) | 待补 | {row.get('净利润-同比增长', '待补')} | 待计算 | 待判断 |")
    else:
        lines.append("| 营业总收入(亿元) | 待补 | 待补 | 待计算 | 待判断 |")
        lines.append("| 净利润(亿元) | 待补 | 待补 | 待计算 | 待判断 |")
        lines.append("| EPS(元) | 待补 | 待补 | 待计算 | 待判断 |")
    lines.append("")

    # 管理层指引历史
    lines.append("## 五、管理层指引历史")
    lines.append("")
    lines.append("| 季度 | 指引 | 实际 | 偏差 | 类型判断 |")
    lines.append("|------|------|------|------|----------|")
    lines.append("| 待补 | 待补 | 待补 | 待补 | 保守/准确/过度承诺 |")
    lines.append("")
    lines.append("**统计**：近 8 个季度，保守 X 次 / 准确 X 次 / 过度承诺 X 次")
    lines.append("")

    # 供应链与渠道检查
    lines.append("## 六、供应链与渠道检查")
    lines.append("")
    lines.append("- **上游信号**：待补")
    lines.append("- **下游信号**：待补")
    lines.append("- **高频数据**：待补")
    lines.append("- **草根调研**：待补")
    lines.append("")

    # 市场情绪信号
    lines.append("## 七、市场情绪信号")
    lines.append("")
    lines.append("| 信号 | 当前值 | 近1月变化 | 解读 |")
    lines.append("|------|--------|-----------|------|")
    if margin:
        for k, v in margin.items():
            lines.append(f"| {k} | {v} | 待补 | 待判断 |")
    else:
        lines.append("| 融资余额 | 待补 | 待补 | 待判断 |")
        lines.append("| 融券余额 | 待补 | 待补 | 待判断 |")
    lines.append("| 北向资金持股 | 待补 | 待补 | 待判断 |")
    lines.append("| 期权隐含波动率 | 待补 | 待补 | 待判断 |")
    lines.append("")

    # 股东增减持
    lines.append("## 八、股东与内幕交易活动")
    lines.append("")
    if not shareholders.empty:
        lines.append("| 股东 | 变动方向 | 变动数量(万股) | 变动日期 | 信号 |")
        lines.append("|------|----------|----------------|----------|------|")
        for _, row in shareholders.head(10).iterrows():
            lines.append(f"| {row.get('股东名称', '待补')} | {row.get('变动方向', '待补')} | {row.get('变动数量', '待补')} | {row.get('变动日期', '待补')} | 待判断 |")
    else:
        lines.append("近期增减持数据待补")
    lines.append("")

    # 同业可比公司读数
    lines.append("## 九、同业可比公司读数")
    lines.append("")
    lines.append("| 公司 | 已披露业绩 | 指引变化 | 估值反应 | 对目标公司启示 |")
    lines.append("|------|------------|----------|----------|----------------|")
    lines.append("| 待补 | 待补 | 待补 | 待补 | 待补 |")
    lines.append("")

    # 共识修订趋势
    lines.append("## 十、共识修订趋势")
    lines.append("")
    lines.append("| 指标 | 近4周变化 | 趋势 |")
    lines.append("|------|-----------|------|")
    lines.append("| EPS 上调家数 | 待补 | 上调/下调 |")
    lines.append("| 目标价中位数 | 待补 | 上调/下调 |")
    lines.append("| 评级分布 | 待补 | 买入/持有/卖出 |")
    lines.append("")

    # 概率加权结果
    lines.append("## 十一、概率加权结果")
    lines.append("")
    lines.append("| 场景 | 概率 | 股价影响(%) | 加权贡献(%) | 触发条件 |")
    lines.append("|------|------|-------------|-------------|----------|")
    lines.append("| 乐观 | 25% | +20% | +5.0% | 业绩大幅超预期 + 指引上调 |")
    lines.append("| 基准 | 50% | +3% | +1.5% | 业绩符合预期 |")
    lines.append("| 悲观 | 25% | -15% | -3.75% | 业绩 miss + 指引下调 |")
    lines.append("| **期望值** | 100% | — | **+2.75%** | — |")
    lines.append("")
    lines.append("*以上概率与股价影响仅为示例，需根据实际分析调整。*")
    lines.append("")

    # 交易结构建议
    lines.append("## 十二、交易结构建议")
    lines.append("")
    lines.append("| 要素 | 建议 |")
    lines.append("|------|------|")
    lines.append("| 方向 | 做多/做空/观望 |")
    lines.append("| 仓位 | 基于波动率和信心度 |")
    lines.append("| 入场点 | 催化剂前 N 个交易日 / 事件触发后突破 |")
    lines.append("| 止损 | 技术位 / 事件证伪 / 波动率阈值 |")
    lines.append("| 止盈 | 目标价 / 事件兑现后减仓 |")
    lines.append("| 时间窗口 | 事件前 / 事件后持有期 |")
    lines.append("| 对冲 | 行业 ETF / 指数期货 / 期权保护 |")
    lines.append("")

    # 风险提示
    lines.append("## 十三、风险提示")
    lines.append("")
    lines.append("- 催化剂时间可能变动")
    lines.append("- 渠道检查数据可能存在偏差")
    lines.append("- 市场宏观环境可能覆盖个股催化剂")
    lines.append("- 做空/期权交易存在特殊风险")
    lines.append("- 本备忘录不构成投资建议")
    lines.append("")

    output_path = Path(output_dir) / f"催化剂_{stock_code}_{event}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"报告已生成：{output_path}")


def main():
    args = parse_args()
    generate_report(args.stock_code, args.event, args.horizon, args.output_dir)


if __name__ == "__main__":
    main()
