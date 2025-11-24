import pandas as pd
import akshare as ak
import requests
import json
import time
from datetime import datetime
from src.logger import logger

def fetch_all_stock_list() -> pd.DataFrame:
    """
    使用 akshare 获取所有A股的股票列表。

    :return: 包含股票列表的 DataFrame，已对字段进行重命名以匹配数据库模型。
             返回的字段: ['code', 'name']
    """
    try:
        logger.info("正在从 akshare 获取所有A股股票列表...")
        # A股列表
        stock_list_sh = ak.stock_info_sh_a_code_name()
        stock_list_sz = ak.stock_info_sz_a_code_name()
        
        # 合并上海和深圳市场
        all_stocks = pd.concat([stock_list_sh, stock_list_sz], ignore_index=True)
        
        # 重命名字段以匹配我们的模型
        all_stocks.rename(columns={'证券代码': 'code', '证券简称': 'name'}, inplace=True)
        
        logger.info(f"成功获取到 {len(all_stocks)} 只A股股票。")
        return all_stocks[['code', 'name']]

    except Exception as e:
        logger.error(f"从 akshare 获取股票列表时发生错误: {e}")
        # 返回一个空的 DataFrame，让调用方可以安全处理
        return pd.DataFrame()

def fetch_stock_daily_kline(stock_code: str, start_date: str = "19900101", end_date: str = "20991231") -> pd.DataFrame:
    """
    使用腾讯接口获取单个股票的历史日K线数据 (前复权)。
    
    :param stock_code: 股票代码, 例如 "sh600519" 或 "000001.SZ"
    :param start_date: 开始日期, 格式 'YYYYMMDD' (腾讯接口主要按条数取，这里作为筛选条件)
    :param end_date: 结束日期, 格式 'YYYYMMDD'
    :return: DataFrame ['time', 'code', 'open', 'high', 'low', 'close', 'volume', 'turnover']
    """
    try:
        # 1. 处理代码格式 (腾讯需要 sh600519 格式)
        clean_code = stock_code.lower().replace('.sz', '').replace('.sh', '')
        if not (clean_code.startswith('sh') or clean_code.startswith('sz')):
            # 尝试推断
            if stock_code.startswith('6'): clean_code = f"sh{clean_code}"
            else: clean_code = f"sz{clean_code}"
            
        logger.debug(f"正在从腾讯源为股票 {clean_code} 获取日K线数据...")

        # 2. 请求腾讯日K接口 (默认获取最近 320 天，也可设更大)
        # param=code,day,,,count,qfq
        count = 320 
        url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={clean_code},day,,,{count},qfq"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        resp = requests.get(url, headers=headers, timeout=5)
        
        if resp.status_code != 200:
            logger.warning(f"腾讯接口请求失败: {resp.status_code}")
            return pd.DataFrame()

        data = resp.json()
        if 'data' not in data or clean_code not in data['data']:
            logger.warning(f"腾讯接口返回数据中未找到 {clean_code}")
            return pd.DataFrame()
            
        # 优先获取前复权数据 'qfqday'，如果没有则取 'day'
        stock_data = data['data'][clean_code]
        kline_list = stock_data.get('qfqday', stock_data.get('day', []))
        
        if not kline_list:
             logger.warning(f"未获取到 {clean_code} 的K线数据列表")
             return pd.DataFrame()

        # 3. 转换为 DataFrame
        # 腾讯数据格式: ['2023-01-03', '1727.000', '1730.010', '1738.000', '1708.000', '25342.000', ...]
        # Index: 0:Date, 1:Open, 2:Close, 3:High, 4:Low, 5:Volume
        records = []
        for item in kline_list:
            if len(item) < 6: continue
            
            records.append({
                'time': item[0],
                'open': float(item[1]),
                'close': float(item[2]),
                'high': float(item[3]),
                'low': float(item[4]),
                'volume': float(item[5]),
                'turnover': 0.0 # 腾讯接口此处不直接提供成交额，设为0或后续计算
            })
            
        df = pd.DataFrame(records)
        df['time'] = pd.to_datetime(df['time'])
        
        # 4. 增加 code 字段
        df['code'] = stock_code
        
        # 5. 按日期筛选 (虽然接口是取最近N条，但我们可以进一步过滤)
        s_date = pd.to_datetime(start_date)
        e_date = pd.to_datetime(end_date)
        mask = (df['time'] >= s_date) & (df['time'] <= e_date)
        df = df.loc[mask]
        
        # 6. 估算 turnover (可选，为了兼容性)
        # 简单的 close * volume * 100 (如果 volume 是手) 或者 close * volume (如果 volume 是股)
        # 腾讯的 volume 通常是手？不，根据之前测试 781552.000 对于平安银行日量，应该是手。
        # 但数据库模型期望 turnover 是金额。
        # 暂时只保证字段存在。
        
        logger.debug(f"成功获取并处理了 {len(df)} 条股票 {stock_code} 的K线数据。")
        
        required_columns = ['time', 'code', 'open', 'high', 'low', 'close', 'volume', 'turnover']
        return df[required_columns]

    except Exception as e:
        logger.error(f"为股票 {stock_code} 获取K线数据时发生错误: {e}")
        return pd.DataFrame()

def fetch_stock_minute_data(stock_code: str, period: str = '1') -> pd.DataFrame:
    """
    获取股票的分时数据 (分钟级)，直接调用腾讯/新浪接口以确保实时性和真实性。
    
    :param stock_code: 股票代码 (e.g., 'sh600519')
    :param period: 周期，目前仅支持 '1' (分时)
    :return: DataFrame ['time', 'open', 'high', 'low', 'close', 'volume']
    """
    try:
        # 1. 处理代码格式
        clean_code = stock_code.lower().replace('.sh', '').replace('.sz', '')
        if not (clean_code.startswith('sh') or clean_code.startswith('sz')):
            if stock_code.startswith('6'): clean_code = f"sh{clean_code}"
            else: clean_code = f"sz{clean_code}"
            
        logger.debug(f"正在从腾讯源获取 {clean_code} 的实时分时数据...")
        
        # 2. 请求腾讯分时接口 (非常稳定且包含今日实时数据)
        # 格式: ["HHMM price cum_volume avg_price", ...] 或者是列表形式，需兼容处理
        url = f"http://web.ifzq.gtimg.cn/appstock/app/minute/query?code={clean_code}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        resp = requests.get(url, headers=headers, timeout=3)
        
        if resp.status_code != 200:
            logger.warning(f"腾讯接口请求失败: {resp.status_code}")
            return pd.DataFrame()
            
        data = resp.json()
        # 解析路径: data -> [code] -> data -> data
        if clean_code not in data['data']:
             return pd.DataFrame()
             
        minute_data = data['data'][clean_code]['data']['data']
        
        # 3. 转换为 DataFrame
        records = []
        today_str = datetime.now().strftime('%Y-%m-%d')
        prev_vol = 0
        
        for item in minute_data:
            # 兼容性处理: 腾讯接口返回的 item 可能是字符串 "0930 10.55 100 ..." 也可能是列表
            if isinstance(item, str):
                fields = item.split(' ')
            else:
                fields = item
                
            if len(fields) < 3:
                continue
                
            time_str = fields[0] # HHMM
            price = float(fields[1])
            cum_vol = float(fields[2]) # 累计成交量 (手)
            
            # 转换时间 "0930" -> "2025-11-24 09:30:00"
            full_time_str = f"{today_str} {time_str[:2]}:{time_str[2:]}:00"
            
            # 计算当前分钟成交量
            vol = cum_vol - prev_vol
            prev_vol = cum_vol
            
            records.append({
                'time': full_time_str,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': vol * 100 # 转换为股数
            })
            
        df = pd.DataFrame(records)
        df['time'] = pd.to_datetime(df['time'])
        
        return df

    except Exception as e:
        logger.error(f"获取分时数据失败: {e}")
        return pd.DataFrame()

def fetch_stock_money_flow_realtime(stock_code: str) -> dict:
    """
    从东方财富 fflow K线接口获取实时当日累计资金流向数据。
    该接口返回当日每分钟的累计净流入，取最后一条即为当前实时净流入。
    
    :param stock_code: 股票代码 (e.g., 'sh600519')
    :return: dict 包含资金流向数据
    """
    try:
        # 1. 转换代码格式为东财 secid
        clean_code = stock_code.lower().replace('sh', '').replace('sz', '').replace('.', '')
        if stock_code.startswith('sh') or stock_code.startswith('6'):
            secid = f"1.{clean_code}"
        else:
            secid = f"0.{clean_code}"
            
        logger.debug(f"正在从东方财富 fflow 接口获取 {stock_code} ({secid}) 的实时资金流向...")
        
        # 2. 请求 fflow/kline 接口
        url = "http://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        params = {
            "lmt": "0",
            "klt": "1", # 1分钟级别
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "secid": secid
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        resp = requests.get(url, params=params, headers=headers, timeout=3)
        
        if resp.status_code != 200:
            return {}
            
        data = resp.json()
        if not data.get('data') or not data['data'].get('klines'):
            return {}
            
        # 3. 解析最后一条数据 (当前累计)
        # 格式: "时间,主力净流入,小单净流入,中单净流入,大单净流入,超大单净流入"
        last_record = data['data']['klines'][-1]
        fields = last_record.split(',')
        
        if len(fields) < 6:
            return {}
            
        # 注意: fflow 接口直接给出净流入，没有区分流入/流出总额
        # 字段顺序映射 (根据调试结果推断):
        # 0: time
        # 1: main_net (主力净流入)
        # 2: small_net (小单净流入)
        # 3: medium_net (中单净流入)
        # 4: large_net (大单净流入)
        # 5: super_large_net (超大单净流入)
        
        main_net = float(fields[1])
        small_net = float(fields[2])
        medium_net = float(fields[3])
        large_net = float(fields[4])
        super_large_net = float(fields[5])
        
        # 因为没有总流入流出，我们构造一个简化的 dict，前端需要适配
        # 假设 流入 = max(0, net), 流出 = max(0, -net) *这只是为了画图展示净额方向，并非真实总额*
        # 或者直接只展示净流入柱状图。
        
        result = {
            "main_net_inflow": main_net,
            "retail_net_inflow": small_net + medium_net,
            
            # 仅用于前端展示净流入方向，非真实成交总额
            "super_large_net": super_large_net,
            "large_net": large_net,
            "medium_net": medium_net,
            "small_net": small_net,
            
            # 标记这是净额数据模式
            "is_net_only": True 
        }
        
        return result

    except Exception as e:
        logger.error(f"获取实时资金流向失败: {e}")
        return {}

if __name__ == '__main__':
    # --- 测试代码 ---
    print("--- 测试 fetch_all_stock_list ---")
    all_stocks_df = fetch_all_stock_list()
    if not all_stocks_df.empty:
        print(f"成功获取 {len(all_stocks_df)} 只股票，前5只如下:")
        print(all_stocks_df.head())
        
        # 测试获取其中一只股票的K线
        test_stock_code = "000001.SZ" # 平安银行
        print(f"\n--- 测试 fetch_stock_daily_kline for {test_stock_code} ---")
        kline_data = fetch_stock_daily_kline(test_stock_code, start_date="20230101", end_date="20230131")
        if not kline_data.empty:
            print(f"成功获取 {len(kline_data)} 条K线数据，示例如下:")
            print(kline_data.head())
            print("数据类型:")
            print(kline_data.dtypes)
        else:
            print(f"未能获取到 {test_stock_code} 的K线数据。")
            
        # 测试分时数据
        print(f"\n--- 测试 fetch_stock_minute_data (腾讯源) for {test_stock_code} ---")
        minute_df = fetch_stock_minute_data("sz000001")
        if not minute_df.empty:
             print(minute_df.tail())
        else:
             print("分时数据获取失败")

    else:
        print("获取股票列表失败。")
