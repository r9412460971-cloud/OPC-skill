#!/usr/bin/env python3
"""
基金多季度备案追踪对比脚本
追踪最新季报及过去 N 个季报的持仓变化
用法：
    python fund_filing_tracker_multi.py <基金代码> [--quarters 5] [--output-dir .]
示例：
    python fund_filing_tracker_multi.py 501210 --quarters 5 --output-dir ./output
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import akshare as ak
import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(description="基金多季度备案追踪对比")
    parser.add_argument("fund_code", help="基金代码，如 501210")
    parser.add_argument("--quarters", type=int, default=5, help="对比季度数，默认 5（最新 + 过去 4 个）")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    return parser.parse_args()


def get_fund_info(fund_code: str) -> dict:
    try:
        df = ak.fund_name_em()
        row = df[df["基金代码"] == fund_code]
        if row.empty:
            return {"基金代码": fund_code, "基金简称": "未知", "基金类型": "未知"}
        return {
            "基金代码": fund_code,
            "基金简称": row.iloc[0].get("基金简称", "未知"),
            "基金类型": row.iloc[0].get("基金类型", "未知"),
        }
    except Exception as e:
        print(f"获取基金信息失败: {e}")
        return {"基金代码": fund_code, "基金简称": "未知", "基金类型": "未知"}


def get_holdings_for_year(fund_code: str, year: int) -> pd.DataFrame:
    """获取指定年份的全部季度持仓数据"""
    try:
        df = ak.fund_portfolio_hold_em(symbol=fund_code, date=str(year))
        df = df.rename(
            columns={
                "股票代码": "代码",
                "股票名称": "名称",
                "占净值比例": "占净值比",
                "持股数": "持股数",
                "持仓市值": "持仓市值",
                "季度": "季度标签",
            }
        )
        df["占净值比"] = pd.to_numeric(df["占净值比"], errors="coerce")
        df["持股数"] = pd.to_numeric(df["持股数"], errors="coerce")
        df["持仓市值"] = pd.to_numeric(df["持仓市值"], errors="coerce")
        # 按季度分组取前 10
        df = df.sort_values(["季度标签", "占净值比"], ascending=[True, False])
        df = df.groupby("季度标签").head(10).reset_index(drop=True)
        df["年份"] = year
        return df
    except Exception as e:
        print(f"获取 {year} 年持仓失败: {e}")
        return pd.DataFrame()


def extract_quarter(label: str) -> str:
    """从 '2026年1季度股票投资明细' 提取 '2026Q1'"""
    m = re.match(r"(\d{4})年(\d)季度股票投资明细", label)
    if m:
        return f"{m.group(1)}Q{m.group(2)}"
    return label


def get_recent_quarters(fund_code: str, n: int) -> pd.DataFrame:
    """获取最近 n 个季度的数据"""
    current_year = datetime.now().year
    all_data = []
    for year in range(current_year, current_year - 3, -1):
        df = get_holdings_for_year(fund_code, year)
        if not df.empty:
            all_data.append(df)

    if not all_data:
        return pd.DataFrame()

    combined = pd.concat(all_data, ignore_index=True)
    combined["季度"] = combined["季度标签"].apply(extract_quarter)
    combined = combined.sort_values("季度", ascending=False)

    # 取最近 n 个季度
    unique_q = combined["季度"].unique()
    selected_q = unique_q[:n]
    return combined[combined["季度"].isin(selected_q)].copy()


def get_industry_for_year(fund_code: str, year: int) -> pd.DataFrame:
    try:
        df = ak.fund_portfolio_industry_allocation_em(symbol=fund_code, date=str(year))
        df = df.rename(columns={"行业类别": "行业", "占净值比例": "占净值比"})
        df["占净值比"] = pd.to_numeric(df["占净值比"], errors="coerce")
        df["年份"] = year
        return df
    except Exception as e:
        print(f"获取 {year} 年行业配置失败: {e}")
        return pd.DataFrame()


def get_recent_industries(fund_code: str, quarters: list) -> pd.DataFrame:
    """获取指定季度的行业配置"""
    years = sorted(set([int(q[:4]) for q in quarters]))
    all_data = []
    for year in years:
        df = get_industry_for_year(fund_code, year)
        if not df.empty:
            all_data.append(df)
    if not all_data:
        return pd.DataFrame()
    combined = pd.concat(all_data, ignore_index=True)
    return combined


def conviction_level(pct: float) -> str:
    if pct >= 8:
        return "🔥🔥🔥🔥🔥"
    elif pct >= 6:
        return "🔥🔥🔥🔥"
    elif pct >= 4:
        return "🔥🔥🔥"
    elif pct >= 2:
        return "🔥🔥"
    else:
        return "🔥"


def generate_multi_report(fund_code: str, n: int, output_dir: str):
    fund_info = get_fund_info(fund_code)
    data = get_recent_quarters(fund_code, n)
    if data.empty:
        print(f"未能获取 {fund_code} 的持仓数据")
        sys.exit(1)

    quarters = sorted(data["季度"].unique(), reverse=True)
    latest_q = quarters[0]

    # 透视表：每只股票在各季度的占净值比
    pivot = data.pivot_table(index=["代码", "名称"], columns="季度", values="占净值比", aggfunc="first")
    pivot = pivot.reset_index()
    pivot.columns.name = None
    pivot = pivot.fillna(0)

    # 只保留至少在任一季度进入前十大的股票
    pivot["最大占比"] = pivot[quarters].max(axis=1)
    pivot = pivot[pivot["最大占比"] > 0].sort_values("最大占比", ascending=False)

    # 计算集中度指标
    concentration = []
    for q in quarters:
        q_data = data[data["季度"] == q]
        top10_sum = q_data["占净值比"].sum()
        top5_sum = q_data.head(5)["占净值比"].sum()
        hhi = sum((q_data["占净值比"] / 100) ** 2) * 10000
        concentration.append(
            {
                "季度": q,
                "前10大合计": top10_sum,
                "前5大合计": top5_sum,
                "HHI": hhi,
                "股票数量": len(q_data),
            }
        )
    conc_df = pd.DataFrame(concentration)

    # 持续变化模式识别
    patterns = []
    for _, row in pivot.iterrows():
        values = [row[q] for q in quarters]
        current = values[0]
        prev = values[1] if len(values) > 1 else 0

        if current > 0 and prev == 0:
            patterns.append({"代码": row["代码"], "名称": row["名称"], "模式": "新进入"})
        elif current == 0 and prev > 0:
            patterns.append({"代码": row["代码"], "名称": row["名称"], "模式": "已退出"})
        elif current > prev > 0:
            patterns.append({"代码": row["代码"], "名称": row["名称"], "模式": "持续增持"})
        elif 0 < current < prev:
            patterns.append({"代码": row["代码"], "名称": row["名称"], "模式": "持续减持"})
    patterns_df = pd.DataFrame(patterns)

    # 行业配置
    industries = get_recent_industries(fund_code, quarters)
    if not industries.empty:
        industries["季度"] = industries["截止时间"].apply(lambda x: f"{x[:4]}Q{int(x[5:7]) // 3 + (1 if int(x[5:7]) % 3 != 0 else 0)}")
        # 修正季度计算
        def date_to_quarter(d):
            year = d[:4]
            month = int(d[5:7])
            q = (month - 1) // 3 + 1
            return f"{year}Q{q}"
        industries["季度"] = industries["截止时间"].apply(date_to_quarter)
        industries = industries[industries["季度"].isin(quarters)]

    # 生成报告
    lines = []
    lines.append(f"# {fund_info['基金简称']} ({fund_code}) 最近 {n} 个季度备案追踪对比情报")
    lines.append("")
    lines.append("## 一、执行摘要")
    lines.append("")
    lines.append(f"- **基金名称**：{fund_info['基金简称']}")
    lines.append(f"- **基金代码**：{fund_code}")
    lines.append(f"- **基金类型**：{fund_info['基金类型']}")
    lines.append(f"- **对比季度**：{', '.join(quarters)}")
    lines.append(f"- **最新季度**：{latest_q}")
    lines.append("")
    lines.append("### 数据声明")
    lines.append("- 数据来源：AKShare / 天天基金网 / 基金季报")
    lines.append(f"- 报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("- 仅含各季度前十大重仓股，无法反映完整持仓")
    lines.append("")

    # 集中度变化
    lines.append("## 二、持仓集中度变化")
    lines.append("")
    lines.append("| 季度 | 前10大合计(%) | 前5大合计(%) | HHI | 股票数量 |")
    lines.append("|------|---------------|--------------|-----|----------|")
    for _, row in conc_df.iterrows():
        lines.append(
            f"| {row['季度']} | {row['前10大合计']:.2f} | {row['前5大合计']:.2f} | {row['HHI']:.0f} | {row['股票数量']} |"
        )
    lines.append("")

    # 全部季度持仓轨迹
    lines.append(f"## 三、前十大持仓跨季度轨迹（{len(pivot)} 只股票）")
    lines.append("")
    header_cols = ["代码", "名称"] + quarters + ["最大占比", "最新信号"]
    lines.append("| " + " | ".join(header_cols) + " |")
    lines.append("|" + "|".join(["------"] * len(header_cols)) + "|")

    for _, row in pivot.iterrows():
        prev_q = quarters[1] if len(quarters) > 1 else None
        prev_val = row[prev_q] if prev_q else 0
        curr_val = row[latest_q]

        if curr_val == 0:
            latest_signal = "已退出"
        elif prev_val == 0:
            latest_signal = "新进入"
        elif curr_val > prev_val:
            latest_signal = "增持"
        elif curr_val < prev_val:
            latest_signal = "减持"
        else:
            latest_signal = "持平"

        vals = [row["代码"], row["名称"]]
        for q in quarters:
            v = row[q]
            vals.append(f"{v:.2f}" if v > 0 else "-")
        vals.append(f"{row['最大占比']:.2f}")
        vals.append(latest_signal)
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")

    # 模式汇总
    lines.append("## 四、持仓变化模式汇总")
    lines.append("")
    for pattern in ["新进入", "持续增持", "持续减持", "已退出"]:
        subset = patterns_df[patterns_df["模式"] == pattern]
        lines.append(f"### {pattern}（{len(subset)} 只）")
        if subset.empty:
            lines.append("无")
        else:
            lines.append("| 代码 | 名称 |")
            lines.append("|------|------|")
            for _, row in subset.iterrows():
                lines.append(f"| {row['代码']} | {row['名称']} |")
        lines.append("")

    # 最新季度前十大详情
    lines.append(f"## 五、{latest_q} 前十大持仓明细")
    lines.append("")
    lines.append("| 排名 | 代码 | 名称 | 占净值比(%) | 信念等级 | 季度变化 |")
    lines.append("|------|------|------|-------------|----------|----------|")
    latest_data = data[data["季度"] == latest_q].sort_values("占净值比", ascending=False).reset_index(drop=True)
    for i, row in latest_data.iterrows():
        prev_q = quarters[1] if len(quarters) > 1 else None
        if prev_q:
            prev_row = pivot[(pivot["代码"] == row["代码"])]
            prev_pct = prev_row[prev_q].iloc[0] if not prev_row.empty else 0
            change = row["占净值比"] - prev_pct
            change_str = f"{change:+.2f}"
        else:
            change_str = "-"
        lines.append(
            f"| {i+1} | {row['代码']} | {row['名称']} | {row['占净值比']:.2f} | {conviction_level(row['占净值比'])} | {change_str} |"
        )
    lines.append("")

    # 行业配置变化
    lines.append("## 六、行业配置变化")
    lines.append("")
    if not industries.empty:
        # 透视表
        ind_pivot = industries.pivot_table(index="行业", columns="季度", values="占净值比", aggfunc="first")
        ind_pivot = ind_pivot.reset_index()
        ind_pivot.columns.name = None
        ind_pivot = ind_pivot.fillna(0)
        ind_pivot["最大占比"] = ind_pivot[quarters].max(axis=1)
        ind_pivot = ind_pivot[ind_pivot["最大占比"] > 0].sort_values("最大占比", ascending=False)

        header = ["行业"] + quarters
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["------"] * len(header)) + "|")
        for _, row in ind_pivot.head(15).iterrows():
            vals = [row["行业"]]
            for q in quarters:
                v = row[q]
                vals.append(f"{v:.2f}" if v > 0 else "-")
            lines.append("| " + " | ".join(vals) + " |")
    else:
        lines.append("行业配置数据待补")
    lines.append("")

    # 核心结论
    lines.append("## 七、核心结论")
    lines.append("")
    new_count = len(patterns_df[patterns_df["模式"] == "新进入"])
    increase_count = len(patterns_df[patterns_df["模式"] == "持续增持"])
    decrease_count = len(patterns_df[patterns_df["模式"] == "持续减持"])
    exit_count = len(patterns_df[patterns_df["模式"] == "已退出"])
    lines.append(f"- 最新季度新进前十大标的：{new_count} 只")
    lines.append(f"- 近季度持续增持标的：{increase_count} 只")
    lines.append(f"- 近季度持续减持标的：{decrease_count} 只")
    lines.append(f"- 近季度退出前十大标的：{exit_count} 只")
    lines.append(f"- 最新季度持仓集中度 HHI：{conc_df.iloc[0]['HHI']:.0f}")
    lines.append("")

    # 3个最值得关注的动作
    lines.append("## 八、3 个最值得关注的跨季度信号")
    lines.append("")
    lines.append("| 优先级 | 标的 | 模式 | 解读 |")
    lines.append("|--------|------|------|------|")
    # 按最大占比排序取前3
    top_signals = patterns_df.merge(pivot[["代码", "名称", "最大占比"]], on=["代码", "名称"], how="left")
    top_signals = top_signals.sort_values("最大占比", ascending=False).head(3)
    for i, row in top_signals.iterrows():
        lines.append(f"| {i+1} | {row['名称']}({row['代码']}) | {row['模式']} | 跨季度重要调仓信号 |")
    lines.append("")

    # 风险提示
    lines.append("## 九、风险提示")
    lines.append("")
    lines.append("- 季报披露存在滞后性")
    lines.append("- 仅基于前十大重仓股，完整持仓未知")
    lines.append("- 基金经理可能在季报披露后继续调仓")
    lines.append("- 聪明钱信号仅为逆向分析线索，不构成投资建议")
    lines.append("")

    output_path = Path(output_dir) / f"备案追踪多季度_{fund_code}_{latest_q}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"报告已生成：{output_path}")
    return str(output_path)


def main():
    args = parse_args()
    generate_multi_report(args.fund_code, args.quarters, args.output_dir)


if __name__ == "__main__":
    main()
