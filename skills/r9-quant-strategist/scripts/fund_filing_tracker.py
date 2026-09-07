#!/usr/bin/env python3
"""
基金季报备案追踪器脚本
用法：
    python fund_filing_tracker.py <基金代码> [--quarter YYYYQ#] [--output-dir .]
示例：
    python fund_filing_tracker.py 519702 --quarter 2024Q3 --output-dir ./output
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
    parser = argparse.ArgumentParser(description="基金季报备案追踪器")
    parser.add_argument("fund_code", help="基金代码，如 519702")
    parser.add_argument("--quarter", default=None, help="目标季度，如 2024Q3；默认最新可获取季度")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    parser.add_argument("--peers", default=None, help="同业基金代码，逗号分隔，如 163406,001938")
    return parser.parse_args()


def validate_quarter(q: str):
    """验证季度格式 YYYYQ[1-4]"""
    if not re.match(r"^\d{4}Q[1-4]$", q):
        raise ValueError(f"季度格式错误: {q}，应为 YYYYQ#，如 2024Q3")
    return q


def quarter_to_cn_label(q: str):
    """2024Q3 -> 2024年3季度股票投资明细"""
    year, qn = q.split("Q")
    return f"{year}年{qn}季度股票投资明细"


def quarter_to_end_date(q: str):
    """2024Q3 -> 2024-09-30"""
    year, qn = q.split("Q")
    month_day = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}
    return f"{year}-{month_day[qn]}"



def prev_quarter(q: str):
    """计算上一季度"""
    year, qn = int(q[:4]), int(q[5])
    if qn == 1:
        return f"{year - 1}Q4"
    return f"{year}Q{qn - 1}"


def get_fund_info(fund_code: str) -> dict:
    """获取基金基本信息"""
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


def get_holdings(fund_code: str, year: str) -> pd.DataFrame:
    """获取基金全年重仓股数据，按占净值比排序并取前10"""
    df = ak.fund_portfolio_hold_em(symbol=fund_code, date=year)
    # 统一列名
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
    # 按季度分组，取每组占净值比最高的 10 只
    df = df.sort_values(["季度标签", "占净值比"], ascending=[True, False])
    df = df.groupby("季度标签").head(10).reset_index(drop=True)
    # 重新生成排名
    df["序号"] = df.groupby("季度标签").cumcount() + 1
    return df


def get_industry_allocation(fund_code: str, year: str) -> pd.DataFrame:
    """获取基金行业配置"""
    try:
        df = ak.fund_portfolio_industry_allocation_em(symbol=fund_code, date=year)
        df = df.rename(columns={"行业类别": "行业", "占净值比例": "占净值比"})
        df["占净值比"] = pd.to_numeric(df["占净值比"], errors="coerce")
        return df
    except Exception as e:
        print(f"获取行业配置失败: {e}")
        return pd.DataFrame()


def analyze_holdings(curr_df: pd.DataFrame, prev_df: pd.DataFrame):
    """分析持仓变化"""
    curr = curr_df.copy()
    prev = prev_df.copy()

    curr_map = curr.set_index("代码")["占净值比"].to_dict()
    prev_map = prev.set_index("代码")["占净值比"].to_dict()

    all_codes = set(curr_map.keys()) | set(prev_map.keys())

    rows = []
    for code in all_codes:
        c_pct = curr_map.get(code)
        p_pct = prev_map.get(code)
        name = curr[curr["代码"] == code]["名称"].iloc[0] if code in curr_map else prev[prev["代码"] == code]["名称"].iloc[0]

        if p_pct is None or pd.isna(p_pct):
            action = "新建"
            change_pp = c_pct
            change_pct = None
        elif c_pct is None or pd.isna(c_pct):
            action = "清仓"
            change_pp = -p_pct
            change_pct = None
        elif c_pct > p_pct:
            action = "增持"
            change_pp = c_pct - p_pct
            change_pct = (change_pp / p_pct) * 100 if p_pct > 0 else None
        elif c_pct < p_pct:
            action = "减持"
            change_pp = c_pct - p_pct
            change_pct = (change_pp / p_pct) * 100 if p_pct > 0 else None
        else:
            action = "持平"
            change_pp = 0
            change_pct = 0

        rows.append(
            {
                "代码": code,
                "名称": name,
                "本期占比": c_pct if c_pct is not None else 0,
                "上期占比": p_pct if p_pct is not None else 0,
                "变动pp": change_pp,
                "变动幅度": change_pct,
                "动作": action,
            }
        )

    return pd.DataFrame(rows)


def conviction_level(pct: float) -> str:
    if pct >= 8:
        return "🔥🔥🔥🔥🔥 极高"
    elif pct >= 6:
        return "🔥🔥🔥🔥 高"
    elif pct >= 4:
        return "🔥🔥🔥 中高"
    elif pct >= 2:
        return "🔥🔥 中"
    else:
        return "🔥 低"


def heat_bar(pct: float) -> str:
    """生成信念热力条"""
    if pct >= 8:
        return "█████"
    elif pct >= 6:
        return "████░"
    elif pct >= 4:
        return "███░░"
    elif pct >= 2:
        return "██░░░"
    else:
        return "█░░░░"


def signal_strength(change_pp: float, is_new: bool, rank: int) -> str:
    if is_new and rank <= 5:
        return "高"
    if abs(change_pp) >= 3:
        return "高"
    if abs(change_pp) >= 1:
        return "中"
    return "低"


def generate_report(fund_code: str, quarter: str, output_dir: str, peers: list = None):
    """生成备案追踪报告"""
    fund_info = get_fund_info(fund_code)
    year = quarter[:4]
    prev_q = prev_quarter(quarter)

    # 获取持仓
    holdings = get_holdings(fund_code, year)
    if holdings.empty:
        print(f"未能获取 {fund_code} {year} 年持仓数据")
        sys.exit(1)

    curr_label = quarter_to_cn_label(quarter)
    prev_label = quarter_to_cn_label(prev_q)

    curr_df = holdings[holdings["季度标签"] == curr_label].copy()
    prev_df = holdings[holdings["季度标签"] == prev_label].copy()

    if curr_df.empty:
        print(f"未找到 {quarter} 数据，可获取季度：{holdings['季度标签'].unique().tolist()}")
        sys.exit(1)

    # 分析变化
    analysis = analyze_holdings(curr_df, prev_df)

    # 行业配置
    industry_df = get_industry_allocation(fund_code, year)
    end_date = quarter_to_end_date(quarter)
    industry_curr = industry_df[industry_df["截止时间"] == end_date].copy()

    # 信念集中度
    top10_total = curr_df["占净值比"].sum()
    top5_total = curr_df.head(5)["占净值比"].sum()
    hhi = sum((curr_df["占净值比"] / 100) ** 2) * 10000

    # 同业重叠分析
    overlap_data = []
    if peers:
        for peer in peers:
            try:
                peer_df = get_holdings(peer, year)
                peer_curr = peer_df[peer_df["季度标签"] == curr_label]
                peer_codes = set(peer_curr["代码"].tolist())
                overlap = peer_codes & set(curr_df["代码"].tolist())
                overlap_data.append(
                    {
                        "基金": peer,
                        "共同持仓数": len(overlap),
                        "共同持仓": ",".join(sorted(overlap)),
                    }
                )
            except Exception as e:
                print(f"获取同业 {peer} 数据失败: {e}")

    # 生成 Markdown
    lines = []
    lines.append(f"# {fund_info['基金简称']} ({fund_code}) {quarter} 13F 风格备案追踪情报")
    lines.append("")
    lines.append("## 一、执行摘要")
    lines.append("")
    lines.append(f"- **基金名称**：{fund_info['基金简称']}")
    lines.append(f"- **基金代码**：{fund_code}")
    lines.append(f"- **基金类型**：{fund_info['基金类型']}")
    lines.append(f"- **目标季度**：{quarter}")
    lines.append(f"- **对比季度**：{prev_q}")
    lines.append(f"- **前十大合计占净值比**：{top10_total:.2f}%")
    lines.append(f"- **前五合计占净值比**：{top5_total:.2f}%")
    lines.append(f"- **持仓集中度 HHI**：{hhi:.0f}")
    lines.append("")
    lines.append("### 数据声明")
    lines.append(f"- 数据来源：AKShare / 天天基金网 / 基金季报")
    lines.append(f"- 报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- 仅含前十大重仓股，完整持仓以基金季报为准")
    lines.append("")

    # 前十大持仓
    lines.append("## 二、前十大持仓明细")
    lines.append("")
    lines.append("| 排名 | 代码 | 名称 | 持股数(万股) | 仓位价值(亿元) | 占净值比(%) | 动作 | 变动pp |")
    lines.append("|------|------|------|--------------|----------------|-------------|------|--------|")
    for i, row in curr_df.iterrows():
        rank = int(row.get("序号", i + 1))
        code = row["代码"]
        name = row["名称"]
        shares = row.get("持股数", 0)
        mv = row.get("持仓市值", 0) / 10000  # 万元 -> 亿元
        pct = row["占净值比"]
        a_row = analysis[analysis["代码"] == code].iloc[0]
        action = a_row["动作"]
        change_pp = a_row["变动pp"]
        lines.append(f"| {rank} | {code} | {name} | {shares:.2f} | {mv:.2f} | {pct:.2f} | {action} | {change_pp:+.2f} |")
    lines.append("")

    # 仓位变动矩阵
    lines.append("## 三、仓位变动矩阵")
    lines.append("")

    new_positions = analysis[analysis["动作"] == "新建"].sort_values("本期占比", ascending=False)
    increased = analysis[analysis["动作"] == "增持"].sort_values("变动pp", ascending=False)
    decreased = analysis[analysis["动作"] == "减持"].sort_values("变动pp", ascending=True)
    exited = analysis[analysis["动作"] == "清仓"].sort_values("上期占比", ascending=False)

    def change_block(title: str, df: pd.DataFrame, cols: list):
        lines.append(f"### {title}")
        if df.empty:
            lines.append("无")
            lines.append("")
            return
        header = "| " + " | ".join([c[0] for c in cols]) + " |"
        sep = "|" + "|".join(["------" for _ in cols]) + "|"
        lines.append(header)
        lines.append(sep)
        for _, row in df.iterrows():
            vals = []
            for _, fmt in cols:
                vals.append(fmt(row))
            lines.append("| " + " | ".join(vals) + " |")
        lines.append("")

    change_block(
        "3.1 新建仓位",
        new_positions,
        [
            ("代码", lambda r: r["代码"]),
            ("名称", lambda r: r["名称"]),
            ("占净值比(%)", lambda r: f"{r['本期占比']:.2f}"),
            ("行业", lambda r: "待补"),
            ("信号解读", lambda r: "新进入前十大"),
        ],
    )

    change_block(
        "3.2 增持仓位",
        increased,
        [
            ("代码", lambda r: r["代码"]),
            ("名称", lambda r: r["名称"]),
            ("本期(%)", lambda r: f"{r['本期占比']:.2f}"),
            ("上期(%)", lambda r: f"{r['上期占比']:.2f}"),
            ("变动pp", lambda r: f"{r['变动pp']:+.2f}"),
            ("变动幅度(%)", lambda r: f"{r['变动幅度']:.1f}" if pd.notna(r["变动幅度"]) else "-"),
            ("行业", lambda r: "待补"),
        ],
    )

    change_block(
        "3.3 减持仓位",
        decreased,
        [
            ("代码", lambda r: r["代码"]),
            ("名称", lambda r: r["名称"]),
            ("本期(%)", lambda r: f"{r['本期占比']:.2f}"),
            ("上期(%)", lambda r: f"{r['上期占比']:.2f}"),
            ("变动pp", lambda r: f"{r['变动pp']:+.2f}"),
            ("变动幅度(%)", lambda r: f"{r['变动幅度']:.1f}" if pd.notna(r["变动幅度"]) else "-"),
            ("行业", lambda r: "待补"),
        ],
    )

    change_block(
        "3.4 清仓仓位",
        exited,
        [
            ("代码", lambda r: r["代码"]),
            ("名称", lambda r: r["名称"]),
            ("上期占比(%)", lambda r: f"{r['上期占比']:.2f}"),
            ("行业", lambda r: "待补"),
            ("风险信号", lambda r: "高" if r["上期占比"] > 5 else "中" if r["上期占比"] > 2 else "低"),
        ],
    )

    # 行业配置
    lines.append("## 四、行业配置分布")
    lines.append("")
    if not industry_curr.empty:
        lines.append("| 行业 | 占净值比(%) | 市值(亿元) |")
        lines.append("|------|-------------|------------|")
        for _, row in industry_curr.head(10).iterrows():
            lines.append(f"| {row['行业']} | {row['占净值比']:.2f} | {row['市值'] / 10000:.2f} |")
    else:
        lines.append("行业配置数据待补")
    lines.append("")

    # 信念热力图
    lines.append("## 五、信念热力图")
    lines.append("")
    lines.append("| 代码 | 名称 | 占净值比(%) | 信念等级 | 热力 |")
    lines.append("|------|------|-------------|----------|------|")
    for _, row in curr_df.iterrows():
        pct = row["占净值比"]
        lines.append(f"| {row['代码']} | {row['名称']} | {pct:.2f} | {conviction_level(pct)} | {heat_bar(pct)} |")
    lines.append("")

    # 重叠分析
    lines.append("## 六、同业重叠分析")
    lines.append("")
    if overlap_data:
        lines.append("| 同业基金 | 共同持仓数 | 共同持仓代码 |")
        lines.append("|----------|------------|--------------|")
        for item in overlap_data:
            lines.append(f"| {item['基金']} | {item['共同持仓数']} | {item['共同持仓']} |")
    else:
        lines.append("未提供同业基金代码")
    lines.append("")

    # 季度环比变化
    lines.append("## 七、季度环比变化总结")
    lines.append("")
    lines.append(f"- 新建仓位：{len(new_positions)} 只")
    lines.append(f"- 增持仓位：{len(increased)} 只")
    lines.append(f"- 减持仓位：{len(decreased)} 只")
    lines.append(f"- 清仓仓位：{len(exited)} 只")
    lines.append(f"- 前十大合计占净值比：{top10_total:.2f}%（上期 {prev_df['占净值比'].sum():.2f}%）")
    lines.append(f"- 持仓集中度 HHI：{hhi:.0f}")
    lines.append("")

    # 3 个最值得关注的动作
    lines.append("## 八、3 个最值得关注的动作")
    lines.append("")
    lines.append("| 优先级 | 动作 | 标的 | 信号强度 | 解读 |")
    lines.append("|--------|------|------|----------|------|")

    # 选择信号强度最高的 3 个动作
    signal_rows = []
    for _, row in analysis.iterrows():
        if row["动作"] == "持平":
            continue
        rank = 0
        if row["代码"] in curr_df["代码"].values:
            rank = curr_df[curr_df["代码"] == row["代码"]].index[0] + 1
        strength = signal_strength(row["变动pp"], row["动作"] == "新建", rank)
        signal_rows.append((row, strength, rank))

    # 排序：高 > 中 > 低，然后按变动绝对值
    strength_order = {"高": 0, "中": 1, "低": 2}
    signal_rows.sort(key=lambda x: (strength_order[x[1]], -abs(x[0]["变动pp"])))

    for i, (row, strength, rank) in enumerate(signal_rows[:3], 1):
        action_desc = {
            "新建": f"新建 {row['名称']}({row['代码']})",
            "增持": f"增持 {row['名称']}({row['代码']}) {row['变动pp']:+.2f}pp",
            "减持": f"减持 {row['名称']}({row['代码']}) {row['变动pp']:+.2f}pp",
            "清仓": f"清仓 {row['名称']}({row['代码']})",
        }[row["动作"]]
        lines.append(f"| {i} | {action_desc} | {row['代码']} | {strength} | 本季度核心调仓信号 |")
    lines.append("")

    # 风险提示
    lines.append("## 九、风险提示")
    lines.append("")
    lines.append("- 季报披露存在滞后性，通常为季度结束后 15 个工作日")
    lines.append("- 本报告仅基于前十大重仓股，无法反映完整持仓")
    lines.append("- 基金经理可能在季报披露后继续调仓")
    lines.append("- 聪明钱信号仅为逆向分析线索，不构成投资建议")
    lines.append("")

    # 写入文件
    output_path = Path(output_dir) / f"备案追踪_{fund_code}_{quarter}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"报告已生成：{output_path}")


def main():
    args = parse_args()
    quarter = args.quarter
    if not quarter:
        # 默认最新季度：取当前年份和季度
        now = datetime.now()
        qn = (now.month - 1) // 3 + 1
        quarter = f"{now.year}Q{qn}"
    else:
        quarter = validate_quarter(args.quarter)

    peers = [p.strip() for p in args.peers.split(",")] if args.peers else []
    generate_report(args.fund_code, quarter, args.output_dir, peers)


if __name__ == "__main__":
    main()
