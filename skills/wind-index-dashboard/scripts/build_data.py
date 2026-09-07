#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build dashboard data for 老登/中登/小登 indices.
Reads Excel files for index list; all financial data comes from Wind API.
"""
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

WIND_CLI_DIR = Path.home() / ".claude" / "skills" / "wind-mcp-skill"
EXCEL_DIR = Path("/Users/r9/Desktop")
OUT_FILE = Path(__file__).parent / "data.json"
CACHE_FILE = Path(__file__).parent / "wind_cache.json"

MODULES = {
    "老登指数": {"file": EXCEL_DIR / "老登指数.xlsx", "tag": "老登", "color": "#8B5CF6"},
    "中登指数": {"file": EXCEL_DIR / "中登指数.xlsx", "tag": "中登", "color": "#3B82F6"},
    "小登指数": {"file": EXCEL_DIR / "小登指数.xlsx", "tag": "小登", "color": "#F59E0B"},
}

# Load cache to avoid re-fetching unchanged data; `--fresh` forces full refetch
FRESH = "--fresh" in sys.argv
_cache = {}
if CACHE_FILE.exists() and not FRESH:
    try:
        _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        _cache = {}


def _cache_key(server_type, tool_name, params):
    return f"{server_type}|{tool_name}|{json.dumps(params, sort_keys=True, ensure_ascii=False)}"


def wind_call(server_type: str, tool_name: str, params: dict, use_cache: bool = True) -> dict:
    """Call Wind MCP CLI and return parsed JSON result."""
    key = _cache_key(server_type, tool_name, params)
    if use_cache and key in _cache:
        return _cache[key]

    params_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
    cmd = f"cd {WIND_CLI_DIR} && node scripts/cli.mjs call {server_type} {tool_name} '{params_json}'"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            _cache[key] = {}
            return {}
        output = json.loads(result.stdout)
        text = output.get("content", [{}])[0].get("text", "{}")
        parsed = json.loads(text)
        _cache[key] = parsed
        return parsed
    except Exception:
        _cache[key] = {}
        return {}


def save_cache():
    CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_wind_table(data: dict) -> list:
    """Parse Wind response with columns/rows into list of dicts."""
    if not data or "data" not in data:
        return []
    inner = data.get("data", {})
    if isinstance(inner, dict) and "rows" in inner and "columns" in inner:
        cols = [c["name"] for c in inner["columns"]]
        return [dict(zip(cols, row)) for row in inner["rows"]]
    if isinstance(inner, dict) and "data" in inner and isinstance(inner["data"], list):
        first = inner["data"][0]
        if isinstance(first, dict) and "rows" in first and "columns" in first:
            cols = [c["name"] for c in first["columns"]]
            return [dict(zip(cols, row)) for row in first["rows"]]
    if isinstance(inner, list) and len(inner) and "rows" in inner[0]:
        cols = [c["name"] for c in inner[0]["columns"]]
        return [dict(zip(cols, row)) for row in inner[0]["rows"]]
    return []


def safe_float(value, default=None):
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return float(value)
    except Exception:
        return default


def read_excel_index(file_path: Path) -> list:
    """Read index rows from Excel, dropping source footer."""
    df = pd.read_excel(file_path, sheet_name="file")
    df = df[df["代码"].notna()]
    df = df[~df["代码"].astype(str).str.contains("数据来源", na=False)]
    records = []
    for _, row in df.iterrows():
        code = str(row["代码"]).strip()
        name = str(row["名称"]).strip() if pd.notna(row["名称"]) else ""
        records.append({"code": code, "name": name})
    return records


def fetch_index_metrics(code: str) -> dict:
    """Fetch daily/weekly/monthly/yearly metrics and 52-week high/low, plus valuation/liquidity."""
    indexes = (
        "最新成交价,涨跌幅,涨跌,5日涨跌幅,10日涨跌幅,20日涨跌幅,60日涨跌幅,120日涨跌幅,250日涨跌幅,"
        "年初至今涨跌幅,52周最高,52周最低,成交量,成交额,换手率,振幅,市盈率(TTM),市净率(LF),总市值1"
    )
    data = wind_call("index_data", "get_index_price_indicators", {"windcode": code, "indexes": indexes})
    rows = parse_wind_table(data)
    if not rows:
        return {}
    r = rows[0]
    return {
        "latest": safe_float(r.get("最新成交价")),
        "daily_change": safe_float(r.get("涨跌幅")),
        "weekly_change": safe_float(r.get("5日涨跌幅")),
        "monthly_change": safe_float(r.get("20日涨跌幅")),
        "yearly_change": safe_float(r.get("250日涨跌幅")),
        "ytd_change": safe_float(r.get("年初至今涨跌幅")),
        "week_52_high": safe_float(r.get("52周最高")),
        "week_52_low": safe_float(r.get("52周最低")),
        "turnover": safe_float(r.get("成交额")),
        "turnover_rate": safe_float(r.get("换手率")),
        "amplitude": safe_float(r.get("振幅")),
        "pe_ttm": safe_float(r.get("市盈率(TTM)")),
        "pb_lf": safe_float(r.get("市净率(LF)")),
        "market_cap": safe_float(r.get("总市值1")),
    }


def fetch_kline(code: str, begin_date: str, end_date: str) -> pd.DataFrame:
    """Fetch daily kline for max drawdown computation. Retries when the API
    returns a suspiciously short series (rate-limit truncation under concurrency)."""
    params = {"windcode": code, "begin_date": begin_date, "end_date": end_date, "period": "10"}
    rows = []
    for attempt in range(4):
        data = wind_call("index_data", "get_index_kline", params, use_cache=(attempt == 0))
        rows = parse_wind_table(data)
        if len(rows) >= 50:
            _cache[_cache_key("index_data", "get_index_kline", params)] = data
            break
        time.sleep(2 + attempt * 2)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["MATCH"] = pd.to_numeric(df.get("MATCH"), errors="coerce")
    date_col = df.get("_DATE") if "_DATE" in df.columns else df.get("TIME")
    df["TIME"] = pd.to_datetime(date_col, errors="coerce", utc=True)
    return df.dropna(subset=["MATCH"])


def compute_max_drawdown(series: pd.Series) -> dict:
    """Compute max drawdown and distance from peak."""
    if series.empty:
        return {"max_drawdown": None}
    rolling_max = series.cummax()
    drawdown = (series - rolling_max) / rolling_max
    max_dd_idx = drawdown.idxmin()
    peak_before = series.loc[:max_dd_idx].max()
    return {
        "max_drawdown": round(drawdown.min() * 100, 2),
        "peak": round(peak_before, 2),
        "trough": round(series.loc[max_dd_idx], 2),
    }


def compute_trading_day_return(series: pd.Series, days: int) -> float:
    """Compute return over the last N trading days from a series (latest last)."""
    if series.empty or len(series) < days + 1:
        return None
    recent = series.iloc[-1]
    past = series.iloc[-(days + 1)]
    return (recent - past) / past * 100


def fetch_constituents(code: str, top_n: int = 10) -> list:
    """Fetch top N constituents by weight, trying query variants."""
    variants = [f"{code}指数前{top_n}大权重股及权重", f"{code}指数成分股及权重", f"{code}指数权重股"]
    for question in variants:
        data = wind_call("index_data", "get_index_fundamentals", {"question": question})
        rows = parse_wind_table(data)
        if rows:
            break
    seen = set()
    out = []
    for r in rows:
        scode = str(r.get("指数成份代码", "")).strip()
        sname = str(r.get("指数成份简称", "")).strip()
        weight = safe_float(r.get("指数成份权重"))
        if scode and scode not in seen:
            seen.add(scode)
            out.append({"code": scode, "name": sname, "weight": weight})
    out.sort(key=lambda x: x["weight"] if x["weight"] is not None else 0, reverse=True)
    return out[:top_n]


def batch_stock_technicals(codes: list) -> dict:
    """Fetch latest change for a batch of stocks."""
    if not codes:
        return {}
    data = wind_call("stock_data", "get_stock_technicals", {"question": f"{'、'.join(codes)}最新涨跌幅"})
    rows = parse_wind_table(data)
    result = {}
    for r in rows:
        code = str(r.get("Wind代码", "")).strip()
        result[code] = safe_float(r.get("最新涨跌幅"))
    return result


def batch_stock_fundamentals(codes: list) -> dict:
    """Fetch fundamentals and main business for a batch of stocks."""
    if not codes:
        return {}
    data = wind_call("stock_data", "get_stock_fundamentals", {
        "question": f"{'、'.join(codes)}主营业务、PE_TTM、PB_LF、ROE、净利润同比增长率"
    })
    rows = parse_wind_table(data)
    result = {}
    for r in rows:
        code = str(r.get("Wind代码", "")).strip()
        name = str(r.get("证券简称", "")).strip()
        if code not in result:
            result[code] = {"name": name, "pe_ttm": None, "pb_lf": None, "roe": None, "profit_growth": None, "businesses": []}
        result[code]["pe_ttm"] = safe_float(r.get("市盈率PE_TTM"), result[code]["pe_ttm"])
        result[code]["pb_lf"] = safe_float(r.get("市净率PB_LF"), result[code]["pb_lf"])
        result[code]["roe"] = safe_float(r.get("净资产收益率ROE"), result[code]["roe"])
        result[code]["profit_growth"] = safe_float(r.get("净利润_同比增长率"), result[code]["profit_growth"])
        biz = r.get("前5大主营业务")
        if biz and pd.notna(biz):
            result[code]["businesses"].append(str(biz))
    return result


def fetch_stock_price_indicator(code: str) -> float:
    data = wind_call("stock_data", "get_stock_price_indicators", {"windcode": code, "indexes": "涨跌幅"})
    rows = parse_wind_table(data)
    return safe_float(rows[0].get("涨跌幅")) if rows else None


def fetch_stock_basicinfo(code: str) -> dict:
    data = wind_call("stock_data", "get_stock_basicinfo", {"question": f"{code}公司基本档案和主营业务"})
    rows = parse_wind_table(data)
    if not rows:
        return {}
    r = rows[0]
    business = r.get("主营收入构成") or r.get("经营范围") or r.get("公司简介") or ""
    return {"main_business": str(business)[:120] if business else ""}


def clean_business(parts: list) -> str:
    """Clean business segments: remove percentages/numbers and keep top names."""
    cleaned = []
    for p in parts:
        # Split by common separators and remove percentage/number portions
        segments = re.split(r"[;；、,，/\\]", str(p))
        for seg in segments:
            # Remove anything that looks like a percentage or ratio
            seg = re.sub(r"[:：]\s*[-\d.]+%?\s*$", "", seg).strip()
            seg = re.sub(r"\s*[-\d.]+%\s*$", "", seg).strip()
            if seg and seg not in cleaned and len(seg) < 40:
                cleaned.append(seg)
    return "、".join(cleaned[:3]) if cleaned else "-"


def clean_pe(pe):
    """Replace extreme/invalid PE with readable marker."""
    if pe is None:
        return None
    if pe < -1000 or pe > 10000 or pe == 0:
        return None
    return pe


def build_commentary(idx: dict, module_tag: str) -> str:
    name = idx["name"]
    daily = idx.get("daily_change")
    weekly = idx.get("weekly_change")
    monthly = idx.get("monthly_change")
    yearly = idx.get("yearly_change")
    ytd = idx.get("ytd_change")
    dd = idx.get("max_drawdown")
    dist = idx.get("distance_to_high")

    tone = "平盘"
    if daily is not None:
        if daily > 1.5:
            tone = "强势领涨"
        elif daily > 0:
            tone = "小幅收红"
        elif daily > -1.5:
            tone = "温和调整"
        else:
            tone = "明显回调"

    parts = [f"【{name}】今日{tone}"]
    if daily is not None:
        parts.append(f"，单日涨跌幅{daily:+.2f}%")
    if weekly is not None:
        parts.append(f"；近一周{weekly:+.2f}%")
    if monthly is not None:
        parts.append(f"、近一月{monthly:+.2f}%")
    if yearly is not None:
        parts.append(f"、近一年{yearly:+.2f}%")

    if daily is not None and monthly is not None:
        if daily > 0 and monthly < 0:
            parts.append("。短期反弹但中期趋势仍弱，需观察成交量能否持续放大，反弹若要升级为反转，需要站稳20日均线并出现板块共振。")
        elif daily > 0 and monthly > 0:
            parts.append("。短期与中期同向，趋势相对健康，但也要警惕获利盘兑现带来的波动。")
        elif daily < 0 and monthly > 0:
            parts.append("。中期趋势尚好，今日回调可视为正常整固，关键看是否跌破重要支撑位。")
        else:
            parts.append("。短中期均承压，资金情绪偏谨慎，宜控制仓位、等待右侧信号。")

    if dist is not None:
        if dist < 5:
            parts.append(f"距离52周新高仅{dist:.1f}%，处于突破临界区。")
        elif dist > 30:
            parts.append(f"距离52周新高仍有{dist:.1f}%，修复空间较大但信心不足。")

    if dd is not None and dd < -20:
        parts.append(f"近一年最大回撤{dd:.1f}%，高波动特征明显，仓位管理上建议分批。")

    return "".join(parts)


def hv_brief(idx: dict, module_tag: str) -> str:
    name = idx["name"]
    daily = idx.get("daily_change")
    monthly = idx.get("monthly_change")
    yearly = idx.get("yearly_change")
    ytd = idx.get("ytd_change")
    dd = idx.get("max_drawdown")

    vertical = []
    if ytd is not None:
        vertical.append(f"年初至今{ytd:+.2f}%")
    if monthly is not None:
        vertical.append(f"近一月{monthly:+.2f}%")
    if yearly is not None:
        vertical.append(f"近一年{yearly:+.2f}%")
    if dd is not None:
        vertical.append(f"最大回撤{dd:.1f}%")

    if module_tag == "老登":
        horizontal = ["估值中枢普遍偏低（银行、地产、能源多为价值蓝筹）", "收益弹性弱于成长板块但防御属性强", "受宏观利率与政策预期影响大"]
    elif module_tag == "中登":
        horizontal = ["医药、军工、新能源、有色、化工等赛道交织", "周期与成长属性并存，波动中等", "对产业政策与库存周期敏感度较高"]
    else:
        horizontal = ["AI、半导体、机器人、消费电子等成长主题集中", "估值弹性大，资金情绪影响显著", "对产业景气度和流动性变化高度敏感"]

    brief = f"<h4>纵向：{name}时间轴</h4>"
    brief += f"<p>{'，'.join(vertical)}。从时间维度看，短期动能{'偏强' if (daily or 0) > 0 else '偏弱'}，"
    if monthly is not None and yearly is not None:
        brief += "中期与长期趋势方向一致，结构相对清晰。" if monthly * yearly > 0 else "中期与长期趋势方向背离，说明市场仍在重新定价。"
    brief += "</p>"

    brief += f"<h4>横向：{module_tag}模块定位</h4><ul>"
    for h in horizontal:
        brief += f"<li>{h}</li>"
    brief += "</ul>"

    brief += "<h4>交叉洞察</h4><p>"
    if (daily or 0) > 0 and (monthly or 0) < 0:
        brief += "短期反弹处于中期下行通道中，趋势反转需要基本面或资金面的持续性验证。"
    elif (daily or 0) > 0 and (monthly or 0) > 0:
        brief += "量价方向共振，若成交配合，有望延续当前的相对强势。"
    elif (daily or 0) < 0 and (monthly or 0) > 0:
        brief += "今日调整属于趋势中的正常整固，重点观察关键均线与龙头承接力。"
    else:
        brief += "短期与中期均处于调整格局，宜以防守为主，等待明确的企稳信号。"
    brief += "</p>"

    return brief


def process_index(idx: dict, tag: str, begin_date: str, end_date: str) -> dict:
    """Process a single index: fetch all Wind data and build commentary."""
    code = idx["code"]
    name = idx["name"]
    print(f"  - {name} ({code})")

    metrics = fetch_index_metrics(code)
    if not metrics:
        print(f"    Warning: no metrics for {code}")

    latest = metrics.get("latest")
    high_52 = metrics.get("week_52_high")
    distance_to_high = None
    is_new_high = False
    if latest and high_52 and high_52 > 0:
        distance_to_high = (high_52 - latest) / high_52 * 100
        is_new_high = latest >= high_52 * 0.999

    kline = fetch_kline(code, begin_date, end_date)
    dd_info = compute_max_drawdown(kline["MATCH"]) if not kline.empty else {}
    seven_day = compute_trading_day_return(kline["MATCH"], 7) if not kline.empty else None

    # Daily close series for sparklines / charts (chronological)
    series = []
    if not kline.empty:
        k = kline.sort_values("TIME")
        for t, c in zip(k["TIME"], k["MATCH"]):
            try:
                series.append({"d": t.strftime("%Y-%m-%d"), "c": round(float(c), 2)})
            except Exception:
                pass

    constituents = fetch_constituents(code, top_n=10)
    stock_codes = [c["code"] for c in constituents]

    # Batch fetch stock changes and fundamentals
    changes = batch_stock_technicals(stock_codes)
    fundamentals = batch_stock_fundamentals(stock_codes)

    # Identify missing items
    missing_change = [c for c in constituents if changes.get(c["code"]) is None]
    missing_biz = [c for c in constituents if not fundamentals.get(c["code"], {}).get("businesses")]

    # Parallel fallback fetch
    with ThreadPoolExecutor(max_workers=5) as ex:
        change_futures = {ex.submit(fetch_stock_price_indicator, c["code"]): c for c in missing_change}
        biz_futures = {ex.submit(fetch_stock_basicinfo, c["code"]): c for c in missing_biz}
        for fut in as_completed(change_futures):
            c = change_futures[fut]
            try:
                changes[c["code"]] = fut.result(timeout=30)
            except Exception:
                pass
        for fut in as_completed(biz_futures):
            c = biz_futures[fut]
            try:
                basic = fut.result(timeout=30)
                if c["code"] not in fundamentals:
                    fundamentals[c["code"]] = {"businesses": []}
                if basic.get("main_business"):
                    fundamentals[c["code"]]["businesses"].append(basic["main_business"])
            except Exception:
                pass

    holdings = []
    for c in constituents:
        scode = c["code"]
        sname = c["name"]
        f = fundamentals.get(scode, {})
        biz_list = f.get("businesses", [])
        main_business = clean_business(biz_list[:3]) if biz_list else "-"
        holdings.append({
            "code": scode,
            "name": f.get("name") or sname,
            "weight": c["weight"],
            "daily_change": changes.get(scode),
            "main_business": main_business,
            "pe_ttm": clean_pe(f.get("pe_ttm")),
            "pb_lf": f.get("pb_lf"),
            "roe": f.get("roe"),
            "profit_growth": f.get("profit_growth"),
        })

    clean = {
        "code": code,
        "name": name,
        "price": metrics.get("latest"),
        "daily_change": metrics.get("daily_change"),
        "weekly_change": round(seven_day, 2) if seven_day is not None else metrics.get("weekly_change"),
        "monthly_change": metrics.get("monthly_change"),
        "yearly_change": metrics.get("yearly_change"),
        "ytd_change": metrics.get("ytd_change"),
        "is_new_high": is_new_high,
        "distance_to_high": round(distance_to_high, 2) if distance_to_high is not None else None,
        "max_drawdown": dd_info.get("max_drawdown"),
        "turnover": metrics.get("turnover"),
        "amplitude": metrics.get("amplitude"),
        "pe_ttm": metrics.get("pe_ttm"),
        "pb_lf": metrics.get("pb_lf"),
        "market_cap": metrics.get("market_cap"),
        "holdings": holdings,
        "series": series,
    }
    clean["commentary"] = build_commentary(clean, tag)
    clean["hv_brief"] = hv_brief(clean, tag)
    return clean


def main():
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    end_date = datetime.now().strftime("%Y%m%d")
    begin_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

    output = {"as_of": today, "data_source": "Wind / 万得金融数据", "modules": []}

    for module_name, config in MODULES.items():
        print(f"\nProcessing {module_name}...")
        indices = read_excel_index(config["file"])

        module_indices = []
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {ex.submit(process_index, idx, config["tag"], begin_date, end_date): idx for idx in indices}
            for fut in as_completed(futures):
                try:
                    module_indices.append(fut.result(timeout=300))
                except Exception as e:
                    print(f"    Error processing index: {e}")

        # Preserve original order
        order = {idx["code"]: i for i, idx in enumerate(indices)}
        module_indices.sort(key=lambda x: order.get(x["code"], 999))

        changes = [i["daily_change"] for i in module_indices if i["daily_change"] is not None]
        avg_change = sum(changes) / len(changes) if changes else 0
        heat = min(100, max(0, (avg_change + 3) / 6 * 100))

        if config["tag"] == "老登":
            commentary = f"老登模块以地产、白酒、煤炭、钢铁、银行、油气、基建为代表，整体估值偏低、分红属性强。今日平均涨跌幅{avg_change:+.2f}%，{'情绪回暖' if avg_change > 0 else '情绪承压'}。价值板块对利率与政策预期最敏感，当前建议以防御为主，关注高股息与低PB品种的相对优势。"
        elif config["tag"] == "中登":
            commentary = f"中登模块覆盖医药、军工、新能源、有色、化工、光伏、恒生科技，兼具周期与成长。今日平均涨跌幅{avg_change:+.2f}%，{'板块轮动偏积极' if avg_change > 0 else '轮动偏谨慎'}。中游赛道对库存周期和产业政策高度敏感，建议重点跟踪龙头业绩兑现与产能利用率变化。"
        else:
            commentary = f"小登模块聚焦AI、半导体、机器人、消费电子、动漫游戏、科创/创业板50，成长弹性最大。今日平均涨跌幅{avg_change:+.2f}%，{'风险偏好较高' if avg_change > 0 else '风险偏好回落'}。主题投资对流动性和产业催化高度敏感，波动大、回撤深，建议用仓位管理替代择时。"

        output["modules"].append({
            "name": module_name,
            "tag": config["tag"],
            "color": config["color"],
            "heat_percentile": round(heat, 1),
            "avg_daily_change": round(avg_change, 2),
            "commentary": commentary,
            "indices": module_indices,
        })

    OUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    save_cache()
    print(f"\nData written to {OUT_FILE}")


if __name__ == "__main__":
    main()
