#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天天基金网数据获取模块
数据来源：fund.eastmoney.com / fundf10.eastmoney.com
用于 R9Alpha 评价报告数据补全
"""

import requests
import json
import re
import time
import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class EastMoneyFetcher:
    """天天基金网数据获取器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive',
        }
        self.session.headers.update(self.headers)
        self.last_request_time = 0
        self.min_interval = 0.3
        
    def _sleep(self):
        current = time.time()
        elapsed = current - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed + random.uniform(0.05, 0.2))
        self.last_request_time = time.time()
        
    def _get(self, url: str, params: dict = None, headers: dict = None, retry: int = 3) -> Optional[requests.Response]:
        """带重试的GET请求"""
        for i in range(retry):
            try:
                self._sleep()
                rh = self.session.headers.copy()
                if headers:
                    rh.update(headers)
                # 仅在调用者未指定 Referer 时使用默认随机值
                if 'Referer' not in rh:
                    rh['Referer'] = random.choice([
                        'https://fundf10.eastmoney.com/',
                        'https://fund.eastmoney.com/',
                        'https://data.fund.eastmoney.com/',
                    ])
                resp = self.session.get(url, params=params, headers=rh, timeout=20)
                resp.encoding = 'utf-8'
                if resp.status_code == 200:
                    return resp
                else:
                    time.sleep(1 + i)
            except Exception as e:
                print(f"  请求异常: {e}，第{i+1}次重试...")
                time.sleep(1 + i)
        return None

    # ------------------------------------------------------------------
    # 1. 基金基本信息
    # ------------------------------------------------------------------
    def get_basic_info(self, fund_code: str) -> Dict:
        """获取基金基本信息（名称、净值、日涨跌）"""
        url = f"https://fundgz.1234567.com.cn/js/{fund_code}.js"
        resp = self._get(url)
        if not resp:
            return {}
        try:
            m = re.search(r'jsonpgz\((\{.+?\})\);', resp.text, re.DOTALL)
            if m:
                d = json.loads(m.group(1))
                return {
                    'fund_code': fund_code,
                    'fund_name': d.get('name', ''),
                    'net_value': d.get('dwjz', ''),
                    'accum_value': d.get('ljjz', ''),
                    'daily_change_pct': d.get('gszzl', ''),
                    'estimate_value': d.get('gsz', ''),
                    'nav_date': d.get('jzrq', ''),
                }
        except Exception as e:
            print(f"  解析基本信息失败: {e}")
        return {}

    # ------------------------------------------------------------------
    # 2. F10 基础概况
    # ------------------------------------------------------------------
    def get_f10_overview(self, fund_code: str) -> Dict:
        """获取F10基础概况（规模、成立日、类型、经理、基准等）"""
        url = f"https://fund.eastmoney.com/f10/jbgk_{fund_code}.html"
        resp = self._get(url)
        if not resp:
            return {}
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            info = {'fund_code': fund_code}
            table = soup.find('table', {'class': 'info w790'})
            if table:
                for row in table.find_all('tr'):
                    cells = row.find_all(['th', 'td'])
                    for i in range(0, len(cells)-1, 2):
                        key = cells[i].text.strip()
                        val = cells[i+1].text.strip()
                        if '基金类型' in key:
                            info['fund_type'] = val
                        elif '成立日期' in key:
                            info['establish_date'] = val
                        elif '资产规模' in key:
                            info['manage_scale'] = val
                        elif '基金管理人' in key and '经理' not in key:
                            info['company'] = val
                        elif '基金经理' in key and '人' not in key:
                            info['manager'] = val
                        elif '业绩比较基准' in key:
                            info['benchmark'] = val
                        elif '管理费率' in key:
                            info['manage_fee'] = val
                        elif '托管费率' in key:
                            info['trustee_fee'] = val
            return info
        except Exception as e:
            print(f"  解析F10概况失败: {e}")
            return {'fund_code': fund_code}

    # ------------------------------------------------------------------
    # 3. 基金经理详情
    # ------------------------------------------------------------------
    def get_manager_detail(self, fund_code: str) -> Dict:
        """获取基金经理详细信息"""
        url = f"https://fundf10.eastmoney.com/jjjl_{fund_code}.html"
        resp = self._get(url)
        if not resp:
            return {}
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            info = {'fund_code': fund_code}
            
            # 从表格获取现任基金经理
            table = soup.find('table', {'class': 'w782'})
            if table:
                for row in table.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        start = cells[0].text.strip()
                        end = cells[1].text.strip()
                        name_cell = cells[2]
                        if '至今' in end:
                            link = name_cell.find('a')
                            info['manager_name'] = link.text.strip() if link else name_cell.text.strip()
                            info['manager_start'] = start
                            break
            
            # 任职回报
            text = resp.text
            m = re.search(r'任职回报[：:\s]*([-\d.]+)%', text)
            if m:
                info['tenure_return_pct'] = float(m.group(1))
            
            # 从业年限
            m = re.search(r'(\d+)年\s*(\d+)天', text)
            if m:
                info['tenure_years'] = f"{m.group(1)}年{m.group(2)}天"
            
            return info
        except Exception as e:
            print(f"  解析基金经理失败: {e}")
            return {'fund_code': fund_code}

    # ------------------------------------------------------------------
    # 4. 历史净值
    # ------------------------------------------------------------------
    def get_nav_history(self, fund_code: str, years: int = 3) -> pd.DataFrame:
        """获取历史净值数据"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * years)
        all_data = []
        page = 1
        page_size = 20
        max_pages = 100
        url = "https://api.fund.eastmoney.com/f10/lsjz"
        
        while page <= max_pages:
            params = {
                'fundCode': fund_code,
                'pageIndex': page,
                'pageSize': page_size,
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
            }
            headers = {'Referer': f'https://fundf10.eastmoney.com/jjjz_{fund_code}.html'}
            resp = self._get(url, params=params, headers=headers)
            if not resp:
                break
            try:
                data = resp.json()
                data_inner = data.get('Data')
                if not data_inner or not isinstance(data_inner, dict):
                    break
                items = data_inner.get('LSJZList', [])
                if not items or not isinstance(items, list):
                    break
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    try:
                        all_data.append({
                            'date': item.get('FSRQ', ''),
                            'nav': float(item.get('DWJZ', 0)) if item.get('DWJZ') else None,
                            'accum_nav': float(item.get('LJJZ', 0)) if item.get('LJJZ') else None,
                            'daily_change': float(item.get('JZZZL', 0)) if item.get('JZZZL') else None,
                        })
                    except:
                        continue
                # 检查是否还有更多数据
                if len(items) < page_size:
                    break
                page += 1
            except Exception as e:
                print(f"  解析净值失败: {e}")
                break
        
        df = pd.DataFrame(all_data)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
        return df

    # ------------------------------------------------------------------
    # 5. 业绩表现与排名
    # ------------------------------------------------------------------
    def get_performance(self, fund_code: str, nav_df: pd.DataFrame = None) -> Dict:
        """获取各周期业绩表现（从净值历史计算）"""
        perf = {}
        if nav_df is None or nav_df.empty:
            return perf
        
        nav = nav_df.copy().reset_index(drop=True)
        nav['nav'] = pd.to_numeric(nav['nav'], errors='coerce')
        nav = nav.dropna(subset=['nav'])
        if len(nav) < 30:
            return perf
        
        latest = nav['nav'].iloc[-1]
        
        def calc_return(days):
            if len(nav) < days + 1:
                return None
            past = nav['nav'].iloc[-(days+1)]
            return round((latest / past - 1) * 100, 2)
        
        periods = [
            ('1w', 5), ('1m', 21), ('3m', 63), ('6m', 126),
            ('1y', 252), ('2y', 504), ('3y', 756), ('5y', 1260),
        ]
        for key, days in periods:
            ret = calc_return(days)
            if ret is not None:
                perf[key] = {'return': ret, 'rank': None, 'percentile': None}
        
        # 成立来收益
        if len(nav) > 1:
            first = nav['nav'].iloc[0]
            perf['since'] = {'return': round((latest / first - 1) * 100, 2), 'rank': None, 'percentile': None}
        
        return perf

    # ------------------------------------------------------------------
    # 6. 持仓数据（十大重仓）
    # ------------------------------------------------------------------
    def get_holdings(self, fund_code: str) -> pd.DataFrame:
        """获取最新十大重仓股"""
        url = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
        params = {'type': 'jjcc', 'code': fund_code, 'topline': '10'}
        headers = {'Referer': f'https://fundf10.eastmoney.com/ccmx_{fund_code}.html'}
        resp = self._get(url, params=params, headers=headers)
        if not resp:
            return pd.DataFrame()
        try:
            m = re.search(r'var apidata=\{\s*content:"(.+?)",\s*arryear:', resp.text, re.DOTALL)
            if not m:
                return pd.DataFrame()
            html = m.group(1).replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            holdings = []
            for box in soup.find_all('div', {'class': 'box'})[:1]:
                label = box.find('label', {'class': 'left'})
                report_date = label.text.strip() if label else ''
                table = box.find('table', {'class': 'w782'})
                if table:
                    for row in table.find_all('tr')[1:]:
                        cells = row.find_all('td')
                        if len(cells) >= 7:
                            try:
                                ratio_text = cells[6].text.strip().replace('%', '') if len(cells) > 6 else ''
                                ratio = float(ratio_text) if ratio_text and ratio_text != '--' else None
                                shares_text = cells[7].text.strip().replace(',', '') if len(cells) > 7 else ''
                                market_text = cells[8].text.strip().replace(',', '') if len(cells) > 8 else ''
                                holdings.append({
                                    'report_date': report_date,
                                    'rank': int(cells[0].text.strip()),
                                    'stock_code': cells[1].text.strip(),
                                    'stock_name': cells[2].text.strip(),
                                    'ratio': ratio,
                                    'shares': shares_text,
                                    'market_value': market_text,
                                })
                            except:
                                continue
            return pd.DataFrame(holdings)
        except Exception as e:
            print(f"  解析持仓失败: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # 7. 行业配置
    # ------------------------------------------------------------------
    def get_industry_allocation(self, fund_code: str) -> pd.DataFrame:
        """获取行业配置"""
        url = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
        params = {'type': 'hytz', 'code': fund_code}
        resp = self._get(url, params=params)
        if not resp:
            return pd.DataFrame()
        try:
            m = re.search(r'var apidata=\{content:"(.+?)",\}', resp.text, re.DOTALL)
            if not m:
                return pd.DataFrame()
            html = m.group(1).replace('\\"', '"')
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            industries = []
            for box in soup.find_all('div', {'class': 'box'})[:1]:
                table = box.find('table', {'class': 'w782'})
                if table:
                    for row in table.find_all('tr')[1:]:
                        cells = row.find_all('td')
                        if len(cells) >= 3:
                            try:
                                industries.append({
                                    'industry': cells[0].text.strip(),
                                    'ratio': float(cells[1].text.strip().replace('%', '')),
                                    'change': float(cells[2].text.strip().replace('%', '')) if cells[2].text.strip() not in ['', '--'] else 0,
                                })
                            except:
                                continue
            return pd.DataFrame(industries)
        except Exception as e:
            print(f"  解析行业配置失败: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # 8. 资产配置
    # ------------------------------------------------------------------
    def get_asset_allocation(self, fund_code: str) -> pd.DataFrame:
        """获取资产配置（股票/债券/现金占比）"""
        url = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
        params = {'type': 'zcpz', 'code': fund_code}
        resp = self._get(url, params=params)
        if not resp:
            return pd.DataFrame()
        try:
            m = re.search(r'var apidata=\{content:"(.+?)",\}', resp.text, re.DOTALL)
            if not m:
                return pd.DataFrame()
            html = m.group(1).replace('\\"', '"').replace('\\n', '\n')
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            allocations = []
            table = soup.find('table', {'class': 'w782'})
            if table:
                headers = [th.text.strip() for th in table.find_all('tr')[0].find_all('td')]
                for row in table.find_all('tr')[1:]:
                    cells = row.find_all('td')
                    if len(cells) >= 5:
                        try:
                            allocations.append({
                                'report_date': cells[0].text.strip(),
                                'stock_ratio': float(cells[1].text.strip().replace('%', '')) if cells[1].text.strip() not in ['', '--'] else None,
                                'bond_ratio': float(cells[2].text.strip().replace('%', '')) if cells[2].text.strip() not in ['', '--'] else None,
                                'cash_ratio': float(cells[3].text.strip().replace('%', '')) if cells[3].text.strip() not in ['', '--'] else None,
                                'other_ratio': float(cells[4].text.strip().replace('%', '')) if cells[4].text.strip() not in ['', '--'] else None,
                            })
                        except:
                            continue
            return pd.DataFrame(allocations)
        except Exception as e:
            print(f"  解析资产配置失败: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # 9. 持有人结构
    # ------------------------------------------------------------------
    def get_holder_structure(self, fund_code: str) -> Dict:
        """获取持有人结构（机构/个人占比）"""
        # 该页面为 JS 动态加载，requests 无法直接获取
        # 如需此数据，建议使用 Wind/Choice 终端
        return {'fund_code': fund_code}

    # ------------------------------------------------------------------
    # 10. 风险指标计算（基于净值）
    # ------------------------------------------------------------------
    def calculate_risk_metrics(self, nav_df: pd.DataFrame) -> Dict:
        """从净值数据计算风险指标"""
        if nav_df.empty or len(nav_df) < 60:
            return {}
        df = nav_df.copy()
        df['nav'] = pd.to_numeric(df['nav'], errors='coerce')
        df = df.dropna(subset=['nav'])
        if len(df) < 60:
            return {}
        
        df['daily_ret'] = df['nav'].pct_change()
        ret = df['daily_ret'].dropna()
        
        # 年化波动率
        vol = ret.std() * np.sqrt(252) * 100
        
        # 最大回撤
        cum = (1 + ret.fillna(0)).cumprod()
        running_max = cum.expanding().max()
        dd = (cum - running_max) / running_max
        max_dd = dd.min() * 100
        
        # 回撤恢复天数
        recovery_days = self._calc_recovery_days(df)
        
        # 夏普比率 (Rf=2.5%)
        latest = df['nav'].iloc[-1]
        year_idx = max(0, len(df) - 252)
        year_ago = df['nav'].iloc[year_idx]
        ann_ret = (latest / year_ago - 1) * 100
        sharpe = (ann_ret - 2.5) / vol if vol > 0 else 0
        
        # 卡玛比率
        calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0
        
        # 月度胜率
        df['month'] = df['date'].dt.to_period('M')
        monthly = df.groupby('month')['nav'].agg(['first', 'last'])
        monthly['ret'] = (monthly['last'] / monthly['first'] - 1) * 100
        win_rate = (monthly['ret'] > 0).mean() * 100
        
        # 下行标准差 (目标收益=0)
        downside = ret[ret < 0]
        downside_std = downside.std() * np.sqrt(252) * 100 if len(downside) > 0 else 0
        
        # 索提诺比率
        sortino = (ann_ret - 2.5) / downside_std if downside_std > 0 else 0
        
        return {
            'annual_return': round(ann_ret, 2),
            'annual_volatility': round(vol, 2),
            'max_drawdown': round(max_dd, 2),
            'sharpe_ratio': round(sharpe, 2),
            'calmar_ratio': round(calmar, 2),
            'sortino_ratio': round(sortino, 2),
            'downside_std': round(downside_std, 2),
            'recovery_days': recovery_days,
            'monthly_win_rate': round(win_rate, 2),
            'up_month_avg': round(monthly[monthly['ret'] > 0]['ret'].mean(), 2),
            'down_month_avg': round(monthly[monthly['ret'] < 0]['ret'].mean(), 2),
        }
    
    def _calc_recovery_days(self, nav_df: pd.DataFrame) -> int:
        """计算最大回撤恢复天数"""
        df = nav_df.copy().reset_index(drop=True)
        df['cummax'] = df['nav'].cummax()
        df['dd'] = (df['nav'] - df['cummax']) / df['cummax']
        
        max_dd_idx = df['dd'].idxmin()
        if max_dd_idx <= 0 or max_dd_idx >= len(df) - 1:
            return None
        
        peak_value = df.loc[:max_dd_idx, 'nav'].max()
        post_dd = df.iloc[max_dd_idx:]
        recovery = post_dd[post_dd['nav'] >= peak_value]
        if recovery.empty:
            return None
        recovery_idx = recovery.index[0]
        return int(recovery_idx - max_dd_idx)

    # ------------------------------------------------------------------
    # 11. 规模变动
    # ------------------------------------------------------------------
    def get_scale_history(self, fund_code: str) -> pd.DataFrame:
        """获取基金规模历史"""
        url = f"https://fundf10.eastmoney.com/jjgg_{fund_code}.html"
        resp = self._get(url)
        if not resp:
            return pd.DataFrame()
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 规模数据一般在另一个接口，这里先尝试页面解析
            # 实际规模历史通常需要从季报数据提取
            # 简化处理：返回空，由调用方用本地数据
            return pd.DataFrame()
        except:
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # 兼容 FundDataProvider 的统一接口
    # ------------------------------------------------------------------
    def get_fund_info(self, fund_code: str) -> Dict:
        """统一接口：合并基本信息 + F10 概况"""
        info = self.get_basic_info(fund_code)
        f10 = self.get_f10_overview(fund_code)
        info.update(f10)
        info.setdefault('fund_code', fund_code)
        return info

    def get_fund_nav(self, fund_code: str, years: int = 3) -> pd.DataFrame:
        """统一接口：历史净值（get_nav_history 的别名）"""
        return self.get_nav_history(fund_code, years=years)

    # ------------------------------------------------------------------
    # 12. 整合获取所有数据
    # ------------------------------------------------------------------
    def fetch_all(self, fund_code: str) -> Dict:
        """获取基金完整数据（整合所有接口）"""
        print(f"\n{'='*60}")
        print(f"  🌐 从天天基金网补全数据: {fund_code}")
        print(f"{'='*60}")
        
        result = {'fund_code': fund_code, 'source': 'eastmoney.com'}
        
        # 1. 基本信息
        print("  [1/9] 获取基金基本信息...")
        result['basic_info'] = self.get_basic_info(fund_code)
        
        # 2. F10概况
        print("  [2/9] 获取F10基础概况...")
        f10 = self.get_f10_overview(fund_code)
        result['f10_overview'] = f10
        
        # 3. 基金经理
        print("  [3/9] 获取基金经理信息...")
        result['manager'] = self.get_manager_detail(fund_code)
        
        # 4. 净值历史（3年）
        print("  [4/9] 获取历史净值...")
        nav_df = self.get_nav_history(fund_code, years=3)
        result['nav_history'] = nav_df
        
        # 5. 业绩表现（从净值计算）
        print("  [5/9] 计算业绩表现...")
        result['performance'] = self.get_performance(fund_code, nav_df)
        
        # 6. 风险指标
        print("  [6/9] 计算风险指标...")
        if not nav_df.empty:
            result['risk_metrics'] = self.calculate_risk_metrics(nav_df)
        else:
            result['risk_metrics'] = {}
        
        # 7. 持仓数据
        print("  [7/9] 获取十大重仓...")
        result['holdings'] = self.get_holdings(fund_code)
        
        # 8. 行业配置
        print("  [8/9] 获取行业配置...")
        result['industry'] = self.get_industry_allocation(fund_code)
        
        # 9. 资产配置
        print("  [9/9] 获取资产配置...")
        result['asset_allocation'] = self.get_asset_allocation(fund_code)
        
        # 10. 持有人结构
        print("  [10/10] 获取持有人结构...")
        result['holder_structure'] = self.get_holder_structure(fund_code)
        
        print(f"\n  ✅ 天天基金数据补全完成！")
        print(f"{'='*60}\n")
        
        return result


# ----------------------------------------------------------------------
# 便捷函数：将天天基金数据转换为 R9Alpha 数据字典格式
# ----------------------------------------------------------------------
def eastmoney_to_r9alpha(eastmoney_data: Dict, fund_code: str) -> Dict:
    """将天天基金原始数据转换为 R9Alpha 评价底稿数据字典"""
    data = {
        'fund_code': fund_code,
        'fund_name': '',
        'manager': '',
        'manager_tenure': '',
        'awards': '',
        'fund_size': '',
        'established_date': '',
        'nav': '',
        'fund_type': '',
        'benchmark': '',
        'annual_return_ytd': '',
        'annual_return_1y': '',
        'annual_return_3y': '',
        'annual_return_5y': '',
        'annual_return_since': '',
        'return_1w': '',
        'return_1m': '',
        'return_3m': '',
        'return_6m': '',
        'rank_1y': '',
        'rank_3y': '',
        'rank_5y': '',
        'max_drawdown_3y': '',
        'annual_vol_3y': '',
        'sharpe_3y': '',
        'calmar_3y': '',
        'sortino_3y': '',
        'downside_std_3y': '',
        'tracking_error': '',
        'info_ratio': '',
        'excess_return': '',
        'excess_vol': '',
        'excess_sharpe': '',
        'recovery_days': '',
        'daily_win_rate': '',
        'monthly_win_rate': '',
        'up_month_avg': '',
        'down_month_avg': '',
        'top10_ratio': '',
        'turnover': '',
        'inst_ratio': '',
        'inst_change': '',
        'top3_sectors': '',
        'pe_ttm': '',
        'brinson': '',
        'market_analysis': '',
        'market_outlook': '',
        'r9alpha_score': '',
        'r9alpha_comment': '',
        'stock_ratio': '',
        'bond_ratio': '',
        'cash_ratio': '',
        'other_ratio': '',
    }
    
    # 基本信息
    basic = eastmoney_data.get('basic_info', {})
    f10 = eastmoney_data.get('f10_overview', {})
    data['fund_name'] = basic.get('fund_name') or f10.get('fund_name', '')
    data['fund_type'] = f10.get('fund_type', '')
    data['established_date'] = f10.get('establish_date', '')
    data['nav'] = f"{basic.get('net_value', '')}元 ({basic.get('nav_date', '')})"
    data['fund_size'] = f"{f10.get('manage_scale', '')}"
    data['benchmark'] = f10.get('benchmark', '')
    
    # 基金经理
    mgr = eastmoney_data.get('manager', {})
    data['manager'] = mgr.get('manager_name', f10.get('manager', ''))
    data['manager_tenure'] = mgr.get('tenure_years', '')
    if mgr.get('manager_start'):
        data['manager_tenure'] += f" (上任: {mgr.get('manager_start')})"
    
    # 业绩表现
    perf = eastmoney_data.get('performance', {})
    for key, r9key in [
        ('1w', 'return_1w'), ('1m', 'return_1m'), ('3m', 'return_3m'),
        ('6m', 'return_6m'), ('1y', 'annual_return_1y'),
        ('2y', 'annual_return_2y'), ('3y', 'annual_return_3y'),
        ('5y', 'annual_return_5y'), ('since', 'annual_return_since'),
    ]:
        if key in perf and perf[key].get('return') is not None:
            data[r9key] = f"{perf[key]['return']}%"
    
    # 排名
    if '1y' in perf:
        data['rank_1y'] = perf['1y'].get('rank', '')
    if '3y' in perf:
        data['rank_3y'] = perf['3y'].get('rank', '')
    if '5y' in perf:
        data['rank_5y'] = perf['5y'].get('rank', '')
    
    # 风险指标（天天基金计算）
    risk = eastmoney_data.get('risk_metrics', {})
    if risk:
        data['annual_return_3y_online'] = f"{risk.get('annual_return', '')}%"
        data['annual_vol_3y'] = f"{risk.get('annual_volatility', '')}%"
        data['max_drawdown_3y'] = f"{risk.get('max_drawdown', '')}%"
        data['sharpe_3y'] = risk.get('sharpe_ratio', '')
        data['calmar_3y'] = risk.get('calmar_ratio', '')
        data['sortino_3y'] = risk.get('sortino_ratio', '')
        data['downside_std_3y'] = f"{risk.get('downside_std', '')}%"
        data['recovery_days'] = f"{risk.get('recovery_days', '')}天"
        data['monthly_win_rate'] = f"{risk.get('monthly_win_rate', '')}%"
        data['up_month_avg'] = f"{risk.get('up_month_avg', '')}%"
        data['down_month_avg'] = f"{risk.get('down_month_avg', '')}%"
    
    # 持仓
    holdings = eastmoney_data.get('holdings', pd.DataFrame())
    if not holdings.empty:
        data['top10_ratio'] = f"{holdings['ratio'].sum():.2f}%"
        # 持仓明细文本
        data['holdings_detail'] = holdings.to_dict('records')
    
    # 行业配置
    industry = eastmoney_data.get('industry', pd.DataFrame())
    if not industry.empty:
        top3 = industry.nlargest(3, 'ratio')
        data['top3_sectors'] = '、'.join([f"{r['industry']}({r['ratio']:.2f}%)" for _, r in top3.iterrows()])
        data['industry_detail'] = industry.to_dict('records')
    
    # 资产配置
    asset = eastmoney_data.get('asset_allocation', pd.DataFrame())
    if not asset.empty:
        latest = asset.iloc[0]
        data['stock_ratio'] = f"{latest.get('stock_ratio', '')}%"
        data['bond_ratio'] = f"{latest.get('bond_ratio', '')}%"
        data['cash_ratio'] = f"{latest.get('cash_ratio', '')}%"
        data['other_ratio'] = f"{latest.get('other_ratio', '')}%"
    
    # 持有人结构
    holder = eastmoney_data.get('holder_structure', {})
    if holder.get('inst_ratio') is not None:
        data['inst_ratio'] = f"{holder['inst_ratio']}%"
    
    return data


if __name__ == '__main__':
    # 测试
    fetcher = EastMoneyFetcher()
    data = fetcher.fetch_all('519702')
    r9data = eastmoney_to_r9alpha(data, '519702')
    print("\n转换后的 R9Alpha 数据字典:")
    for k, v in r9data.items():
        if v and v != 'None' and v != 'None%':
            print(f"  {k}: {v}")
