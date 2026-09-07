#!/usr/bin/env python3
"""
基金筛选器脚本
用法：
    python fund_screener.py <基金代码1,代码2,...> [--benchmark 000300.SH] [--output-dir .] [--risk-free 0.025]
示例：
    python fund_screener.py 519702,163406,001938 --benchmark 000300.SH --output-dir ./output
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak
import numpy as np
import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(description="基金筛选器")
    parser.add_argument("fund_codes", help="基金代码，逗号分隔，如 519702,163406")
    parser.add_argument("--benchmark", default="000300.SH", help="基准指数代码，默认 000300.SH")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    parser.add_argument("--risk-free", type=float, default=0.025, help="无风险利率，默认 2.5%%")
    return parser.parse_args()


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
        print(f"获取基金信息失败 {fund_code}: {e}")
        return {"基金代码": fund_code, "基金简称": "未知", "基金类型": "未知"}


def get_fund_nav(fund_code: str) -> pd.DataFrame:
    """获取基金历史净值"""
    try:
        df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
        df = df.rename(columns={"净值日期": "date", "单位净值": "nav"})
        df["date"] = pd.to_datetime(df["date"])
        df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
        df = df.dropna(subset=["nav"]).sort_values("date").reset_index(drop=True)
        df["daily_return"] = df["nav"].pct_change()
        return df
    except Exception as e:
        print(f"获取基金净值失败 {fund_code}: {e}")
        return pd.DataFrame()


def get_index_data(index_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取指数历史数据"""
    try:
        # 去除 .SH/.SZ 后缀
        symbol = index_code.split(".")[0]
        df = ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date)
        df = df.rename(columns={"日期": "date", "收盘": "close"})
        df["date"] = pd.to_datetime(df["date"])
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
        df["daily_return"] = df["close"].pct_change()
        return df
    except Exception as e:
        print(f"获取指数数据失败 {index_code}: {e}")
        return pd.DataFrame()


def annualized_return(returns: pd.Series, periods_per_year: int = 252) -> float:
    """年化收益率"""
    if returns.empty or returns.isna().all():
        return np.nan
    total = (1 + returns).prod()
    n = len(returns.dropna())
    return total ** (periods_per_year / n) - 1


def annualized_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    """年化波动率"""
    return returns.dropna().std() * np.sqrt(periods_per_year)


def downside_deviation(returns: pd.Series, periods_per_year: int = 252) -> float:
    """下行标准差"""
    downside = returns[returns < 0].dropna()
    if downside.empty:
        return 0.0
    return downside.std() * np.sqrt(periods_per_year)


def max_drawdown(nav: pd.Series) -> float:
    """最大回撤"""
    cummax = nav.cummax()
    drawdown = (nav - cummax) / cummax
    return drawdown.min()


def max_drawdown_recovery_days(nav: pd.Series) -> int:
    """最大回撤恢复天数（简化：从最低点到创新高所需交易日）"""
    cummax = nav.cummax()
    drawdown = (nav - cummax) / cummax
    max_dd_idx = drawdown.idxmin()
    post_low = nav.loc[max_dd_idx:]
    recovery = post_low[post_low >= cummax.loc[max_dd_idx]]
    if recovery.empty:
        return len(nav) - max_dd_idx
    recovery_idx = recovery.index[0]
    return recovery_idx - max_dd_idx


def sharpe_ratio(ann_ret: float, ann_vol: float, rf: float) -> float:
    if ann_vol == 0 or np.isnan(ann_vol):
        return np.nan
    return (ann_ret - rf) / ann_vol


def sortino_ratio(ann_ret: float, downside_std: float, rf: float) -> float:
    if downside_std == 0 or np.isnan(downside_std):
        return np.nan
    return (ann_ret - rf) / downside_std


def calmar_ratio(ann_ret: float, max_dd: float) -> float:
    if max_dd == 0 or np.isnan(max_dd):
        return np.nan
    return ann_ret / abs(max_dd)


def capm_alpha_beta(fund_rets: pd.Series, bench_rets: pd.Series) -> tuple:
    """计算 CAPM alpha 和 beta"""
    aligned = pd.concat([fund_rets, bench_rets], axis=1).dropna()
    if aligned.empty or len(aligned) < 30:
        return np.nan, np.nan
    X = aligned.iloc[:, 1].values
    y = aligned.iloc[:, 0].values
    beta = np.cov(y, X)[0, 1] / np.var(X) if np.var(X) > 0 else np.nan
    alpha = y.mean() - beta * X.mean()
    return alpha * 252, beta


def information_ratio(fund_rets: pd.Series, bench_rets: pd.Series) -> float:
    """信息比率"""
    diff = (fund_rets - bench_rets).dropna()
    if diff.empty or diff.std() == 0:
        return np.nan
    return diff.mean() * 252 / (diff.std() * np.sqrt(252))


def rolling_correlation(fund_rets: pd.Series, other_rets: pd.Series, window: int = 252) -> float:
    """滚动相关性（最近 window 个交易日）"""
    aligned = pd.concat([fund_rets, other_rets], axis=1).dropna()
    if len(aligned) < window:
        return aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
    return aligned.iloc[-window:, 0].corr(aligned.iloc[-window:, 1])


def get_period_returns(nav_df: pd.DataFrame) -> dict:
    """计算各周期收益"""
    nav_df = nav_df.copy()
    nav_df = nav_df.set_index("date").sort_index()
    latest = nav_df.index[-1]

    def period_return(days: int):
        start = latest - timedelta(days=days)
        subset = nav_df[nav_df.index >= start]
        if len(subset) < 2:
            return np.nan
        return subset["nav"].iloc[-1] / subset["nav"].iloc[0] - 1

    return {
        "1年": period_return(365),
        "3年": (1 + period_return(365 * 3)) ** (1 / 3) - 1 if not np.isnan(period_return(365 * 3)) else np.nan,
        "5年": (1 + period_return(365 * 5)) ** (1 / 5) - 1 if not np.isnan(period_return(365 * 5)) else np.nan,
    }


def analyze_fund(fund_code: str, benchmark_rets: pd.Series, rf: float) -> dict:
    """分析单只基金"""
    info = get_fund_info(fund_code)
    nav_df = get_fund_nav(fund_code)
    if nav_df.empty:
        return {"基金代码": fund_code, "基金简称": info["基金简称"], "错误": "无法获取净值"}

    nav_df = nav_df.sort_values("date").reset_index(drop=True)
    rets = nav_df["daily_return"].dropna()
    nav = nav_df["nav"]

    ann_ret = annualized_return(rets)
    ann_vol = annualized_volatility(rets)
    dd_std = downside_deviation(rets)
    mdd = max_drawdown(nav)
    recovery = max_drawdown_recovery_days(nav)

    sharpe = sharpe_ratio(ann_ret, ann_vol, rf)
    sortino = sortino_ratio(ann_ret, dd_std, rf)
    calmar = calmar_ratio(ann_ret, mdd)

    alpha, beta = capm_alpha_beta(rets, benchmark_rets)
    ir = information_ratio(rets, benchmark_rets)
    corr = rolling_correlation(rets, benchmark_rets)

    period_rets = get_period_returns(nav_df)

    return {
        "基金代码": fund_code,
        "基金简称": info["基金简称"],
        "基金类型": info["基金类型"],
        "年化回报": ann_ret,
        "年化波动率": ann_vol,
        "最大回撤": mdd,
        "回撤恢复天数": recovery,
        "夏普": sharpe,
        "索提诺": sortino,
        "卡玛": calmar,
        "Alpha": alpha,
        "Beta": beta,
        "信息比率": ir,
        "与基准相关性": corr,
        "1年收益": period_rets["1年"],
        "3年年化": period_rets["3年"],
        "5年年化": period_rets["5年"],
    }


def generate_report(fund_codes: list, benchmark_code: str, output_dir: str, rf: float):
    """生成基金筛选报告"""
    # 获取基准数据
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=365 * 10)).strftime("%Y%m%d")
    bench_df = get_index_data(benchmark_code, start_date, end_date)
    if bench_df.empty:
        print(f"基准 {benchmark_code} 数据获取失败，将跳过 Alpha/Beta/相关性计算")
        benchmark_rets = pd.Series(dtype=float)
    else:
        bench_df = bench_df.sort_values("date").reset_index(drop=True)
        benchmark_rets = bench_df.set_index("date")["daily_return"]

    # 分析每只基金
    results = []
    for code in fund_codes:
        result = analyze_fund(code, benchmark_rets, rf)
        results.append(result)

    df = pd.DataFrame(results)

    # 生成 Markdown
    lines = []
    lines.append(f"# 基金筛选报告：{', '.join(fund_codes)}")
    lines.append("")
    lines.append("## 一、执行摘要")
    lines.append("")
    lines.append(f"- **入选基金**：{', '.join(fund_codes)}")
    lines.append(f"- **基准指数**：{benchmark_code}")
    lines.append(f"- **无风险利率**：{rf * 100:.2f}%")
    lines.append(f"- **报告生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("### 数据声明")
    lines.append("- 数据来源：AKShare / 天天基金网 / 公开市场数据")
    lines.append("- 计算窗口为基金成立以来的全部净值数据；1/3/5 年收益为滚动窗口")
    lines.append("- 历史业绩不代表未来表现")
    lines.append("")

    # 基础信息表
    lines.append("## 二、基金基础信息")
    lines.append("")
    lines.append("| 基金代码 | 基金简称 | 基金类型 |")
    lines.append("|----------|----------|----------|")
    for _, row in df.iterrows():
        lines.append(f"| {row['基金代码']} | {row['基金简称']} | {row.get('基金类型', '待补')} |")
    lines.append("")

    # 业绩对比
    lines.append("## 三、业绩对比")
    lines.append("")
    def fmt_pct(x):
        return f"{x * 100:.2f}" if pd.notna(x) else "待补"

    def fmt_num(x):
        return f"{x:.2f}" if pd.notna(x) else "待补"

    def fmt_int(x):
        return f"{int(x)}" if pd.notna(x) else "待补"

    lines.append("| 基金 | 1年收益(%) | 3年年化(%) | 5年年化(%) | 年化回报(%) |")
    lines.append("|------|------------|------------|------------|-------------|")
    for _, row in df.iterrows():
        lines.append(
            f"| {row['基金简称']} | {fmt_pct(row['1年收益'])} | "
            f"{fmt_pct(row['3年年化'])} | "
            f"{fmt_pct(row['5年年化'])} | "
            f"{fmt_pct(row['年化回报'])} |"
        )
    lines.append("")

    # 风险调整后回报
    lines.append("## 四、风险调整后回报")
    lines.append("")
    lines.append("| 基金 | 夏普 | 索提诺 | 卡玛 | 年化波动率(%) | 最大回撤(%) | 恢复天数 |")
    lines.append("|------|------|--------|------|---------------|-------------|----------|")
    for _, row in df.iterrows():
        lines.append(
            f"| {row['基金简称']} | {fmt_num(row['夏普'])} | "
            f"{fmt_num(row['索提诺'])} | "
            f"{fmt_num(row['卡玛'])} | "
            f"{fmt_pct(row['年化波动率'])} | "
            f"{fmt_pct(row['最大回撤'])} | "
            f"{fmt_int(row['回撤恢复天数'])} |"
        )
    lines.append("")

    # Alpha 与相关性
    lines.append("## 五、Alpha 与相关性")
    lines.append("")
    lines.append("| 基金 | Alpha(%) | Beta | 信息比率 | 与基准相关性 |")
    lines.append("|------|----------|------|----------|--------------|")
    for _, row in df.iterrows():
        lines.append(
            f"| {row['基金简称']} | {fmt_pct(row['Alpha'])} | "
            f"{fmt_num(row['Beta'])} | "
            f"{fmt_num(row['信息比率'])} | "
            f"{fmt_num(row['与基准相关性'])} |"
        )
    lines.append("")

    # 风险仪表盘（综合评分）
    lines.append("## 六、风险仪表盘")
    lines.append("")
    lines.append("| 基金 | 收益 | 风险调整 | 回撤控制 | 稳定性 | 综合 |")
    lines.append("|------|------|----------|----------|--------|------|")
    def score_return(x):
        if pd.isna(x):
            return "待补"
        y = x * 100
        if y >= 30:
            return 5
        if y >= 15:
            return 4
        if y >= 5:
            return 3
        if y >= 0:
            return 2
        return 1

    def score_sharpe(x):
        if pd.isna(x):
            return "待补"
        if x >= 1.5:
            return 5
        if x >= 1.0:
            return 4
        if x >= 0.5:
            return 3
        if x >= 0:
            return 2
        return 1

    def score_drawdown(x):
        if pd.isna(x):
            return "待补"
        dd = x * 100
        if dd >= -10:
            return 5
        if dd >= -20:
            return 4
        if dd >= -30:
            return 3
        if dd >= -40:
            return 2
        return 1

    def score_ir(x):
        if pd.isna(x):
            return "待补"
        if x >= 1.0:
            return 5
        if x >= 0.5:
            return 4
        if x >= 0:
            return 3
        if x >= -0.5:
            return 2
        return 1

    for _, row in df.iterrows():
        s_ret = score_return(row["1年收益"])
        s_sharpe = score_sharpe(row["夏普"])
        s_dd = score_drawdown(row["最大回撤"])
        s_ir = score_ir(row["信息比率"])
        if all(isinstance(x, (int, float)) for x in [s_ret, s_sharpe, s_dd, s_ir]):
            avg = np.mean([s_ret, s_sharpe, s_dd, s_ir])
            avg_str = f"{avg:.1f}"
        else:
            avg_str = "待补"
        lines.append(
            f"| {row['基金简称']} | {s_ret} | {s_sharpe} | {s_dd} | {s_ir} | {avg_str} |"
        )
    lines.append("")

    # 配置建议
    lines.append("## 七、配置建议")
    lines.append("")
    lines.append("基于定量指标给出以下分类：")
    lines.append("")
    lines.append("| 基金 | 建议 | 理由 |")
    lines.append("|------|------|------|")
    for _, row in df.iterrows():
        if pd.isna(row["夏普"]) or pd.isna(row["最大回撤"]):
            suggestion = "待补充数据后评估"
        elif row["夏普"] > 1.0 and row["最大回撤"] > -0.20:
            suggestion = "核心配置"
        elif row["夏普"] > 0.5:
            suggestion = "卫星配置"
        else:
            suggestion = "回避或低配"
        reason = f"夏普 {row['夏普']:.2f}，最大回撤 {row['最大回撤'] * 100:.1f}%"
        lines.append(f"| {row['基金简称']} | {suggestion} | {reason} |")
    lines.append("")

    # 风险提示
    lines.append("## 八、风险提示")
    lines.append("")
    lines.append("- 历史业绩不代表未来表现")
    lines.append("- 定量筛选需结合定性尽调与管理人研究")
    lines.append("- 费率数据未完全纳入，实际净回报可能低于费前回报")
    lines.append("- 关键人风险、风格漂移等定性风险需持续跟踪")
    lines.append("")

    output_path = Path(output_dir) / f"基金筛选_{'_'.join(fund_codes)}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"报告已生成：{output_path}")


def main():
    args = parse_args()
    fund_codes = [c.strip() for c in args.fund_codes.split(",") if c.strip()]
    if len(fund_codes) < 2:
        print("请至少提供 2 只基金代码")
        sys.exit(1)
    generate_report(fund_codes, args.benchmark, args.output_dir, args.risk_free)


if __name__ == "__main__":
    main()
