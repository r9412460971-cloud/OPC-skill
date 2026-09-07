#!/usr/bin/env python3
"""
激进投资者分析器脚本
用法：
    python activist_analyzer.py <公司代码> [--activist 投资者名称] [--output-dir .]
示例：
    python activist_analyzer.py 000001 --activist 某对冲基金 --output-dir ./output
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(description="激进投资者分析器")
    parser.add_argument("stock_code", help="公司股票代码，如 000001")
    parser.add_argument("--activist", default="待指定", help="激进投资者名称")
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


def get_top_shareholders(stock_code: str) -> pd.DataFrame:
    """获取前十大股东"""
    try:
        df = ak.stock_main_stock_holder(stock=stock_code)
        return df.head(10)
    except Exception as e:
        print(f"获取前十大股东失败: {e}")
        return pd.DataFrame()


def get_recent_notices(stock_code: str, days: int = 180) -> pd.DataFrame:
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


def get_stock_price(stock_code: str, days: int = 180) -> pd.DataFrame:
    """获取近期股价"""
    try:
        df = ak.stock_zh_a_hist(symbol=stock_code, period="daily")
        df = df.rename(columns={"日期": "date", "收盘": "close"})
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        return df.tail(days)
    except Exception as e:
        print(f"获取股价失败: {e}")
        return pd.DataFrame()


def generate_report(stock_code: str, activist: str, output_dir: str):
    """生成激进投资者分析报告"""
    info = get_stock_info(stock_code)
    name = info["名称"]

    shareholders = get_top_shareholders(stock_code)
    notices = get_recent_notices(stock_code)
    price_df = get_stock_price(stock_code)

    lines = []
    lines.append(f"# {name} ({stock_code}) vs {activist} Pershing Square 风格激进情况分析")
    lines.append("")
    lines.append("## 一、执行摘要")
    lines.append("")
    lines.append(f"- **公司名称**：{name}")
    lines.append(f"- **股票代码**：{stock_code}")
    lines.append(f"- **激进投资者**：{activist}")
    lines.append("- **核心诉求**：待通过网络搜索 / 公开信原文补充")
    lines.append("- **交易建议**：买入 / 观望 / 回避（待分析）")
    lines.append("- **概率加权预期回报**：待分析")
    lines.append("")
    lines.append("### 数据声明")
    lines.append("- 数据来源：AKShare / 东方财富 / 公开市场数据")
    lines.append(f"- 报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("- 激进投资者数据需结合网络搜索、交易所披露、SEC/港交所文件交叉验证")
    lines.append("")

    # 近期股价表现
    lines.append("## 二、近期股价表现")
    lines.append("")
    if not price_df.empty:
        latest = price_df.iloc[-1]
        first = price_df.iloc[0]
        ret = latest["close"] / first["close"] - 1
        lines.append(f"- 近 180 个交易日涨跌幅：{ret * 100:.2f}%")
        lines.append(f"- 最新收盘价：{latest['close']:.2f}")
        lines.append(f"- 区间最高：{price_df['close'].max():.2f}")
        lines.append(f"- 区间最低：{price_df['close'].min():.2f}")
    else:
        lines.append("股价数据待补")
    lines.append("")

    # 激进投资者画像
    lines.append("## 三、激进投资者画像")
    lines.append("")
    lines.append("| 维度 | 内容 |")
    lines.append("|------|------|")
    lines.append(f"| 名称 | {activist} |")
    lines.append("| 类型 | 对冲基金 / 私募股权 / 个人大股东（待确认） |")
    lines.append("| AUM | 待补 |")
    lines.append("| 历史激进案例 | 待补 |")
    lines.append("| 胜率 | 待补 |")
    lines.append("| 平均持有期 | 待补 |")
    lines.append("| 风格 | 待补 |")
    lines.append("")

    # 核心诉求与价值释放逻辑
    lines.append("## 四、核心诉求与价值释放逻辑")
    lines.append("")
    lines.append("| 诉求 | 价值释放逻辑 | 可行性 | 管理层抵触 | 股东支持 |")
    lines.append("|------|--------------|--------|------------|----------|")
    lines.append("| 待补 | 待补 | 待判断 | 待判断 | 待判断 |")
    lines.append("")

    # 管理层回应评估
    lines.append("## 五、管理层回应评估")
    lines.append("")
    lines.append("- **管理层主要论点**：待补")
    lines.append("- **反驳有效性评估**：待补")
    lines.append("- **管理层可信度**：待补")
    lines.append("")

    # 估值差距分析
    lines.append("## 六、估值差距分析")
    lines.append("")
    lines.append("| 估值方法 | 当前 | 激进目标 | 上行空间 |")
    lines.append("|----------|------|----------|----------|")
    lines.append("| PE | 待补 | 待补 | 待补 |")
    lines.append("| EV/EBITDA | 待补 | 待补 | 待补 |")
    lines.append("| Sum-of-the-parts | 待补 | 待补 | 待补 |")
    lines.append("| DCF | 待补 | 待补 | 待补 |")
    lines.append("")

    # 代理权争夺概率与投票预测
    lines.append("## 七、代理权争夺概率与投票预测")
    lines.append("")
    lines.append("| 项目 | 评估 |")
    lines.append("|------|------|")
    lines.append("| 代理权争夺概率 | 高/中/低（待判断） |")
    lines.append("| 关键日期 | 年度股东大会 / 特别股东大会（待确认） |")
    lines.append("| 机构站队 | 待补 |")
    lines.append("| ISS/Glass Lewis 预测 | 待补 |")
    lines.append("| 预计投票结果 | 待补 |")
    lines.append("")

    # 历史先例
    lines.append("## 八、历史先例")
    lines.append("")
    lines.append("| 案例 | 激进投资者 | 诉求 | 结果 | 启示 |")
    lines.append("|------|------------|------|------|------|")
    lines.append("| 待补 | 待补 | 待补 | 待补 | 待补 |")
    lines.append("")

    # 关键日期时间线
    lines.append("## 九、关键日期时间线")
    lines.append("")
    lines.append("| 日期 | 事件 | 重要性 |")
    lines.append("|------|------|--------|")
    lines.append("| 待补 | 激进投资者建仓披露 | 事件起点 |")
    lines.append("| 待补 | 公开信/13D 披露 | 公开对抗 |")
    lines.append("| 待补 | 管理层回应 | 防御姿态 |")
    lines.append("| 待补 | 代理权征集截止 | 投票动员 |")
    lines.append("| 待补 | 股东大会 | 决战日 |")
    lines.append("")

    # 概率树与加权回报预测
    lines.append("## 十、概率树与加权回报预测")
    lines.append("")
    lines.append("| 场景 | 概率 | 股价影响(%) | 加权贡献(%) | 触发条件 |")
    lines.append("|------|------|-------------|-------------|----------|")
    lines.append("| 激进完全成功 | 30% | +40% | +12.0% | 董事会改组 + 战略执行 |")
    lines.append("| 部分成功 | 40% | +15% | +6.0% | 部分诉求实现 |")
    lines.append("| 僵持/失败 | 25% | -10% | -2.5% | 管理层保住控制权 |")
    lines.append("| 极端下行 | 5% | -30% | -1.5% | 激进投资者割肉退出 |")
    lines.append("| **期望值** | 100% | — | **+14.0%** | — |")
    lines.append("")
    lines.append("*以上概率与股价影响仅为示例，需根据实际分析调整。*")
    lines.append("")

    # 机构持仓站队
    lines.append("## 十一、机构持仓站队")
    lines.append("")
    if not shareholders.empty:
        lines.append("| 排名 | 股东名称 | 持股比例(%) | 股本性质 | 可能立场 |")
        lines.append("|------|----------|-------------|----------|----------|")
        for _, row in shareholders.iterrows():
            holder = row.get("股东名称", "待补")
            pct = row.get("持股比例", "待补")
            nature = row.get("股本性质", "待补")
            lines.append(f"| {row.get('编号', '待补')} | {holder} | {pct} | {nature} | 待判断 |")
    else:
        lines.append("前十大股东数据待补")
    lines.append("")

    # 交易建议
    lines.append("## 十二、交易建议")
    lines.append("")
    lines.append("| 要素 | 建议 |")
    lines.append("|------|------|")
    lines.append("| 评级 | 买入/观望/回避（待判断） |")
    lines.append("| 进场点 | 待补 |")
    lines.append("| 目标价 | 待补 |")
    lines.append("| 止损 | 待补 |")
    lines.append("| 时间窗口 | 待补 |")
    lines.append("| 仓位 | 待补 |")
    lines.append("| 对冲 | 待补 |")
    lines.append("")

    # 近期相关公告
    lines.append("## 十三、近期相关公告")
    lines.append("")
    if not notices.empty:
        lines.append("| 日期 | 公告标题 | 类型 |")
        lines.append("|------|----------|------|")
        for _, row in notices.head(15).iterrows():
            lines.append(f"| {row.get('公告日期', '')} | {row.get('公告标题', '')} | {row.get('公告类型', '')} |")
    else:
        lines.append("近期公告数据待补")
    lines.append("")

    # 风险提示
    lines.append("## 十四、风险提示")
    lines.append("")
    lines.append("- 激进投资者可能提前退出")
    lines.append("- 管理层可能采取防御措施（毒丸、金色降落伞等）")
    lines.append("- 监管审查可能延长事件进程")
    lines.append("- 市场情绪变化可能覆盖个股催化剂")
    lines.append("- 本分析不构成投资建议")
    lines.append("")

    output_path = Path(output_dir) / f"激进分析_{stock_code}_{activist.replace(' ', '_')}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"报告已生成：{output_path}")


def main():
    args = parse_args()
    generate_report(args.stock_code, args.activist, args.output_dir)


if __name__ == "__main__":
    main()
