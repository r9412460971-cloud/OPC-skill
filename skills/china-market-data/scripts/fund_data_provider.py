#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R9 基金数据统一获取层 (Fund Data Provider)

数据优先级（R9 执行标准）：
    且慢(盈米) MCP → 天天基金网 → AKShare 基金接口 → Wind / iFinD / Choice

使用示例：
    from fund_data_provider import FundDataProvider
    provider = FundDataProvider()
    info = provider.get_fund_info('000001')
    nav = provider.get_nav_history('000001', years=1)
    holdings = provider.get_holdings('000001')
"""

import os
import sys
import json
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
import pandas as pd

# 当前脚本所在目录，用于导入同目录的 EastMoneyFetcher
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

from eastmoney_fetcher import EastMoneyFetcher


# ------------------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------------------

def _safe_getenv(key: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(key, default)


def _log_source(source: str, method: str, fund_code: str):
    """打印当前使用的数据源，便于排查和审计"""
    print(f"  [FundData] {method}({fund_code}) 数据源: {source}")


# ------------------------------------------------------------------------------
# P0: 且慢(盈米) MCP 数据层
# ------------------------------------------------------------------------------

class QiemanMCPProvider:
    """
    且慢(盈米) MCP 数据提供层。
    使用标准 MCP over SSE 协议（jsonrpc 2.0）连接 stargate.yingmi.com。
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or _safe_getenv("QIEMAN_MCP_API_KEY") or _safe_getenv("QIEMAN_API_KEY")
        self.base_url = _safe_getenv("QIEMAN_MCP_BASE_URL", "https://stargate.yingmi.com/mcp")
        self.session = requests.Session()
        self._tools: List[str] = []
        self._message_url: Optional[str] = None
        self._sse_resp = None
        self._sse_thread = None
        self._response_queue = None
        self._initialized = False

    def available(self) -> bool:
        """检查是否配置了 API Key"""
        return bool(self.api_key)

    def _start_sse(self, timeout: int = 15) -> bool:
        """启动后台 SSE 连接并初始化"""
        if self._message_url and self._initialized:
            return True
        if not self.api_key:
            return False

        try:
            import sseclient
            import threading
            import queue

            self._response_queue = queue.Queue()
            self._sse_resp = self.session.get(
                f"{self.base_url}/sse?apiKey={self.api_key}",
                stream=True,
                timeout=timeout,
            )
            self._sse_resp.raise_for_status()
            client = sseclient.SSEClient(self._sse_resp)

            def consume():
                """后台消费 SSE 事件"""
                try:
                    for event in client.events():
                        if event.event == "endpoint":
                            self._message_url = event.data
                        elif event.event == "message":
                            try:
                                self._response_queue.put(json.loads(event.data))
                            except Exception:
                                pass
                except Exception as e:
                    # SSE 连接断开，标记需要重新连接
                    self._message_url = None
                    self._initialized = False

            self._sse_thread = threading.Thread(target=consume, daemon=True)
            self._sse_thread.start()

            # 等待 endpoint
            deadline = time.time() + timeout
            while self._message_url is None and time.time() < deadline:
                time.sleep(0.1)

            if not self._message_url:
                return False

            # 发送 initialize
            self._rpc_call("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "r9-fund-provider", "version": "1.0.0"},
            }, rpc_timeout=10)

            # 获取 tools 列表
            tools_result = self._rpc_call("tools/list", {}, rpc_timeout=10)
            tools = tools_result.get("result", {}).get("tools", []) if isinstance(tools_result, dict) else []
            self._tools = [t.get("name") for t in tools]
            self._initialized = True
            return True

        except Exception as e:
            print(f"  [Qieman MCP] 启动失败: {e}")
            self._message_url = None
            self._initialized = False
            return False

    def _rpc_call(self, method: str, params: dict, rpc_timeout: int = 30) -> dict:
        """发送 jsonrpc 请求并等待响应"""
        if not self._start_sse():
            return {}

        req_id = int(time.time() * 1000) % 1000000
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        try:
            url = urljoin(self.base_url, self._message_url)
            resp = self.session.post(url, json=payload, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [Qieman MCP] 发送 {method} 请求失败: {e}")
            return {}

        # 等待响应
        deadline = time.time() + rpc_timeout
        while time.time() < deadline:
            try:
                msg = self._response_queue.get(timeout=0.2)
                if msg.get("id") == req_id:
                    return msg
                # 不是本次请求的响应，丢弃
            except Exception:
                continue
        return {}

    def _call_tool(self, tool: str, params: dict, rpc_timeout: int = 30) -> dict:
        """调用 MCP tool"""
        if self._tools and tool not in self._tools:
            print(f"  [Qieman MCP] 工具 {tool} 不存在")
            return {}

        result = self._rpc_call("tools/call", {"name": tool, "arguments": params}, rpc_timeout=rpc_timeout)
        if not isinstance(result, dict):
            return {}
        if result.get("error"):
            print(f"  [Qieman MCP] {tool} 返回错误: {result['error']}")
            return {}

        # 解析 text 内容中的 JSON
        content = result.get("result", {}).get("content", [])
        for item in content:
            if item.get("type") == "text":
                try:
                    return json.loads(item.get("text", "{}"))
                except Exception:
                    return {"text": item.get("text", "")}
        return {}

    # ---- 公开接口 ----

    def get_fund_info(self, fund_code: str) -> Dict:
        """基金详细信息"""
        data = self._call_tool("BatchGetFundsDetail", {"fundCodes": [fund_code]})
        funds = data.get("funds") if isinstance(data, dict) else None
        if not funds:
            return {}
        d = funds[0] if isinstance(funds, list) else funds
        return {
            "fund_code": fund_code,
            "fund_name": d.get("fundName", d.get("fund_name", "")),
            "fund_type": d.get("fundType", d.get("fund_type", "")),
            "company": d.get("fundCompany", d.get("company", "")),
            "establish_date": d.get("establishDate", d.get("establish_date", "")),
            "manage_scale": d.get("fundSize", d.get("manage_scale", "")),
            "benchmark": d.get("benchmark", ""),
            "manager": d.get("managerName", d.get("manager", "")),
            "source": "qieman_mcp",
        }

    def get_fund_nav(self, fund_code: str, limit: int = 252) -> pd.DataFrame:
        """基金历史净值"""
        data = self._call_tool("BatchGetFundNavHistory", {"fundCodes": [fund_code]})
        nav_list = data.get("navList") if isinstance(data, dict) else None
        if not isinstance(nav_list, list) or not nav_list:
            return pd.DataFrame()
        df = pd.DataFrame(nav_list)
        # 列名兼容
        col_map = {
            "tradeDate": "date",
            "unitNav": "nav",
            "accumNav": "accum_nav",
            "dailyReturn": "daily_change",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        return df.tail(limit).reset_index(drop=True)

    def get_fund_performance(self, fund_code: str, period: str = "1y") -> Dict:
        """基金业绩表现"""
        data = self._call_tool("GetBatchFundPerformance", {"fundCodes": [fund_code]})
        funds = data.get("funds") if isinstance(data, dict) else None
        if not funds:
            return {}
        return funds[0] if isinstance(funds, list) else funds

    def get_holdings(self, fund_code: str, date: Optional[str] = None) -> pd.DataFrame:
        """十大重仓：通过 BatchGetFundsDetail 解析"""
        data = self._call_tool("BatchGetFundsDetail", {"fundCodes": [fund_code]})
        funds = data.get("funds") if isinstance(data, dict) else None
        if not funds:
            return pd.DataFrame()
        d = funds[0] if isinstance(funds, list) else funds
        holdings = d.get("holdings") or d.get("topHoldings") or d.get("stockHoldings")
        if not isinstance(holdings, list):
            return pd.DataFrame()
        df = pd.DataFrame(holdings)
        # 列名兼容
        col_map = {
            "stockCode": "code",
            "stockName": "name",
            "ratio": "ratio",
            "holdRatio": "ratio",
            "marketValue": "market_value",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        return df

    def get_industry_allocation(self, fund_code: str, date: Optional[str] = None) -> pd.DataFrame:
        """行业配置"""
        data = self._call_tool("getFundIndustryAllocation", {"fundCode": fund_code})
        industries = data.get("industryAllocation") if isinstance(data, dict) else None
        if not isinstance(industries, list):
            return pd.DataFrame()
        df = pd.DataFrame(industries)
        col_map = {
            "industryName": "industry",
            "industryCode": "industry_code",
            "ratio": "ratio",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        return df

    def get_asset_allocation(self, fund_code: str, date: Optional[str] = None) -> pd.DataFrame:
        """资产配置"""
        data = self._call_tool("GetFundAssetClassAnalysis", {"fundCodes": [fund_code]})
        allocation = data.get("assetAllocation") if isinstance(data, dict) else None
        if not isinstance(allocation, list):
            return pd.DataFrame()
        return pd.DataFrame(allocation)

    def analyze_portfolio(self, holdings: List[Dict]) -> Dict:
        """组合分析，优先且慢 MCP"""
        # holdings: [{"code": "000001", "weight": 0.3}, ...]
        # 转换为且慢需要的金额格式：需要基金净值才能换算金额
        codes = [h["code"] for h in holdings]
        data = self._call_tool("DiagnoseFundPortfolio", {"fundCodes": codes})
        if data:
            data["data_source"] = "qieman_mcp"
        return data or {}


# ------------------------------------------------------------------------------
# P2: AKShare 基金数据层
# ------------------------------------------------------------------------------

class AKShareProvider:
    """AKShare 基金数据提供层，作为天天基金失效后的兜底。"""

    def __init__(self):
        self._ak = None
        try:
            import akshare as ak
            self._ak = ak
        except ImportError:
            print("  [AKShare] 未安装，跳过。运行: pip install akshare")

    def available(self) -> bool:
        return self._ak is not None

    def _year_to_date(self, year: str, quarter: Optional[int] = None) -> str:
        """将 2024 或 2024Q3 转换为 AKShare 需要的报告期字符串"""
        if quarter:
            month_day = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
            return f"{year}-{month_day[quarter]}"
        return f"{year}-12-31"

    def get_fund_info(self, fund_code: str) -> Dict:
        if not self._ak:
            return {}
        try:
            df = self._ak.fund_name_em()
            row = df[df["基金代码"] == fund_code]
            if row.empty:
                return {}
            return {
                "fund_code": fund_code,
                "fund_name": str(row.iloc[0].get("基金简称", "")),
                "fund_type": str(row.iloc[0].get("基金类型", "")),
                "source": "akshare",
            }
        except Exception as e:
            print(f"  [AKShare] get_fund_info 失败: {e}")
            return {}

    def get_fund_nav(self, fund_code: str, years: int = 3) -> pd.DataFrame:
        if not self._ak:
            return pd.DataFrame()
        try:
            df = self._ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
            df = df.rename(columns={"净值日期": "date", "单位净值": "nav", "累计净值": "accum_nav"})
            df["date"] = pd.to_datetime(df["date"])
            start_date = datetime.now() - timedelta(days=365 * years)
            df = df[df["date"] >= start_date].sort_values("date").reset_index(drop=True)
            return df
        except Exception as e:
            print(f"  [AKShare] get_fund_nav 失败: {e}")
            return pd.DataFrame()

    def get_holdings(self, fund_code: str, date: Optional[str] = None) -> pd.DataFrame:
        if not self._ak:
            return pd.DataFrame()
        try:
            # 默认取最近一年报告期
            if not date:
                date = str(datetime.now().year)
            df = self._ak.fund_portfolio_hold_em(symbol=fund_code, date=date)
            df = df.rename(columns={
                "股票代码": "code",
                "股票名称": "name",
                "占净值比例": "ratio",
                "持股数": "shares",
                "持仓市值": "market_value",
                "季度": "quarter",
            })
            df["ratio"] = pd.to_numeric(df["ratio"], errors="coerce")
            # 取最新一期前十大
            if "quarter" in df.columns and not df.empty:
                latest = df["quarter"].iloc[-1]
                df = df[df["quarter"] == latest].reset_index(drop=True)
            return df
        except Exception as e:
            print(f"  [AKShare] get_holdings 失败: {e}")
            return pd.DataFrame()

    def get_industry_allocation(self, fund_code: str, date: Optional[str] = None) -> pd.DataFrame:
        if not self._ak:
            return pd.DataFrame()
        try:
            if not date:
                date = str(datetime.now().year)
            df = self._ak.fund_portfolio_industry_allocation_em(symbol=fund_code, date=date)
            df = df.rename(columns={"行业类别": "industry", "占净值比例": "ratio"})
            df["ratio"] = pd.to_numeric(df["ratio"], errors="coerce")
            if "季度" in df.columns and not df.empty:
                latest = df["季度"].iloc[-1]
                df = df[df["季度"] == latest].reset_index(drop=True)
            return df
        except Exception as e:
            print(f"  [AKShare] get_industry_allocation 失败: {e}")
            return pd.DataFrame()

    def get_asset_allocation(self, fund_code: str, date: Optional[str] = None) -> pd.DataFrame:
        if not self._ak:
            return pd.DataFrame()
        try:
            if not date:
                date = str(datetime.now().year)
            df = self._ak.fund_portfolio_asset_allocation_em(symbol=fund_code, date=date)
            df = df.rename(columns={"项目": "asset", "数值": "ratio"})
            return df
        except Exception as e:
            print(f"  [AKShare] get_asset_allocation 失败: {e}")
            return pd.DataFrame()


# ------------------------------------------------------------------------------
# P3: Wind / Choice 占位层
# ------------------------------------------------------------------------------

class WindProvider:
    """
    Wind/Choice/iFinD 终端数据占位层。
    当前仅做提示，未来可接入 WindPy / iFinD API。
    """

    def __init__(self):
        self._wind = None

    def available(self) -> bool:
        return False

    def _not_impl(self, method: str):
        print(f"  [Wind/Choice] {method} 未接入，请在有终端账号后扩展 WindProvider")
        return {} if "info" in method else pd.DataFrame()

    def get_fund_info(self, fund_code: str) -> Dict:
        return self._not_impl("get_fund_info")

    def get_fund_nav(self, fund_code: str, years: int = 3) -> pd.DataFrame:
        return self._not_impl("get_fund_nav")

    def get_holdings(self, fund_code: str, date: Optional[str] = None) -> pd.DataFrame:
        return self._not_impl("get_holdings")

    def get_industry_allocation(self, fund_code: str, date: Optional[str] = None) -> pd.DataFrame:
        return self._not_impl("get_industry_allocation")

    def get_asset_allocation(self, fund_code: str, date: Optional[str] = None) -> pd.DataFrame:
        return self._not_impl("get_asset_allocation")


# ------------------------------------------------------------------------------
# 统一入口：FundDataProvider
# ------------------------------------------------------------------------------

class FundDataProvider:
    """
    R9 基金数据统一入口。
    按「且慢 MCP → 天天基金 → AKShare → Wind」顺序尝试，自动降级。
    """

    def __init__(
        self,
        qieman_api_key: Optional[str] = None,
        enable_qieman: bool = True,
        enable_eastmoney: bool = True,
        enable_akshare: bool = True,
        enable_wind: bool = False,
    ):
        self.qieman = QiemanMCPProvider(qieman_api_key) if enable_qieman else None
        self.eastmoney = EastMoneyFetcher() if enable_eastmoney else None
        self.akshare = AKShareProvider() if enable_akshare else None
        self.wind = WindProvider() if enable_wind else None

    # ---- 内部 fallback 工具 ----

    def _try_providers(self, method: str, fund_code: str, *args, **kwargs):
        """
        按优先级尝试各数据源的同名方法，返回第一个非空结果。
        返回元组 (result, source_name)。
        """
        providers = [
            ("qieman_mcp", self.qieman),
            ("eastmoney", self.eastmoney),
            ("akshare", self.akshare),
            ("wind", self.wind),
        ]
        for source_name, provider in providers:
            if provider is None or not getattr(provider, "available", lambda: True)():
                continue
            try:
                result = getattr(provider, method)(fund_code, *args, **kwargs)
                # DataFrame 判空
                if isinstance(result, pd.DataFrame):
                    if not result.empty:
                        _log_source(source_name, method, fund_code)
                        return result, source_name
                # dict 判空
                elif isinstance(result, dict):
                    if result:
                        _log_source(source_name, method, fund_code)
                        return result, source_name
            except Exception as e:
                print(f"  [FundData] {source_name}.{method} 异常: {e}")
                continue
        return (pd.DataFrame() if method in ("get_fund_nav", "get_holdings",
                                               "get_industry_allocation", "get_asset_allocation") else {}), None

    # ---- 公开接口 ----

    def get_fund_info(self, fund_code: str) -> Dict:
        """获取基金基本信息"""
        info, source = self._try_providers("get_fund_info", fund_code)
        if source:
            info.setdefault("fund_code", fund_code)
            info.setdefault("data_source", source)
        return info

    def get_nav_history(self, fund_code: str, years: int = 3) -> pd.DataFrame:
        """获取历史净值"""
        # 且慢 MCP 用 limit 参数，其他用 years 参数
        if self.qieman and self.qieman.available():
            try:
                limit = int(years * 252)
                df = self.qieman.get_fund_nav(fund_code, limit=limit)
                if not df.empty:
                    _log_source("qieman_mcp", "get_nav_history", fund_code)
                    return df
            except Exception as e:
                print(f"  [FundData] qieman_mcp.get_nav_history 异常: {e}")
        df, source = self._try_providers("get_fund_nav", fund_code, years)
        if source:
            df["data_source"] = source
        return df

    def get_holdings(self, fund_code: str) -> pd.DataFrame:
        """获取最新十大重仓股"""
        df, source = self._try_providers("get_holdings", fund_code)
        if source:
            df["data_source"] = source
        return df

    def get_industry_allocation(self, fund_code: str) -> pd.DataFrame:
        """获取行业配置"""
        df, source = self._try_providers("get_industry_allocation", fund_code)
        if source:
            df["data_source"] = source
        return df

    def get_asset_allocation(self, fund_code: str) -> pd.DataFrame:
        """获取资产配置（股票/债券/现金占比）"""
        df, source = self._try_providers("get_asset_allocation", fund_code)
        if source:
            df["data_source"] = source
        return df

    def get_manager_info(self, fund_code: str) -> Dict:
        """获取基金经理信息（目前仅天天基金提供）"""
        if self.eastmoney:
            try:
                info = self.eastmoney.get_manager_detail(fund_code)
                if info:
                    _log_source("eastmoney", "get_manager_info", fund_code)
                    info["data_source"] = "eastmoney"
                    return info
            except Exception as e:
                print(f"  [FundData] eastmoney.get_manager_info 异常: {e}")
        return {"fund_code": fund_code, "data_source": None}

    def get_performance(self, fund_code: str, nav_df: Optional[pd.DataFrame] = None) -> Dict:
        """基于净值计算各周期业绩表现"""
        if nav_df is None or nav_df.empty:
            nav_df = self.get_nav_history(fund_code, years=3)
        if self.eastmoney:
            return self.eastmoney.get_performance(fund_code, nav_df)
        return {}

    def analyze_portfolio(self, holdings: List[Dict]) -> Dict:
        """组合分析，优先且慢 MCP"""
        if self.qieman and self.qieman.available():
            result = self.qieman.analyze_portfolio(holdings)
            if result:
                result["data_source"] = "qieman_mcp"
                return result
        print("  [FundData] analyze_portfolio 暂只支持且慢 MCP")
        return {}


# ------------------------------------------------------------------------------
# CLI 简单测试
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="R9 基金数据统一获取层测试")
    parser.add_argument("fund_code", help="基金代码，如 000001")
    parser.add_argument("--no-qieman", action="store_true", help="禁用且慢 MCP")
    parser.add_argument("--no-eastmoney", action="store_true", help="禁用天天基金")
    parser.add_argument("--no-akshare", action="store_true", help="禁用 AKShare")
    args = parser.parse_args()

    provider = FundDataProvider(
        enable_qieman=not args.no_qieman,
        enable_eastmoney=not args.no_eastmoney,
        enable_akshare=not args.no_akshare,
    )

    print(f"\n测试基金: {args.fund_code}")
    print("-" * 60)

    info = provider.get_fund_info(args.fund_code)
    print("基本信息:", json.dumps(info, ensure_ascii=False, indent=2))

    nav = provider.get_nav_history(args.fund_code, years=1)
    print(f"\n历史净值: {len(nav)} 条")
    if not nav.empty:
        print(nav.tail(3).to_string(index=False))

    holdings = provider.get_holdings(args.fund_code)
    print(f"\n十大重仓: {len(holdings)} 条")
    if not holdings.empty:
        print(holdings.head(10).to_string(index=False))
