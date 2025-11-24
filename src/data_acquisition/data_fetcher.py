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
    使用 akshare 获取单个股票的历史日K线数据。

    :param stock_code: 股票代码, 例如 "000001"
    :param start_date: 开始日期, 格式 'YYYYMMDD'
    :param end_date: 结束日期, 格式 'YYYYMMDD'
    :return: 包含日K线数据的 DataFrame，已对字段进行清理和重命名。
    """
    try:
        logger.debug(f"正在为股票 {stock_code} 获取从 {start_date} 到 {end_date} 的日K线数据...")
        # Akshare 的 stock_zh_a_hist 需要不带后缀的代码
        code_for_ak = stock_code.split('.')[0]
        
        kline_df = ak.stock_zh_a_hist(symbol=code_for_ak, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        
        if kline_df.empty:
            logger.warning(f"未能获取到股票 {stock_code} 的K线数据，可能该代码或日期范围有误。")
            return pd.DataFrame()

        # --- 数据清洗和格式化 ---
        # 1. 重命名字段以匹配数据库模型
        kline_df.rename(columns={
            '日期': 'time',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
            '成交额': 'turnover'
        }, inplace=True)

        # 2. 增加 'code' 字段，值为完整的股票代码
        kline_df['code'] = stock_code

        # 3. 转换 'time' 字段为带时区的时间戳
        kline_df['time'] = pd.to_datetime(kline_df['time']).dt.tz_localize('Asia/Shanghai')

        logger.debug(f"成功获取并处理了 {len(kline_df)} 条股票 {stock_code} 的K线数据。")
        
        # 4. 只选择我们需要的字段
        required_columns = ['time', 'code', 'open', 'high', 'low', 'close', 'volume', 'turnover']
        return kline_df[required_columns]

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
