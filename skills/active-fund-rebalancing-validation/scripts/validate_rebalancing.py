#!/usr/bin/env python3
"""
主动管理基金调仓有效性验证脚本
用法: python validate_rebalancing.py <基金代码> [options]

示例:
    python validate_rebalancing.py 519702
    python validate_rebalancing.py 519702 --peers 519700,519001,000001 --quarters 8 --output ~/reports/
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import re
from bs4 import BeautifulSoup
from io import StringIO

# 尝试导入 AKShare，未安装则给出提示
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False


# ── 常量 ──
DEFAULT_QUARTERS = 8
EASTMONEY_FUND_INFO_API = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
EASTMONEY_JJCC_API = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
# 在某些网络环境下需要显式禁用代理，避免被系统代理拦截
PROXIES = {"http": None, "https": None}

SECTOR_MAP = {
    "化工": "周期", "有色金属": "周期", "钢铁": "周期", "煤炭": "周期", "建筑材料": "周期",
    "电力": "防御", "公用事业": "防御", "银行": "防御", "交通运输": "防御",
    "医药生物": "成长", "电力设备": "成长", "新能源": "成长", "电子": "成长",
    "计算机": "成长", "传媒": "成长", "通信": "成长", "半导体": "成长",
    "食品饮料": "消费", "家用电器": "消费", "农林牧渔": "消费", "商贸零售": "消费",
    "汽车": "制造", "机械设备": "制造", "国防军工": "制造", "建筑装饰": "制造",
    "非银金融": "金融", "房地产": "金融",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="主动管理基金调仓有效性验证",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 validate_rebalancing.py 519702
  python3 validate_rebalancing.py 519702 --peers 519700,519001 --quarters 8 --output ~/reports
        """
    )
    parser.add_argument("fund_code", help="基金代码，如 519702")
    parser.add_argument("--peers", default="", help="对比基金代码，逗号分隔，如 519700,519001")
    parser.add_argument("--quarters", type=int, default=DEFAULT_QUARTERS,
                        help=f"分析季度数，默认 {DEFAULT_QUARTERS}")
    parser.add_argument("--output", default=".", help="输出目录，默认当前目录")
    parser.add_argument("--benchmark", default="000300", help="业绩基准指数代码，默认沪深300")
    parser.add_argument("--no-pdf", action="store_true", help="不自动生成 PDF")
    return parser.parse_args()


def get_report_dates(end_date: Optional[str] = None, n: int = DEFAULT_QUARTERS) -> List[str]:
    """生成过去 N 个季度的报告期字符串（YYYYMMDD格式）"""
    if end_date is None:
        now = datetime.now()
    else:
        now = datetime.strptime(end_date, "%Y%m%d")

    # 取上一个完整季度末
    month = now.month
    if month <= 3:
        year, q_end_month = now.year - 1, 12
    elif month <= 6:
        year, q_end_month = now.year, 3
    elif month <= 9:
        year, q_end_month = now.year, 6
    else:
        year, q_end_month = now.year, 9

    dates = []
    for i in range(n):
        y = year
        m = q_end_month - i * 3
        while m <= 0:
            y -= 1
            m += 12
        dates.append(f"{y}{m:02d}31" if m in [3, 12] else f"{y}{m:02d}30")
    return dates[::-1]


def fetch_json(url: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """通用 HTTP GET 请求，返回 JSON"""
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, params=params, headers=headers, proxies=PROXIES, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[WARN] 请求失败 {url}: {e}")
        return None


def get_fund_info_em(fund_code: str) -> Dict:
    """从天天基金网获取基金基本信息（名称、类型、基金经理、基金公司）"""
    info = {"code": fund_code, "name": fund_code, "manager": "", "type": ""}

    # 方案 1：从移动端 API 获取完整信息
    try:
        url = "https://fundmobapi.eastmoney.com/FundMApi/FundBaseTypeInformation.ashx"
        params = {
            "FCODE": fund_code,
            "deviceid": "Wap",
            "plat": "Wap",
            "product": "EFund",
            "version": "2.0.0",
        }
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, params=params, headers=headers, proxies=PROXIES, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "Datas" in data and data["Datas"]:
            d = data["Datas"]
            info["name"] = d.get("SHORTNAME", info["name"])
            info["type"] = d.get("FTYPE", "")
            info["manager"] = d.get("JJJL", "")
            info["company"] = d.get("JJGS", "")
            info["establish_date"] = d.get("PLTDATE", "")
            return info
    except Exception as e:
        print(f"[WARN] 从移动端 API 获取基金 {fund_code} 信息失败: {e}")

    # 方案 2：从持仓页面解析基金名称（兜底）
    try:
        url = f"https://fundf10.eastmoney.com/ccmx_{fund_code}.html"
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://fundf10.eastmoney.com/",
        }
        resp = requests.get(url, headers=headers, proxies=PROXIES, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            if "(" in title:
                info["name"] = title.split("(")[0].strip()
    except Exception as e:
        print(f"[WARN] 获取基金 {fund_code} 基本信息失败: {e}")
    return info


def parse_eastmoney_jjcc_response(text: str, target_year_month: str) -> pd.DataFrame:
    """
    解析东方财富基金持仓接口返回的 var apidata={ content:"..." } 内容
    target_year_month: "2024年4季度" 这种格式
    """
    text = text.strip()
    # 提取 content 字段的 HTML
    match = re.search(r'content:\s*"(.*?)"\s*,\s*info', text, re.DOTALL)
    if not match:
        match = re.search(r'content:\s*"(.*?)"\s*,\s*arryear', text, re.DOTALL)
    if not match:
        match = re.search(r'content:\s*"(.*?)"\s*}\s*$', text, re.DOTALL)
    if not match:
        return pd.DataFrame()

    # 反转义
    html = match.group(1).replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')
    soup = BeautifulSoup(html, "html.parser")

    # 找到所有季度标题和对应表格
    h4_tags = soup.find_all("h4", class_="t")
    tables = soup.find_all("table")

    if len(h4_tags) != len(tables):
        # 兜底：尝试用 pandas 解析所有表格
        pass

    for h4, table in zip(h4_tags, tables):
        label = h4.get_text(strip=True)
        if target_year_month in label:
            # 用 pandas 解析这个 table
            try:
                dfs = pd.read_html(StringIO(str(table)))
                if dfs:
                    df = dfs[0]
                    # 标准化列名
                    df = standardize_holdings_columns(df)
                    return df
            except Exception:
                continue

    # 如果没匹配到，返回第一个表格兜底
    if tables:
        try:
            dfs = pd.read_html(StringIO(str(tables[0])))
            if dfs:
                return standardize_holdings_columns(dfs[0])
        except Exception:
            pass
    return pd.DataFrame()


def standardize_holdings_columns(df: pd.DataFrame) -> pd.DataFrame:
    """标准化持仓表格列名为统一格式"""
    if df.empty:
        return df

    col_map = {}
    for col in df.columns:
        col_str = str(col).strip()
        if "代码" in col_str:
            col_map[col] = "股票代码"
        elif "名称" in col_str:
            col_map[col] = "股票名称"
        elif "占净值" in col_str or "净值比例" in col_str:
            col_map[col] = "占净值比"
        elif "持股数" in col_str:
            col_map[col] = "持股数"
        elif "持仓市值" in col_str:
            col_map[col] = "持仓市值"
        elif "序号" in col_str:
            col_map[col] = "序号"
        else:
            col_map[col] = col_str

    df = df.rename(columns=col_map)

    # 确保必要列存在
    for c in ["股票代码", "股票名称", "占净值比"]:
        if c not in df.columns:
            df[c] = None

    # 转换数据类型
    if "占净值比" in df.columns:
        df["占净值比"] = df["占净值比"].apply(lambda x: to_float(str(x).replace("%", "")))
    if "持股数" in df.columns:
        df["持股数_万股"] = df["持股数"].apply(lambda x: to_float(str(x).replace(",", "")))
    if "持仓市值" in df.columns:
        df["持仓市值_万元"] = df["持仓市值"].apply(lambda x: to_float(str(x).replace(",", "")))

    # 过滤掉空行和表头重复行
    df = df[df["股票代码"].notna()]
    df = df[df["股票代码"] != "股票代码"]
    # 股票代码统一为字符串并补齐 6 位
    df["股票代码"] = df["股票代码"].apply(lambda x: str(int(x)).zfill(6) if pd.notna(x) else "")
    return df


def get_fund_holdings_em(fund_code: str, report_date: str) -> pd.DataFrame:
    """
    从天天基金网获取某基金某报告期的十大重仓股
    report_date: YYYYMMDD 格式
    返回 DataFrame: 股票代码, 股票名称, 持股数_万股, 持仓市值_万元, 占净值比(%)
    """
    url = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
    year = report_date[:4]
    month = int(report_date[4:6])
    quarter_num = (month - 1) // 3 + 1
    target_label = f"{year}年{quarter_num}季度"
    params = {
        "type": "jjcc",
        "code": fund_code,
        "topline": "10",
        "year": year,
        "month": "",
        "rt": "0.5",
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": f"https://fundf10.eastmoney.com/ccmx_{fund_code}.html",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, proxies=PROXIES, timeout=30)
        resp.raise_for_status()
        df = parse_eastmoney_jjcc_response(resp.text, target_label)
        return df
    except Exception as e:
        print(f"[WARN] 获取基金 {fund_code} {report_date}({target_label}) 持仓失败: {e}")
        return pd.DataFrame()


def to_float(val) -> Optional[float]:
    """安全转换为浮点数"""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).replace(",", "").replace("%", "").strip()
    try:
        return float(val)
    except ValueError:
        return None


# K 线数据缓存，避免重复请求
_KLINE_CACHE: Dict[str, pd.DataFrame] = {}


def get_tencent_kline(stock_code: str, start_date: str, end_date: str,
                      is_index: bool = False) -> Optional[pd.DataFrame]:
    """
    从腾讯财经获取前复权 K 线数据
    start_date/end_date: YYYYMMDD 格式
    返回 DataFrame（含日期、开盘、收盘、最高、最低、成交量）
    """
    code = stock_code.strip().zfill(6)

    # 确定市场前缀
    if is_index:
        if code.startswith("000") or code.startswith("399") or code == "000300" or code == "000905":
            prefix = "sh" if code.startswith("0") else "sz"
        else:
            prefix = "sh"
    else:
        if code.startswith("6") or code.startswith("5") or code.startswith("68"):
            prefix = "sh"
        else:
            prefix = "sz"

    symbol = f"{prefix}{code}"
    cache_key = f"{symbol}_{start_date}_{end_date}"
    if cache_key in _KLINE_CACHE:
        return _KLINE_CACHE[cache_key]

    # 腾讯接口使用 YYYY-MM-DD
    start_fmt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    end_fmt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        "param": f"{symbol},day,{start_fmt},{end_fmt},640,qfq",
    }
    headers = {"User-Agent": USER_AGENT}

    # 重试 3 次，间隔递增
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=headers, proxies=PROXIES, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            klines = data.get("data", {}).get(symbol, {}).get("qfqday", [])
            if not klines:
                # 尝试不复权
                klines = data.get("data", {}).get(symbol, {}).get("day", [])
            if not klines:
                return None

            rows = []
            for k in klines:
                if len(k) >= 5:
                    rows.append({
                        "日期": k[0],
                        "开盘": float(k[1]),
                        "收盘": float(k[2]),
                        "最低": float(k[3]),
                        "最高": float(k[4]),
                        "成交量": float(k[5]) if len(k) > 5 else None,
                    })
            df = pd.DataFrame(rows)
            _KLINE_CACHE[cache_key] = df
            return df
        except Exception as e:
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
            else:
                print(f"[WARN] 获取 K 线 {symbol} 失败: {e}")
                return None


def get_stock_returns_em(stock_code: str, start_date: str, end_date: str) -> Optional[float]:
    """获取个股区间涨跌幅"""
    df = get_tencent_kline(stock_code, start_date, end_date, is_index=False)
    if df is None or df.empty:
        return None
    return (df["收盘"].iloc[-1] / df["收盘"].iloc[0] - 1) * 100


def get_index_returns_em(index_code: str, start_date: str, end_date: str) -> Optional[float]:
    """获取指数区间涨跌幅"""
    df = get_tencent_kline(index_code, start_date, end_date, is_index=True)
    if df is None or df.empty:
        return None
    return (df["收盘"].iloc[-1] / df["收盘"].iloc[0] - 1) * 100


def add_months(date_str: str, months: int) -> str:
    """给 YYYYMMDD 格式的日期增加月份"""
    d = datetime.strptime(date_str, "%Y%m%d")
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, [31, 29 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return f"{year}{month:02d}{day:02d}"


def format_date(date_str: str) -> str:
    """YYYYMMDD -> YYYY-MM-DD"""
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"


# ── 分析函数 ──

def analyze_holdings_evolution(holdings_dict: Dict[str, pd.DataFrame], benchmark_code: str = "000300") -> Dict:
    """
    分析多季度持仓演变
    holdings_dict: {report_date: DataFrame}
    返回核心持仓、调仓节奏、行业配置等
    """
    dates = sorted(holdings_dict.keys())
    if not dates:
        return {}

    # 构建股票 × 季度 矩阵
    all_stocks = set()
    for df in holdings_dict.values():
        all_stocks.update(df["股票代码"].tolist())

    matrix = []
    for stock in sorted(all_stocks):
        row = {"股票代码": stock, "股票名称": ""}
        quarters_held = 0
        for d in dates:
            df = holdings_dict[d]
            match = df[df["股票代码"] == stock]
            if not match.empty:
                ratio = match.iloc[0]["占净值比"]
                name = match.iloc[0]["股票名称"]
                row[d] = ratio if ratio is not None else 0
                row["股票名称"] = name if name else row["股票名称"]
                quarters_held += 1
            else:
                row[d] = 0
        row["持有季度数"] = quarters_held
        matrix.append(row)

    matrix_df = pd.DataFrame(matrix)

    # 核心持仓：持有 >=6 季度
    core_holdings = matrix_df[matrix_df["持有季度数"] >= 6].sort_values("持有季度数", ascending=False)

    # 每季度调仓节奏
    quarter_changes = []
    for i in range(1, len(dates)):
        prev_date = dates[i - 1]
        curr_date = dates[i]
        prev_stocks = set(str(s) for s in holdings_dict[prev_date]["股票代码"])
        curr_stocks = set(str(s) for s in holdings_dict[curr_date]["股票代码"])
        new_stocks = curr_stocks - prev_stocks
        exit_stocks = prev_stocks - curr_stocks
        quarter_changes.append({
            "报告期": curr_date,
            "新增": len(new_stocks),
            "退出": len(exit_stocks),
            "变动合计": len(new_stocks) + len(exit_stocks),
            "新增名单": ",".join(sorted(new_stocks)),
            "退出名单": ",".join(sorted(exit_stocks)),
        })

    # 行业配置演变
    sector_evolution = []
    for d in dates:
        df = holdings_dict[d]
        sector_weights = {}
        total_ratio = 0
        for _, row in df.iterrows():
            # 优先使用 AKShare 真实行业分类，失败时回退到名称关键词推断
            sector = get_stock_sector(str(row["股票代码"]), str(row["股票名称"]))
            ratio = row["占净值比"] or 0
            sector_weights[sector] = sector_weights.get(sector, 0) + ratio
            total_ratio += ratio
        sector_weights["其他"] = max(0, total_ratio - sum(sector_weights.values()))
        sector_evolution.append({"报告期": d, **sector_weights})

    # 行业轮动质量（基于真实持仓收益）
    sector_rotation_quality = calculate_sector_rotation_quality(holdings_dict, dates, benchmark_code)

    return {
        "matrix": matrix_df,
        "core_holdings": core_holdings,
        "quarter_changes": pd.DataFrame(quarter_changes),
        "sector_evolution": pd.DataFrame(sector_evolution),
        "sector_rotation_quality": sector_rotation_quality,
        "dates": dates,
    }


def analyze_peer_overlap(
    fund_code: str,
    holdings_dict: Dict[str, pd.DataFrame],
    peer_codes: List[str],
    dates: List[str],
) -> Dict:
    """
    获取对比基金持仓并计算重叠度。
    返回：{peer_holdings, overlap_by_date, consensus_positions, divergent_positions, summary}
    """
    result = {
        "peer_holdings": {},
        "overlap_by_date": [],
        "consensus_positions": [],
        "divergent_positions": [],
        "summary": {"avg_overlap_ratio": None, "max_overlap_peer": None, "max_overlap_ratio": None},
    }
    if not peer_codes or not dates:
        return result

    # 拉取每个对比基金的持仓
    peer_holdings: Dict[str, Dict[str, set]] = {}
    for peer in peer_codes:
        peer_holdings[peer] = {}
        for d in dates:
            df = get_fund_holdings_em(peer, d)
            if not df.empty:
                peer_holdings[peer][d] = set(str(s).zfill(6) for s in df["股票代码"].tolist())

    result["peer_holdings"] = peer_holdings

    # 计算每期重叠
    overlap_records = []
    consensus_records = []
    divergent_records = []
    all_overlap_ratios = []
    peer_overlap_ratios: Dict[str, List[float]] = {peer: [] for peer in peer_codes}

    for d in dates:
        target_df = holdings_dict.get(d)
        if target_df is None or target_df.empty:
            continue
        target_stocks = set(str(s).zfill(6) for s in target_df["股票代码"].tolist())
        if not target_stocks:
            continue

        # 所有对比基金在该期的共同持仓
        peer_union: set = set()
        peer_counts: Dict[str, int] = {}
        for peer in peer_codes:
            peer_set = peer_holdings.get(peer, {}).get(d, set())
            peer_union |= peer_set
            for s in peer_set:
                peer_counts[s] = peer_counts.get(s, 0) + 1

        overlap = target_stocks & peer_union
        overlap_ratio = len(overlap) / len(target_stocks) * 100
        all_overlap_ratios.append(overlap_ratio)

        # 每只对比基金与目标基金的重叠度
        for peer in peer_codes:
            peer_set = peer_holdings.get(peer, {}).get(d, set())
            if peer_set:
                peer_overlap = len(target_stocks & peer_set) / len(target_stocks) * 100
                peer_overlap_ratios[peer].append(peer_overlap)

        # 共识仓位（≥3 只基金共同重仓，含本基金）
        consensus = [s for s, c in peer_counts.items() if c >= 2 and s in target_stocks]
        # 分歧仓位（仅本基金重仓）
        divergent = [s for s in target_stocks if peer_counts.get(s, 0) == 0]

        overlap_records.append({
            "报告期": d,
            "本基金重仓数": len(target_stocks),
            "对比基金并集": len(peer_union),
            "重叠标的数": len(overlap),
            "重叠度": overlap_ratio,
            "共识仓位": ",".join(sorted(consensus)) if consensus else "无",
            "分歧仓位": ",".join(sorted(divergent)) if divergent else "无",
        })

        for s in consensus:
            name = target_df[target_df["股票代码"] == s]["股票名称"].values
            name = name[0] if len(name) else ""
            consensus_records.append({"报告期": d, "股票代码": s, "股票名称": name})

        for s in divergent:
            name = target_df[target_df["股票代码"] == s]["股票名称"].values
            name = name[0] if len(name) else ""
            divergent_records.append({"报告期": d, "股票代码": s, "股票名称": name})

    result["overlap_by_date"] = pd.DataFrame(overlap_records)
    result["consensus_positions"] = pd.DataFrame(consensus_records)
    result["divergent_positions"] = pd.DataFrame(divergent_records)

    if all_overlap_ratios:
        result["summary"]["avg_overlap_ratio"] = round(sum(all_overlap_ratios) / len(all_overlap_ratios), 2)

    # 与单只对比基金平均重叠度最高的
    best_peer, best_ratio = None, -1.0
    for peer, ratios in peer_overlap_ratios.items():
        if ratios:
            avg = sum(ratios) / len(ratios)
            if avg > best_ratio:
                best_peer, best_ratio = peer, avg
    if best_peer is not None:
        result["summary"]["max_overlap_peer"] = best_peer
        result["summary"]["max_overlap_ratio"] = round(best_ratio, 2)

    return result


# 行业分类缓存
_INDUSTRY_CACHE: Dict[str, Optional[str]] = {}


def get_stock_industry_akshare(stock_code: str) -> Optional[str]:
    """
    尝试从 AKShare 获取个股真实行业名称。
    失败或 AKShare 未安装时返回 None。
    """
    if not AKSHARE_AVAILABLE:
        return None
    code = str(stock_code).zfill(6)
    if code in _INDUSTRY_CACHE:
        return _INDUSTRY_CACHE[code]

    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=code)
        if df is None or df.empty:
            _INDUSTRY_CACHE[code] = None
            return None
        # 返回格式通常为 item/value 两列
        if "item" in df.columns and "value" in df.columns:
            industry_row = df[df["item"] == "行业"]
            if not industry_row.empty:
                industry = str(industry_row.iloc[0]["value"]).strip()
                _INDUSTRY_CACHE[code] = industry
                return industry
        # 兜底：尝试第二列包含"行业"字样的行
        for _, row in df.iterrows():
            text = " ".join(str(v) for v in row.values)
            if "行业" in text and len(text) < 50:
                parts = text.replace("行业", "").replace(":", "").replace("：", "").strip().split()
                if parts:
                    _INDUSTRY_CACHE[code] = parts[-1]
                    return parts[-1]
    except Exception:
        pass
    _INDUSTRY_CACHE[code] = None
    return None


_INDUSTRY_TO_SECTOR: Dict[str, str] = {
    # 金融
    "银行": "金融", "证券": "金融", "保险": "金融", "信托": "金融", "期货": "金融",
    "多元金融": "金融", "互联网金融": "金融", "金融": "金融", "租赁": "金融",
    # 消费
    "白酒": "消费", "饮料制造": "消费", "食品加工": "消费", "食品": "消费",
    "家电": "消费", "白色家电": "消费", "黑色家电": "消费", "小家电": "消费",
    "农业": "消费", "种植业": "消费", "养殖业": "消费", "渔业": "消费", "林业": "消费",
    "畜牧养殖": "消费", "农产品": "消费", "饲料": "消费", "兽药": "消费",
    "零售": "消费", "百货": "消费", "超市": "消费", "贸易": "消费", "电商": "消费",
    "酒店": "消费", "旅游": "消费", "餐饮": "消费", "景区": "消费",
    "纺织服装": "消费", "服装": "消费", "纺织": "消费", "家纺": "消费",
    "家具": "消费", "家居": "消费", "造纸": "消费", "包装": "消费",
    "美容护理": "消费", "化妆品": "消费", "医美": "消费",
    # 成长 - 医药/医疗
    "化学制药": "成长", "生物制品": "成长", "医疗器械": "成长", "医疗服务": "成长",
    "中药": "成长", "医药商业": "成长", "医药": "成长", "医疗": "成长",
    "疫苗": "成长", "创新药": "成长", "CXO": "成长", "CRO": "成长",
    # 成长 - 科技/TMT
    "半导体": "成长", "集成电路": "成长", "芯片": "成长", "电子": "成长",
    "软件": "成长", "计算机": "成长", "IT服务": "成长", "互联网": "成长",
    "传媒": "成长", "游戏": "成长", "广告": "成长", "影视": "成长",
    "通信": "成长", "通信设备": "成长", "5G": "成长", "光通信": "成长",
    # 成长 - 新能源/高端制造
    "电力设备": "成长", "新能源": "成长", "锂电池": "成长", "光伏": "成长",
    "储能": "成长", "风电": "成长", "核电": "成长", "电网": "成长",
    "电池": "成长", "电机": "成长", "专用设备": "成长", "通用设备": "成长",
    "自动化设备": "成长", "仪器仪表": "成长", "光学光电子": "成长",
    "航空装备": "成长", "航天装备": "成长", "军工": "成长", "船舶": "成长",
    "汽车": "成长", "汽车零部件": "成长", "乘用车": "成长", "商用车": "成长",
    "智能汽车": "成长", "新能源车": "成长",
    # 周期
    "有色金属": "周期", "稀土": "周期", "钢铁": "周期", "煤炭": "周期",
    "化工": "周期", "化学制品": "周期", "化学原料": "周期", "石化": "周期",
    "建筑材料": "周期", "水泥": "周期", "玻璃": "周期", "玻璃纤维": "周期",
    "石油": "周期", "天然气": "周期", "油服": "周期", "矿业": "周期",
    "造纸": "周期", "化纤": "周期", "塑料": "周期", "橡胶": "周期",
    "航运": "周期", "港口": "周期", "机场": "周期", "物流": "周期",
    "房地产开发": "周期", "房地产": "周期", "基建": "周期", "建筑": "周期",
    "建筑装饰": "周期", "工程机械": "周期", "船舶": "周期",
    # 防御
    "电力": "防御", "公用事业": "防御", "水务": "防御", "燃气": "防御",
    "供热": "防御", "环保": "防御", "高速公路": "防御", "铁路": "防御",
    "电信运营": "防御", "广播电视": "防御",
    # 制造（未被上面覆盖的制造业）
    "机械设备": "制造", "专用设备": "制造", "通用设备": "制造", "自动化": "制造",
    "国防军工": "制造", "汽车整车": "制造", "汽车零部件": "制造",
}


def classify_industry_to_sector(industry_name: Optional[str]) -> str:
    """将 AKShare 返回的细分行业映射到六大板块。"""
    if not industry_name:
        return "其他"
    industry_name = str(industry_name).strip()
    # 优先精确匹配
    if industry_name in _INDUSTRY_TO_SECTOR:
        return _INDUSTRY_TO_SECTOR[industry_name]
    # 模糊匹配
    for ind, sector in _INDUSTRY_TO_SECTOR.items():
        if ind in industry_name or industry_name in ind:
            return sector
    return "其他"


def get_stock_sector(stock_code: str, stock_name: str) -> str:
    """
    获取股票所属板块：优先 AKShare 真实行业，失败时回退到名称关键词推断。
    """
    industry = get_stock_industry_akshare(stock_code)
    if industry:
        sector = classify_industry_to_sector(industry)
        if sector != "其他":
            return sector
    return infer_sector(stock_name)


def infer_sector(stock_name: str) -> str:
    """
    基于股票名称关键词粗略推断板块（兜底方案）。
    注意：关键词存在歧义，准确行业分类应使用真实行业数据接口（如 AKShare）。
    """
    if not stock_name:
        return "其他"

    # 部分典型个股兜底映射（避免常见公司被误分类）
    known_mapping = {
        "宁德时代": "成长",
        "贵州茅台": "消费",
        "五粮液": "消费",
        "比亚迪": "制造",
        "隆基绿能": "成长",
        "通威股份": "成长",
        "立讯精密": "成长",
        "海康威视": "成长",
        "美的集团": "消费",
        "格力电器": "消费",
        "中国平安": "金融",
        "招商银行": "金融",
        "中信证券": "金融",
        "长江电力": "防御",
        "中国中免": "消费",
        "药明康德": "成长",
        "迈瑞医疗": "成长",
        "恒瑞医药": "成长",
        "金山办公": "成长",
        "科大讯飞": "成长",
        "中芯国际": "成长",
        "紫金矿业": "周期",
        "万华化学": "周期",
        "中国石油": "周期",
        "中国神华": "周期",
    }
    if stock_name in known_mapping:
        return known_mapping[stock_name]

    # 关键词映射：顺序靠前的优先级更高
    sector_keywords = {
        "金融": ["银行", "证券", "保险", "信托", "期货", "金融", "互金", "支付", "租赁", "AMC"],
        "消费": [
            "酒", "食品", "饮料", "家电", "农业", "牧", "消费", "百货", "零售", "超市",
            "酒店", "旅游", "餐饮", "免税", "医美", "美妆", "服饰", "服装", "纺织", "家具",
            "家居", "白电", "黑电", "小家电", "乳业", "调味", "零食", "养殖", "种植", "果业",
        ],
        "成长": [
            "医药", "药", "医疗", "生物", "疫苗", "器械", "医院", "诊断",
            "新能源", "锂电", "光伏", "储能", "氢能", "风电", "太阳能",
            "半导体", "芯片", "集成电路", "电子", "软件", "传媒", "通信", "5G",
            "科技", "计算机", "互联网", "信息", "网络", "数据", "云计算", "人工智能",
            "AI", "机器人", "无人机", "智能", "光学", "光电", "激光", "LED", "LCD",
            "军工", "航天", "航空", "卫星", "导弹", "防务",
        ],
        "周期": [
            "有色", "钢铁", "煤炭", "化工", "建材", "石油", "矿", "稀土", "锂", "钴", "镍",
            "铜", "铝", "锌", "铅", "黄金", "白银", "化纤", "塑料", "橡胶", "造纸",
            "航运", "港口", "机场", "基建", "建筑", "地产", "房地产开发", "水泥", "玻璃",
        ],
        "防御": [
            "电力", "高速", "铁路", "水务", "燃气", "供热", "环保", "公用", "港口",
            "公路", "桥梁", "隧道", "邮政", "电信运营", "广电", "核电",
        ],
        "制造": [
            "汽车", "机械", "航空", "船舶", "制造", "装备", "重工", "机床", "工具",
            "电气", "电器", "电机", "自动化", "仪器", "仪表", "零部件", "配件", "轮胎",
        ],
    }

    # 计算各板块命中关键词数量，命中最多者胜出
    scores = {}
    for sector, keywords in sector_keywords.items():
        scores[sector] = sum(1 for kw in keywords if kw in stock_name)

    if not scores or max(scores.values()) == 0:
        return "其他"

    return max(scores, key=scores.get)


def classify_rebalance_intensity(n_changes: int) -> str:
    if n_changes <= 1:
        return "微调"
    elif n_changes <= 3:
        return "调整"
    else:
        return "大调"


def calculate_effectiveness(holdings_dict: Dict[str, pd.DataFrame], dates: List[str],
                            benchmark_code: str) -> Dict:
    """
    计算调仓有效性指标
    """
    results = {
        "new_positions": [],
        "exit_positions": [],
        "sector_rotations": [],
        "summary": {},
    }

    benchmark_returns_cache = {}

    for i in range(1, len(dates)):
        prev_date = dates[i - 1]
        curr_date = dates[i]

        prev_df = holdings_dict[prev_date]
        curr_df = holdings_dict[curr_date]

        prev_stocks = set(prev_df["股票代码"])
        curr_stocks = set(curr_df["股票代码"])

        # 新增仓位
        new_stocks = curr_stocks - prev_stocks
        for code in new_stocks:
            row = curr_df[curr_df["股票代码"] == code].iloc[0]
            ret_3m = get_stock_returns_em(code, curr_date, add_months(curr_date, 3))
            bench_ret_3m = get_index_or_cache(benchmark_code, curr_date, add_months(curr_date, 3),
                                              benchmark_returns_cache)
            excess = None
            if ret_3m is not None and bench_ret_3m is not None:
                excess = ret_3m - bench_ret_3m
            results["new_positions"].append({
                "报告期": curr_date,
                "股票代码": code,
                "股票名称": row["股票名称"],
                "占净值比": row["占净值比"],
                "3个月收益": ret_3m,
                "基准3个月收益": bench_ret_3m,
                "超额收益": excess,
            })

        # 清仓仓位
        exit_stocks = prev_stocks - curr_stocks
        for code in exit_stocks:
            row = prev_df[prev_df["股票代码"] == code].iloc[0]
            ret_3m = get_stock_returns_em(code, curr_date, add_months(curr_date, 3))
            bench_ret_3m = get_index_or_cache(benchmark_code, curr_date, add_months(curr_date, 3),
                                              benchmark_returns_cache)
            excess = None
            if ret_3m is not None and bench_ret_3m is not None:
                excess = ret_3m - bench_ret_3m
            results["exit_positions"].append({
                "报告期": curr_date,
                "股票代码": code,
                "股票名称": row["股票名称"],
                "上期占净值比": row["占净值比"],
                "清仓后3个月收益": ret_3m,
                "基准3个月收益": bench_ret_3m,
                "相对收益": excess,
            })

    # 汇总统计
    new_df = pd.DataFrame(results["new_positions"])
    exit_df = pd.DataFrame(results["exit_positions"])

    summary = {}
    if not new_df.empty and "超额收益" in new_df.columns:
        valid = new_df["超额收益"].dropna()
        summary["new_positions_count"] = len(valid)
        summary["new_positions_avg_excess"] = valid.mean() if len(valid) > 0 else None
        summary["new_positions_win_rate"] = (valid > 0).mean() * 100 if len(valid) > 0 else None
    else:
        summary["new_positions_count"] = 0
        summary["new_positions_avg_excess"] = None
        summary["new_positions_win_rate"] = None

    if not exit_df.empty and "相对收益" in exit_df.columns:
        valid = exit_df["相对收益"].dropna()
        summary["exit_positions_count"] = len(valid)
        summary["exit_positions_avg_relative"] = valid.mean() if len(valid) > 0 else None
        summary["exit_positions_avoid_rate"] = (valid < 0).mean() * 100 if len(valid) > 0 else None
    else:
        summary["exit_positions_count"] = 0
        summary["exit_positions_avg_relative"] = None
        summary["exit_positions_avoid_rate"] = None

    results["summary"] = summary
    return results


def get_index_or_cache(index_code: str, start: str, end: str, cache: Dict) -> Optional[float]:
    key = f"{index_code}_{start}_{end}"
    if key not in cache:
        cache[key] = get_index_returns_em(index_code, start, end)
    return cache[key]


def calculate_sector_rotation_quality(
    holdings_dict: Dict[str, pd.DataFrame],
    dates: List[str],
    benchmark_code: str,
) -> Dict:
    """
    基于真实持仓数据计算行业轮动质量。
    逻辑：对每期行业配置变化 ≥3pp 的 sector，计算该 sector 持仓在后 3 个月的加权超额收益。
    """
    result = {"score": 10, "details": [], "switches": 0}
    if len(dates) < 2:
        return result

    sector_returns = []
    for i in range(1, len(dates)):
        prev_date = dates[i - 1]
        curr_date = dates[i]
        prev_df = holdings_dict.get(prev_date)
        curr_df = holdings_dict.get(curr_date)
        if prev_df is None or curr_df is None or prev_df.empty or curr_df.empty:
            continue

        # 计算各 sector 在两期的权重
        def _sector_weights(df: pd.DataFrame) -> Dict[str, float]:
            weights: Dict[str, float] = {}
            for _, row in df.iterrows():
                sector = get_stock_sector(str(row["股票代码"]), str(row["股票名称"]))
                weights[sector] = weights.get(sector, 0) + (row["占净值比"] or 0)
            return weights

        prev_weights = _sector_weights(prev_df)
        curr_weights = _sector_weights(curr_df)

        all_sectors = set(prev_weights.keys()) | set(curr_weights.keys())
        for sector in all_sectors:
            delta = curr_weights.get(sector, 0) - prev_weights.get(sector, 0)
            if delta >= 3:  # 显著增持
                result["switches"] += 1
                # 计算增持 sector 中持仓股票在后 3 个月的加权超额收益
                sector_stocks = curr_df[
                    curr_df.apply(
                        lambda r: get_stock_sector(str(r["股票代码"]), str(r["股票名称"])) == sector,
                        axis=1,
                    )
                ]
                if sector_stocks.empty:
                    continue
                total_weight = sector_stocks["占净值比"].sum()
                weighted_excess = 0
                valid_weight = 0
                end_date = add_months(curr_date, 3)
                bench_ret = get_index_returns_em(benchmark_code, curr_date, end_date)
                for _, row in sector_stocks.iterrows():
                    stock_ret = get_stock_returns_em(str(row["股票代码"]), curr_date, end_date)
                    if stock_ret is not None and bench_ret is not None:
                        excess = stock_ret - bench_ret
                        w = row["占净值比"] or 0
                        weighted_excess += excess * w
                        valid_weight += w
                if valid_weight > 0:
                    avg_excess = weighted_excess / valid_weight
                    sector_returns.append({
                        "报告期": curr_date,
                        "sector": sector,
                        "增持幅度": delta,
                        "加权超额": avg_excess,
                    })

    if not sector_returns:
        return result

    result["details"] = sector_returns
    avg_sector_excess = sum(r["加权超额"] for r in sector_returns) / len(sector_returns)

    # 得分映射：平均超额 >5% 得 16-20；0-5% 得 10-16；<0 得 5-10
    if avg_sector_excess > 5:
        result["score"] = min(20, 16 + (avg_sector_excess - 5) / 5 * 4)
    elif avg_sector_excess > 0:
        result["score"] = 10 + avg_sector_excess / 5 * 6
    else:
        result["score"] = max(5, 10 + avg_sector_excess)

    return result


def calculate_peer_uniqueness_score(
    peer_analysis: Dict,
    holdings_dict: Dict[str, pd.DataFrame],
    dates: List[str],
    benchmark_code: str,
) -> float:
    """
    基于分歧仓位（仅本基金重仓）的后 3 个月超额收益胜率计算同业独特性得分。
    """
    divergent_df = peer_analysis.get("divergent_positions", pd.DataFrame()) if peer_analysis else pd.DataFrame()
    if divergent_df.empty or not dates:
        return 6.0

    wins = 0
    total = 0
    for _, row in divergent_df.iterrows():
        code = str(row["股票代码"]).zfill(6)
        d = str(row["报告期"])
        if d not in holdings_dict:
            continue
        # 找到该股票在当期持仓中的占净值比
        stock_row = holdings_dict[d][holdings_dict[d]["股票代码"] == code]
        if stock_row.empty:
            continue
        end_date = add_months(d, 3)
        stock_ret = get_stock_returns_em(code, d, end_date)
        bench_ret = get_index_returns_em(benchmark_code, d, end_date)
        if stock_ret is not None and bench_ret is not None:
            total += 1
            if stock_ret > bench_ret:
                wins += 1

    if total == 0:
        return 6.0
    win_rate = wins / total
    # 胜率 >60% 得 8-10；40-60% 得 5-7；<40% 得 2-4
    if win_rate > 0.6:
        return min(10, 8 + (win_rate - 0.6) / 0.4 * 2)
    elif win_rate > 0.4:
        return 5 + (win_rate - 0.4) / 0.2 * 2
    else:
        return max(2, 2 + win_rate / 0.4 * 3)


def calculate_scores(
    analysis: Dict,
    effectiveness: Dict,
    peer_analysis: Dict = None,
    holdings_dict: Dict[str, pd.DataFrame] = None,
    benchmark_code: str = "000300",
) -> Dict:
    """
    计算调仓有效性综合评分（满分100）。
    每个维度得分已按权重折算为该维度对总分的实际贡献，直接相加即得总分。
    """
    scores = {
        "调仓时机": 0,
        "行业轮动": 0,
        "核心持仓": 0,
        "风险控制": 0,
        "换手效率": 0,
        "同业独特性": 0,
    }

    s = effectiveness.get("summary", {})

    # ── 调仓时机（权重25，得分范围0-25）：新增 + 清仓 ──
    avg_excess = s.get("new_positions_avg_excess")
    win_rate = s.get("new_positions_win_rate")
    if avg_excess is not None and win_rate is not None:
        # 新增仓位评分（0-18分）
        if avg_excess > 10:
            new_score = 18
        elif avg_excess > 5:
            new_score = 14 + (avg_excess - 5) / 5 * 4
        elif avg_excess > 2:
            new_score = 9 + (avg_excess - 2) / 3 * 5
        elif avg_excess > 0:
            new_score = 4 + avg_excess / 2 * 5
        else:
            new_score = 0
        # 胜率修正
        new_score = min(18, new_score * (0.4 + win_rate / 100 * 0.6))
        scores["调仓时机"] += new_score

    avg_exit = s.get("exit_positions_avg_relative")
    avoid_rate = s.get("exit_positions_avoid_rate")
    if avg_exit is not None and avoid_rate is not None:
        # 清仓仓位评分（0-7分）：卖出后跑输越多、规避比例越高，得分越高
        if avg_exit < -10:
            exit_score = 7
        elif avg_exit < -5:
            exit_score = 5.5
        elif avg_exit < -2:
            exit_score = 4
        elif avg_exit < 0:
            exit_score = 2.5
        elif avg_exit < 3:
            exit_score = 1
        else:
            exit_score = 0
        # 规避比例修正
        exit_score = min(7, exit_score * (0.3 + avoid_rate / 100 * 0.7))
        scores["调仓时机"] += exit_score

    # ── 核心持仓（权重20，得分范围0-20）：持有持续性 + 数量 ──
    core = analysis.get("core_holdings", pd.DataFrame())
    if not core.empty:
        max_held = core["持有季度数"].max()
        if max_held >= 6:
            scores["核心持仓"] += 14
        elif max_held >= 4:
            scores["核心持仓"] += 10
        elif max_held >= 2:
            scores["核心持仓"] += 5
        # 核心持仓数量加分
        n_core = len(core)
        scores["核心持仓"] += min(6, n_core * 2)

    # ── 风险控制（权重15，得分范围0-15）：前十大占比波动 + 集中度 ──
    matrix = analysis.get("matrix", pd.DataFrame())
    dates = analysis.get("dates", [])
    if not matrix.empty and len(dates) > 1:
        total_ratios = matrix[dates].sum(axis=0)
        volatility = total_ratios.std()
        if volatility < 2:
            scores["风险控制"] += 10
        elif volatility < 4:
            scores["风险控制"] += 8
        elif volatility < 6:
            scores["风险控制"] += 5
        elif volatility < 10:
            scores["风险控制"] += 2
        # 平均集中度：适度集中为佳
        avg_concentration = total_ratios.mean()
        if 40 <= avg_concentration <= 70:
            scores["风险控制"] += 5
        elif 30 <= avg_concentration <= 80:
            scores["风险控制"] += 3

    # ── 换手效率（权重10，得分范围0-10）：换手频率 + 新增胜率 ──
    changes = analysis.get("quarter_changes", pd.DataFrame())
    if not changes.empty:
        avg_changes = changes["变动合计"].mean()
        if win_rate is not None:
            if avg_changes < 3:
                base = 7
            elif avg_changes < 5:
                base = 6
            elif avg_changes < 7:
                base = 4
            else:
                base = 2
            # 胜率高则加分
            scores["换手效率"] = min(10, base + win_rate / 100 * 4)
        else:
            scores["换手效率"] = 5

    # ── 行业轮动（权重20，得分范围0-20）：优先使用基于真实持仓收益的质量评分 ──
    sector_rotation = analysis.get("sector_rotation_quality")
    if sector_rotation and sector_rotation.get("score") is not None:
        scores["行业轮动"] = sector_rotation["score"]
    elif not sector_evolution.empty and len(dates) > 2:
        sector_cols = [c for c in sector_evolution.columns if c != "报告期"]
        dominant_changes = 0
        for i in range(1, len(sector_evolution)):
            prev_dominant = max(sector_cols, key=lambda c: sector_evolution.iloc[i-1][c])
            curr_dominant = max(sector_cols, key=lambda c: sector_evolution.iloc[i][c])
            if prev_dominant != curr_dominant:
                dominant_changes += 1
        if dominant_changes == 0:
            scores["行业轮动"] = 16
        elif dominant_changes <= 2:
            scores["行业轮动"] = 13
        elif dominant_changes <= 4:
            scores["行业轮动"] = 9
        else:
            scores["行业轮动"] = 5
    else:
        scores["行业轮动"] = 10

    # ── 同业独特性（权重10，得分范围0-10）：基于分歧仓位胜率 ──
    uniqueness_score = calculate_peer_uniqueness_score(peer_analysis, holdings_dict, dates, benchmark_code)
    scores["同业独特性"] = uniqueness_score

    # 综合得分（各维度得分已按权重折算，直接相加）
    total = sum(scores.values())

    # 评级
    if total >= 85:
        rating, stars = "极强", "★★★★★"
    elif total >= 75:
        rating, stars = "较强", "★★★★"
    elif total >= 60:
        rating, stars = "中等", "★★★"
    elif total >= 45:
        rating, stars = "较弱", "★★"
    else:
        rating, stars = "弱", "★"

    return {
        "scores": {k: round(v, 1) for k, v in scores.items()},
        "total": round(total, 1),
        "rating": rating,
        "stars": stars,
    }


# ── 报告生成 ──

def generate_markdown_report(fund_code: str, fund_info: Dict,
                             analysis: Dict, effectiveness: Dict,
                             scores: Dict, peers: List[str],
                             peer_analysis: Dict = None) -> str:
    """生成 Markdown 格式报告"""
    today = datetime.now().strftime("%Y-%m-%d")
    dates = analysis.get("dates", [])
    window = f"过去 {len(dates)} 个季度" if dates else "未获取到数据"

    lines = []
    lines.append(f"# {fund_info.get('name', fund_code)} 主动管理基金调仓有效性验证报告")
    lines.append("")
    lines.append(f"> 基金代码：{fund_code} | 研究时间：{today} | 分析窗口：{window}")
    lines.append("")

    # 一、执行摘要
    lines.append("## 一、执行摘要")
    lines.append("")
    lines.append(f"**基金名称**：{fund_info.get('name', fund_code)}")
    lines.append(f"**基金经理**：{fund_info.get('manager', '待补')}")
    lines.append(f"**基金类型**：{fund_info.get('type', '待补')}")
    lines.append(f"**调仓有效性评级**：{scores.get('stars', '')} {scores.get('rating', '待评')}（综合得分 {scores.get('total', 'N/A')} / 100）")
    lines.append("")

    # 3 个关键发现
    changes = analysis.get("quarter_changes", pd.DataFrame())
    core = analysis.get("core_holdings", pd.DataFrame())
    s = effectiveness.get("summary", {})

    lines.append("**三个关键发现**：")
    findings = []
    if not changes.empty:
        max_change_idx = changes["变动合计"].idxmax()
        max_change = changes.iloc[max_change_idx]
        findings.append(f"调仓最剧烈的一期是 {max_change['报告期']}，{classify_rebalance_intensity(int(max_change['变动合计']))}，新增 {max_change['新增']} 只、退出 {max_change['退出']} 只重仓股。")
    if not core.empty:
        top_core = core.iloc[0]
        findings.append(f"核心持仓为 {top_core['股票名称']}（{top_core['股票代码']}），连续持有 {top_core['持有季度数']} 个季度。")
    if s.get("new_positions_avg_excess") is not None:
        findings.append(f"过去 {s.get('new_positions_count', 0)} 次新建仓位的平均 3 个月超额收益为 {s.get('new_positions_avg_excess', 0):.2f}%，胜率 {s.get('new_positions_win_rate', 0):.1f}%。")
    else:
        findings.append("由于行情数据缺失，本次未完整计算新增仓位超额收益。")
    for f in findings:
        lines.append(f"- {f}")
    lines.append("")

    # 二、基金概览
    lines.append("## 二、基金概览")
    lines.append("")
    lines.append(f"- **基金代码**：{fund_code}")
    lines.append(f"- **基金名称**：{fund_info.get('name', '待补')}")
    lines.append(f"- **基金类型**：{fund_info.get('type', '待补')}")
    lines.append(f"- **基金经理**：{fund_info.get('manager', '待补')}")
    lines.append(f"- **成立日期**：{fund_info.get('establish_date', '待补')}")
    lines.append(f"- **对比标的**：{', '.join(peers) if peers else '未指定'}")
    lines.append("")

    # 三、纵向调仓时间轴
    lines.append("## 三、纵向调仓时间轴")
    lines.append("")

    lines.append("### 3.1 十大重仓演变")
    lines.append("")
    matrix = analysis.get("matrix", pd.DataFrame())
    if not matrix.empty:
        # 显示占净值比矩阵
        header = "| 股票代码 | 股票名称 | " + " | ".join(dates) + " | 持有季度数 |"
        lines.append(header)
        lines.append("|" + "|".join(["---"] * (len(dates) + 3)) + "|")
        for _, row in matrix.iterrows():
            cells = [row["股票代码"], row["股票名称"]]
            for d in dates:
                val = row.get(d, 0)
                cells.append(f"{val:.2f}%" if val else "-")
            cells.append(str(int(row["持有季度数"])))
            lines.append("| " + " | ".join(cells) + " |")
    else:
        lines.append("> 未获取到持仓数据。")
    lines.append("")

    lines.append("### 3.2 核心持仓识别")
    lines.append("")
    if not core.empty:
        lines.append("| 股票代码 | 股票名称 | 持有季度数 |")
        lines.append("| --- | --- | --- |")
        for _, row in core.head(5).iterrows():
            lines.append(f"| {row['股票代码']} | {row['股票名称']} | {int(row['持有季度数'])} |")
    else:
        lines.append("> 未发现持有超过 6 个季度的核心持仓。")
    lines.append("")

    lines.append("### 3.3 季度调仓节奏")
    lines.append("")
    if not changes.empty:
        lines.append("| 报告期 | 新增 | 退出 | 变动合计 | 调仓幅度 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for _, row in changes.iterrows():
            intensity = classify_rebalance_intensity(int(row["变动合计"]))
            lines.append(f"| {row['报告期']} | {row['新增']} | {row['退出']} | {row['变动合计']} | {intensity} |")
    else:
        lines.append("> 未获取到足够季度数据。")
    lines.append("")

    # 四、横向同业对比
    lines.append("## 四、横向同业对比")
    lines.append("")

    if not peers:
        lines.append("> 未指定对比基金，可使用 `--peers 519700,519001` 参数补充。")
    elif peer_analysis is None or peer_analysis.get("overlap_by_date", pd.DataFrame()).empty:
        lines.append("> 已指定对比基金，但未能获取到足够对比持仓数据，请检查网络或基金代码。")
    else:
        summary = peer_analysis.get("summary", {})
        lines.append(f"**对比基金**：{', '.join(peers)}")
        lines.append(f"**平均持仓重叠度**：{summary.get('avg_overlap_ratio', 'N/A')}%")
        if summary.get('max_overlap_peer'):
            lines.append(f"**最接近同业**：{summary.get('max_overlap_peer')}（平均重叠度 {summary.get('max_overlap_ratio')}%）")
        lines.append("")

        lines.append("### 4.1 各期重叠度")
        lines.append("")
        overlap_df = peer_analysis.get("overlap_by_date", pd.DataFrame())
        if not overlap_df.empty:
            lines.append("| 报告期 | 本基金重仓数 | 对比基金并集 | 重叠标的数 | 重叠度 | 共识仓位 | 分歧仓位 |")
            lines.append("| --- | --- | --- | --- | --- | --- | --- |")
            for _, row in overlap_df.iterrows():
                lines.append(
                    f"| {row['报告期']} | {row['本基金重仓数']} | {row['对比基金并集']} | "
                    f"{row['重叠标的数']} | {row['重叠度']:.1f}% | {row['共识仓位']} | {row['分歧仓位']} |"
                )
        lines.append("")

        lines.append("### 4.2 共识仓位（多只基金共同重仓）")
        lines.append("")
        consensus_df = peer_analysis.get("consensus_positions", pd.DataFrame())
        if not consensus_df.empty:
            lines.append("| 报告期 | 股票代码 | 股票名称 |")
            lines.append("| --- | --- | --- |")
            for _, row in consensus_df.head(20).iterrows():
                lines.append(f"| {row['报告期']} | {row['股票代码']} | {row['股票名称']} |")
        else:
            lines.append("> 未发现共识仓位。")
        lines.append("")

        lines.append("### 4.3 分歧仓位（仅本基金重仓）")
        lines.append("")
        divergent_df = peer_analysis.get("divergent_positions", pd.DataFrame())
        if not divergent_df.empty:
            lines.append("| 报告期 | 股票代码 | 股票名称 |")
            lines.append("| --- | --- | --- |")
            for _, row in divergent_df.head(20).iterrows():
                lines.append(f"| {row['报告期']} | {row['股票代码']} | {row['股票名称']} |")
        else:
            lines.append("> 未发现分歧仓位。")

    lines.append("")

    # 五、调仓有效性验证
    lines.append("## 五、调仓有效性验证")
    lines.append("")

    lines.append("### 5.1 新增仓位效果")
    lines.append("")
    new_df = pd.DataFrame(effectiveness.get("new_positions", []))
    if not new_df.empty:
        lines.append("| 报告期 | 股票代码 | 股票名称 | 占净值比 | 3个月收益 | 基准收益 | 超额收益 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for _, row in new_df.iterrows():
            lines.append(
                f"| {row['报告期']} | {row['股票代码']} | {row['股票名称']} | "
                f"{fmt(row['占净值比'])}% | {fmt(row['3个月收益'])}% | "
                f"{fmt(row['基准3个月收益'])}% | {fmt(row['超额收益'], sign=True)}% |"
            )
    else:
        lines.append("> 未识别到新建仓位。")
    lines.append("")

    lines.append("### 5.2 清仓仓位效果")
    lines.append("")
    exit_df = pd.DataFrame(effectiveness.get("exit_positions", []))
    if not exit_df.empty:
        lines.append("| 报告期 | 股票代码 | 股票名称 | 上期占净值比 | 清仓后3个月收益 | 基准收益 | 相对收益 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for _, row in exit_df.iterrows():
            lines.append(
                f"| {row['报告期']} | {row['股票代码']} | {row['股票名称']} | "
                f"{fmt(row['上期占净值比'])}% | {fmt(row['清仓后3个月收益'])}% | "
                f"{fmt(row['基准3个月收益'])}% | {fmt(row['相对收益'], sign=True)}% |"
            )
    else:
        lines.append("> 未识别到清仓仓位。")
    lines.append("")

    lines.append("### 5.3 有效性汇总")
    lines.append("")
    summary = effectiveness.get("summary", {})
    lines.append(f"- 新增仓位数量：{summary.get('new_positions_count', 'N/A')}")
    lines.append(f"- 新增仓位平均超额收益：{fmt(summary.get('new_positions_avg_excess'), sign=True)}%")
    lines.append(f"- 新增仓位胜率：{fmt(summary.get('new_positions_win_rate'))}%")
    lines.append(f"- 清仓仓位数量：{summary.get('exit_positions_count', 'N/A')}")
    lines.append(f"- 清仓后相对收益：{fmt(summary.get('exit_positions_avg_relative'), sign=True)}%（负值代表卖出有效）")
    lines.append(f"- 有效规避比例：{fmt(summary.get('exit_positions_avoid_rate'))}%")
    lines.append("")

    # 六、基金经理调仓风格画像
    lines.append("## 六、基金经理调仓风格画像")
    lines.append("")
    style_notes = []
    if not changes.empty:
        avg_changes = changes["变动合计"].mean()
        if avg_changes < 2:
            style_notes.append("**低换手型**：季度调仓幅度较小，持股稳定性高。")
        elif avg_changes < 4:
            style_notes.append("**稳健调仓型**：每季度适度优化结构，既有核心持仓也有灵活调整。")
        else:
            style_notes.append("**高换手型**：调仓频繁，策略灵活度高，需重点关注每次切换的有效性。")
    if not core.empty:
        style_notes.append("存在长期核心持仓，倾向于用压舱石锚定组合。")
    else:
        style_notes.append("未发现持续持有的核心仓位，风格偏向轮动或波段。")
    for note in style_notes:
        lines.append(f"- {note}")
    lines.append("")

    # 七、评分卡
    lines.append("## 七、调仓有效性评分卡")
    lines.append("")
    lines.append("| 维度 | 得分（已按权重折算） | 满分权重 |")
    lines.append("| --- | --- | --- |")
    weights = {"调仓时机": 0.25, "行业轮动": 0.20, "核心持仓": 0.20,
               "风险控制": 0.15, "换手效率": 0.10, "同业独特性": 0.10}
    for dim, score in scores.get("scores", {}).items():
        w = weights.get(dim, 0)
        lines.append(f"| {dim} | {score:.1f} | {int(w*100)}% |")
    lines.append(f"| **综合得分** | **{scores.get('total', 'N/A')} / 100** | |")
    lines.append(f"| **调仓有效性评级** | **{scores.get('stars', '')} {scores.get('rating', '')}** | |")
    lines.append("")

    # 八、投资建议与风险提示
    lines.append("## 八、投资建议与风险提示")
    lines.append("")
    total = scores.get("total", 0)
    if total >= 80:
        advice = "基金经理调仓能力较强，新增仓位和行业切换多数有效，可作为核心或重点配置关注。"
    elif total >= 70:
        advice = "调仓效果良好，存在较多有效决策，可作为卫星配置或重点观察对象持续跟踪。"
    elif total >= 60:
        advice = "调仓效果中等，存在有效决策但也有改进空间，建议作为卫星配置跟踪观察。"
    elif total >= 45:
        advice = "调仓有效性偏弱，部分决策存在追涨或过早离场迹象，建议放入观察名单。"
    else:
        advice = "调仓行为对组合贡献有限甚至负贡献，需谨慎评估基金经理的主动管理能力。"
    lines.append(f"**投资建议**：{advice}")
    lines.append("")
    lines.append("**风险提示**：")
    lines.append("- 本报告基于季报前十大重仓数据，存在滞后性和样本局限。")
    lines.append("- 行情数据可能因停牌、退市等原因缺失，导致超额收益计算不完整。")
    lines.append("- 市场环境、基金经理变更等因素会影响历史调仓有效性的参考价值。")
    lines.append("- 本报告不构成投资建议，基金投资有风险，入市需谨慎。")
    lines.append("")

    # 九、信息来源
    lines.append("## 九、信息来源与数据声明")
    lines.append("")
    lines.append("- 基金基础信息：天天基金网（fundf10.eastmoney.com）")
    lines.append("- 基金持仓数据：天天基金网")
    lines.append("- 个股行情数据：腾讯财经")
    lines.append("- 指数数据：腾讯财经")
    lines.append("- 行业分类：申万行业分类标准（简化推断）")
    lines.append("")
    lines.append("数据缺失项已在报告中标注为「待补」或「N/A」。")
    lines.append("")

    return "\n".join(lines)


def fmt(val, sign: bool = False) -> str:
    """格式化数值，处理 None"""
    if val is None:
        return "N/A"
    if sign:
        return f"{val:+.2f}"
    return f"{val:.2f}"


# ── 主流程 ──

def main():
    if not AKSHARE_AVAILABLE:
        print("[WARN] 未检测到 AKShare，部分行情数据可能无法获取。")
        print("[提示] 可运行：pip install akshare --break-system-packages")

    args = parse_args()
    fund_code = args.fund_code
    peers = [p.strip() for p in args.peers.split(",") if p.strip()]
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] 开始分析基金：{fund_code}")
    print(f"[INFO] 分析季度数：{args.quarters}")
    print(f"[INFO] 输出目录：{output_dir}")

    # 1. 基金基本信息
    fund_info = get_fund_info_em(fund_code)
    print(f"[INFO] 基金名称：{fund_info.get('name', '未知')}")

    # 2. 报告期
    report_dates = get_report_dates(n=args.quarters)
    print(f"[INFO] 报告期：{report_dates}")

    # 3. 获取持仓数据
    holdings_dict = {}
    for date in report_dates:
        df = get_fund_holdings_em(fund_code, date)
        if not df.empty:
            holdings_dict[date] = df
            print(f"[OK] {date} 获取 {len(df)} 条持仓记录")
        else:
            print(f"[WARN] {date} 未获取到持仓数据")

    if len(holdings_dict) < 2:
        print("[ERROR] 有效持仓数据不足，无法完成分析。请检查网络连接或基金代码。")
        sys.exit(1)

    # 4. 分析持仓演变
    analysis = analyze_holdings_evolution(holdings_dict, benchmark_code=args.benchmark)

    # 5. 计算有效性
    effectiveness = calculate_effectiveness(holdings_dict, sorted(holdings_dict.keys()), args.benchmark)

    # 6. 对比基金重叠分析
    peer_analysis = analyze_peer_overlap(fund_code, holdings_dict, peers, sorted(holdings_dict.keys()))

    # 7. 评分
    scores = calculate_scores(
        analysis,
        effectiveness,
        peer_analysis=peer_analysis,
        holdings_dict=holdings_dict,
        benchmark_code=args.benchmark,
    )

    # 8. 生成 Markdown 报告
    md_content = generate_markdown_report(fund_code, fund_info, analysis, effectiveness, scores, peers, peer_analysis)
    md_path = output_dir / f"调仓有效性验证_{fund_code}_{fund_info.get('name', fund_code)}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[OK] Markdown 报告已生成：{md_path}")

    # 9. 保存数据底稿
    data_path = output_dir / f"调仓有效性验证_{fund_code}_{fund_info.get('name', fund_code)}_data.json"
    try:
        data_payload = {
            "fund_info": fund_info,
            "scores": scores,
            "summary": effectiveness.get("summary", {}),
            "quarter_changes": analysis.get("quarter_changes", pd.DataFrame()).to_dict(orient="records"),
        }
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data_payload, f, ensure_ascii=False, indent=2, default=str)
        print(f"[OK] 数据底稿已生成：{data_path}")
    except Exception as e:
        print(f"[WARN] 数据底稿保存失败：{e}")

    # 10. 生成 PDF
    if not args.no_pdf:
        pdf_path = output_dir / f"调仓有效性验证_{fund_code}_{fund_info.get('name', fund_code)}.pdf"
        script_dir = Path(__file__).parent
        weasy_script = script_dir / "md_to_pdf.py"
        playwright_script = script_dir / "md_to_pdf_playwright.py"
        title = f"{fund_info.get('name', fund_code)} 调仓有效性验证"
        author = "R9（资产配置研习社）"

        def _run_pdf_converter(script: Path) -> bool:
            """使用 subprocess 安全调用 PDF 转换脚本，避免 shell 注入。"""
            cmd = [
                sys.executable,
                str(script),
                str(md_path),
                str(pdf_path),
                "--title", title,
                "--author", author,
            ]
            try:
                result = subprocess.run(cmd, check=False, capture_output=True, text=True, encoding="utf-8")
                if result.returncode == 0:
                    print(f"[OK] PDF 报告已生成：{pdf_path}")
                    return True
                else:
                    stderr = result.stderr.strip()
                    if stderr:
                        print(f"[WARN] PDF 转换失败：{stderr[:200]}")
                    return False
            except Exception as e:
                print(f"[WARN] PDF 转换异常：{e}")
                return False

        print(f"[INFO] 正在生成 PDF：{pdf_path}")
        if weasy_script.exists():
            if _run_pdf_converter(weasy_script):
                pass
            elif playwright_script.exists():
                print(f"[INFO] WeasyPrint 失败，尝试 Playwright 备选方案...")
                if not _run_pdf_converter(playwright_script):
                    print(f"[WARN] PDF 生成失败，请检查 weasyprint 或 playwright 是否安装。")
            else:
                print(f"[WARN] PDF 生成失败，请检查 weasyprint 是否安装。")
        elif playwright_script.exists():
            if not _run_pdf_converter(playwright_script):
                print(f"[WARN] PDF 生成失败，请检查 playwright 是否安装。")
        else:
            print(f"[WARN] 未找到 PDF 转换脚本。")


if __name__ == "__main__":
    main()
