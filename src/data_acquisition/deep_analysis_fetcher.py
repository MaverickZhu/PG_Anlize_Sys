import akshare as ak
import pandas as pd
import requests
import baostock as bs
import json
from src.logger import logger
from datetime import datetime

# --- 核心工具：代码格式转换工厂 ---
def get_clean_code(stock_code):
    """返回纯数字代码: 300434"""
    if not stock_code: return ""
    return stock_code.lower().replace('sh', '').replace('sz', '').replace('.', '')

def get_market_type(clean_code):
    """判断市场类型: sh/sz/bj"""
    if clean_code.startswith('6'): return 'sh'
    if clean_code.startswith('0') or clean_code.startswith('3'): return 'sz'
    if clean_code.startswith('8') or clean_code.startswith('4'): return 'bj'
    return 'sz'

def to_baostock_code(stock_code):
    """转为 Baostock 格式: sz.300434"""
    clean = get_clean_code(stock_code)
    mkt = get_market_type(clean)
    return f"{mkt}.{clean}"

def to_tencent_code(stock_code):
    """转为 Tencent 格式: sz300434"""
    clean = get_clean_code(stock_code)
    mkt = get_market_type(clean)
    return f"{mkt}{clean}"

def to_eastmoney_web_code(stock_code):
    """转为 Eastmoney Web 格式: SZ300434 (必须大写)"""
    clean = get_clean_code(stock_code)
    mkt = get_market_type(clean)
    return f"{mkt.upper()}{clean}"

def to_eastmoney_secid(stock_code):
    """转为 Eastmoney SecID: 0.300434"""
    clean = get_clean_code(stock_code)
    mkt = get_market_type(clean)
    prefix = "1" if mkt == 'sh' else "0"
    return f"{prefix}.{clean}"

def to_eastmoney_code(stock_code):
    """转为 Eastmoney 格式: 300434.SZ"""
    clean = get_clean_code(stock_code)
    mkt = get_market_type(clean)
    return f"{clean}.{mkt.upper()}"

# --- 数据获取函数 ---

def fetch_individual_info(stock_code):
    """
    获取个股基本信息
    策略：Akshare -> Baostock (行业) + Tencent (市值/PE)
    """
    clean_code = get_clean_code(stock_code)
    info = {}
    
    # 1. Akshare
    try:
        df = ak.stock_individual_info_em(symbol=clean_code)
        for _, row in df.iterrows():
            info[row['item']] = row['value']
    except Exception:
        pass 

    # 2. 补全: 行业 (Baostock)
    if '行业' not in info or info['行业'] == '未知':
        try:
            lg = bs.login()
            if lg.error_code == '0':
                bs_code = to_baostock_code(stock_code) # sz.300434
                rs = bs.query_stock_industry(code=bs_code)
                if rs.error_code == '0' and rs.next():
                    row = rs.get_row_data()
                    if len(row) > 3 and row[3]:
                        info['行业'] = row[3]
            bs.logout()
        except Exception as e:
            logger.error(f"Baostock Industry Error: {e}")

    # 3. 补全: 市值/PE (Tencent HTTP)
    if '总市值' not in info or '市盈率(动)' not in info:
        try:
            tx_code = to_tencent_code(stock_code) # sz300434
            url = f"http://qt.gtimg.cn/q={tx_code}"
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                content = resp.content.decode('gbk', errors='ignore')
                if '="' in content:
                    data_str = content.split('="')[1].strip('";')
                    fields = data_str.split('~')
                    if len(fields) > 45:
                        if '总市值' not in info:
                            info['总市值'] = float(fields[45]) * 100000000 if fields[45] else 0
                        if '流通市值' not in info:
                            info['流通市值'] = float(fields[44]) * 100000000 if fields[44] else 0
                        if '市盈率(动)' not in info:
                            info['市盈率(动)'] = fields[39]
        except Exception as e:
            logger.error(f"Tencent Cap Error: {e}")

    return info

def fetch_stock_news(stock_code, limit=10):
    """
    获取新闻/公告
    策略：Akshare -> Eastmoney NP-Notice (HTTP)
    """
    clean_code = get_clean_code(stock_code)
    news_list = []
    
    # 1. Akshare
    try:
        df = ak.stock_news_em(symbol=clean_code)
        if not df.empty:
            for _, row in df.head(limit).iterrows():
                news_list.append({
                    'title': row.get('新闻标题', row.get('标题', '无标题')),
                    'time': row.get('发布时间', ''),
                    'url': row.get('新闻链接', row.get('url', '')),
                    'source': row.get('文章来源', '网络'),
                })
            return news_list
    except Exception:
        pass

    # 2. Eastmoney NP-Notice (HTTP Fallback)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "http://data.eastmoney.com/notices/"
        }
        url = "http://np-anotice-stock.eastmoney.com/api/security/ann"
        params = {
            "sr": -1, "page_size": limit, "page_index": 1, 
            "ann_type": "A", "client_source": "web", 
            "stock_list": clean_code 
        }
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()
        
        if data.get('data') and data.get('data').get('list'):
            for item in data['data']['list']:
                art_code = item.get('art_code')
                title = item.get('title_ch', item.get('title', '无标题'))
                date_str = item.get('notice_date', '')[:10]
                
                news_list.append({
                    'title': title,
                    'time': date_str,
                    'url': f"http://data.eastmoney.com/notices/detail/{clean_code}/{art_code}.html",
                    'source': '公司公告'
                })
    except Exception as e:
        logger.error(f"Eastmoney NP-Notice Error: {e}")

    return news_list

def fetch_top_holders(stock_code):
    """
    获取股东
    策略：Akshare -> Eastmoney Web HTTP (Ajax with Headers)
    """
    clean_code = get_clean_code(stock_code)
    
    # 1. Akshare
    try:
        df = ak.stock_share_hold_top_10_em(symbol=clean_code)
        if not df.empty:
            latest_date = df['报告期'].max()
            return df[df['报告期'] == latest_date][['股东名称', '持股数量', '持股比例', '增减', '报告期']].rename(columns={
                '股东名称': 'holder_name', '持股数量': 'hold_num', 
                '持股比例': 'hold_ratio', '增减': 'change'
            })
    except Exception:
        pass

    # 2. Eastmoney Web HTTP (The Golden Ticket with Referer)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "http://f10.eastmoney.com/"
        }
        em_code = to_eastmoney_web_code(stock_code) # SZ300434 (UPPERCASE)
        
        url = "http://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/ShareholderResearchAjax"
        params = {"code": em_code}
        
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()
        
        # Use Top 10 Circulating (sdltgd)
        if 'sdltgd' in data and data['sdltgd']:
            latest = data['sdltgd'][0] # Latest quarter
            report_date = latest['rq']
            holders = latest['sdltgd']
            
            records = []
            for item in holders:
                records.append({
                    'holder_name': item.get('gdmc'),
                    'hold_num': item.get('cgs'),
                    'hold_ratio': item.get('zltgbcgbl'),
                    'change': item.get('zj'),
                    '报告期': report_date
                })
            return pd.DataFrame(records)
            
    except Exception as e:
        logger.error(f"Eastmoney Holders Web Error: {e}")
        
    return pd.DataFrame()

def fetch_capital_flow_history(stock_code):
    """
    资金流向历史
    策略：Akshare -> Eastmoney HTTP (Push2)
    """
    clean_code = get_clean_code(stock_code)
    
    # 1. Akshare
    try:
        mkt = get_market_type(clean_code)
        df = ak.stock_individual_fund_flow(stock=clean_code, market=mkt)
        if not df.empty:
            df = df.rename(columns={
                '日期': 'date', '主力净流入-净额': 'main_net_inflow', 
                '超大单净流入-净额': 'super_net_inflow', '大单净流入-净额': 'large_net_inflow',
                '中单净流入-净额': 'medium_net_inflow', '小单净流入-净额': 'small_net_inflow'
            })
            df['date'] = pd.to_datetime(df['date'])
            return df.tail(60)
    except Exception:
        pass

    # 2. Eastmoney HTTP Fallback
    try:
        secid = to_eastmoney_secid(stock_code)
        url = "http://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        params = {
            "lmt": 60, "klt": 101, # Daily
            "fields1": "f1", "fields2": "f51,f52,f53,f54,f55,f56",
            "secid": secid
        }
        resp = requests.get(url, params=params, timeout=3)
        data = resp.json()
        if data.get('data') and data['data'].get('klines'):
            records = []
            for line in data['data']['klines']:
                # date, main, small, medium, large, super
                parts = line.split(',')
                records.append({
                    'date': parts[0],
                    'main_net_inflow': float(parts[1]),
                    # Others are not strictly mapped in this simple fallback but main is key
                })
            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date'])
            return df
    except Exception as e:
        logger.error(f"Capital Flow Fallback Error: {e}")
        
    return pd.DataFrame()
