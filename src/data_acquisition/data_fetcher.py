import pandas as pd
import akshare as ak
import baostock as bs
import requests
import json
import time
import os
from datetime import datetime, timedelta
import concurrent.futures
from src.logger import logger
from src.data_storage import database, crud

def update_stock_list_to_db():
    """
    更新数据库中的股票列表。
    优先从 Baostock 获取，失败则从本地 CSV 读取。
    """
    logger.info("开始更新数据库股票列表...")
    
    stock_list_df = pd.DataFrame()
    
    # 1. 尝试从 Baostock 获取
    lg = bs.login()
    if lg.error_code == '0':
        logger.info("Baostock 登录成功，尝试获取股票列表...")
        
        # 尝试回溯最近 30 天
        for i in range(30):
            query_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            logger.info(f"尝试查询日期: {query_date}")
            
            rs = bs.query_all_stock(day=query_date)
            if rs.error_code == '0':
                data_list = []
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())
                
                if data_list:
                    stock_list_df = pd.DataFrame(data_list, columns=rs.fields)
                    logger.info(f"成功从 Baostock 获取 {len(stock_list_df)} 只股票 (日期: {query_date})")
                    break
                else:
                    logger.warning(f"日期 {query_date} 无数据，尝试前一天...")
            else:
                logger.error(f"Baostock 查询失败: {rs.error_msg}")
        
        bs.logout()
    else:
        logger.error(f"Baostock 登录失败: {lg.error_msg}")

    # 2. 如果 Baostock 获取失败，尝试读取本地 CSV
    if stock_list_df.empty:
        csv_path = os.path.join("data", "all_stock_codes.csv")
        if os.path.exists(csv_path):
            logger.warning(f"Baostock 获取失败，转为读取本地文件: {csv_path}")
            stock_list_df = pd.read_csv(csv_path)
        else:
            logger.error("无法获取股票列表：Baostock 失败且本地 CSV 不存在。")
            return

    # 3. 写入数据库
    if not stock_list_df.empty:
        db = next(database.get_db())
        try:
            stocks_data = []
            for _, row in stock_list_df.iterrows():
                # 确保字段存在
                raw_code = row.get('code')
                # 关键修复: 去除代码中的点 (sh.600000 -> sh600000)
                code = raw_code.replace('.', '')
                
                name = row.get('code_name') or row.get('name') # 兼容不同来源的列名
                ipoDate = row.get('ipoDate')
                
                # 简单映射 market
                market = 'Unknown'
                if code.startswith('sh'):
                    market = 'SH'
                elif code.startswith('sz'):
                    market = 'SZ'
                elif code.startswith('bj'):
                    market = 'BJ'

                stocks_data.append({
                    'code': code,
                    'name': name,
                    'market': market,
                    'ipo_date': ipoDate if ipoDate else None
                })
            
            crud.bulk_save_stocks(db, stocks_data)
            logger.info("数据库股票列表更新完成。")
        except Exception as e:
            logger.error(f"更新数据库失败: {e}")
        finally:
            db.close()
    else:
        logger.error("股票列表为空，无法更新数据库。")

def fetch_all_stock_list() -> pd.DataFrame:
    """
    从本地数据库获取所有A股代码列表。
    """
    try:
        db = next(database.get_db())
        stocks = crud.get_all_stocks(db)
        db.close()
        
        if not stocks:
            logger.warning("数据库中没有股票列表数据，请先运行更新脚本。")
            return pd.DataFrame()
            
        data = []
        for stock in stocks:
            data.append({
                'code': stock.code,
                'name': stock.name
            })
            
        df = pd.DataFrame(data)
        logger.info(f"成功从数据库加载 {len(df)} 只股票代码。")
        return df
        
    except Exception as e:
        logger.error(f"从数据库获取股票列表失败: {e}")
        return pd.DataFrame()

def fetch_stock_spot_realtime(stock_code: str) -> dict:
    """
    获取单个股票的实时快照 (五档盘口等)。
    直接调用腾讯接口。
    """
    try:
        clean_code = stock_code.lower().replace('.sh', '').replace('.sz', '')
        if not (clean_code.startswith('sh') or clean_code.startswith('sz')):
            if stock_code.startswith('6'): clean_code = f"sh{clean_code}"
            else: clean_code = f"sz{clean_code}"
            
        url = f"http://qt.gtimg.cn/q={clean_code}"
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            content = resp.content.decode('gbk', errors='ignore')
            if '="' in content:
                data_str = content.split('="')[1].strip('";').strip()
                fields = data_str.split('~')
                if len(fields) > 40:
                    # 构造详细数据字典
                    return {
                        'code': clean_code,
                        'name': fields[1],
                        'price': float(fields[3]),
                        'open': float(fields[5]),
                        'high': float(fields[33]),
                        'low': float(fields[34]),
                        'change': float(fields[31]),
                        'change_pct': float(fields[32]),
                        'volume': float(fields[36]) * 100,
                        'turnover': float(fields[37]) * 10000,
                        'bid1': float(fields[9]), 'bid1_vol': float(fields[10])*100,
                        'bid2': float(fields[11]), 'bid2_vol': float(fields[12])*100,
                        'bid3': float(fields[13]), 'bid3_vol': float(fields[14])*100,
                        'bid4': float(fields[15]), 'bid4_vol': float(fields[16])*100,
                        'bid5': float(fields[17]), 'bid5_vol': float(fields[18])*100,
                        'ask1': float(fields[19]), 'ask1_vol': float(fields[20])*100,
                        'ask2': float(fields[21]), 'ask2_vol': float(fields[22])*100,
                        'ask3': float(fields[23]), 'ask3_vol': float(fields[24])*100,
                        'ask4': float(fields[25]), 'ask4_vol': float(fields[26])*100,
                        'ask5': float(fields[27]), 'ask5_vol': float(fields[28])*100,
                        'volume_ratio': float(fields[49]) if len(fields) > 49 and fields[49] else 0.0,
                    }
        return {}
    except Exception as e:
        logger.error(f"获取单股实时行情失败: {e}")
        return {}

def fetch_all_stock_spot_realtime() -> pd.DataFrame:
    """
    获取全市场实时行情快照。
    流程: 
    1. 使用 fetch_all_stock_list (Database) 获取代码表。
    2. 分批请求腾讯批量接口 (qt.gtimg.cn) 获取实时数据。
    """
    # 1. 获取代码
    stock_list_df = fetch_all_stock_list()
    if stock_list_df.empty:
        logger.error("无法获取股票代码列表，无法进行全市场扫描。")
        return pd.DataFrame()
    
    all_codes = stock_list_df['code'].tolist()
    # 关键修复：腾讯接口不支持带点的代码 (sh.600000 -> sh600000)
    all_codes = [code.replace('.', '') for code in all_codes]
    logger.info(f"准备扫描 {len(all_codes)} 只股票的实时行情 (腾讯接口)...")
    
    # 2. 分批请求腾讯接口
    # 腾讯接口 url: http://qt.gtimg.cn/q=sh600519,sz000001,...
    # 每批建议 80 个
    batch_size = 80
    chunks = [all_codes[i:i + batch_size] for i in range(0, len(all_codes), batch_size)]
    
    realtime_data = []
    
    def fetch_chunk(chunk_codes):
        try:
            codes_str = ','.join(chunk_codes)
            url = f"http://qt.gtimg.cn/q={codes_str}"
            # 腾讯简易接口不需要复杂 Header
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                # 解析返回文本 (GBK 编码)
                content = resp.content.decode('gbk', errors='ignore')
                # v_sh600519="1~贵州茅台~600519~1700.00~..."
                lines = content.strip().split(';')
                chunk_results = []
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    if '="' in line:
                        parts = line.split('="')
                        if len(parts) < 2: continue
                        
                        data_str = parts[1].strip('"')
                        fields = data_str.split('~')
                        if len(fields) < 40: continue
                        
                        # 解析字段
                        # 1: name, 2: code(无前缀), 3: price, 
                        # 31: change, 32: pct, 36: vol(手), 38: turnover_rate(%)
                        
                        raw_code = fields[2]
                        # 根据原始请求的前缀来补全，或者简单判断
                        # 这里 fields[2] 是纯数字 600519
                        if raw_code.startswith('6'): full_code = f"sh{raw_code}"
                        else: full_code = f"sz{raw_code}"
                        
                        try:
                            price = float(fields[3])
                            pct = float(fields[32])
                            vol = float(fields[36]) * 100 # 手 -> 股
                            turnover_rate = float(fields[38]) if fields[38] else 0.0
                            volume_ratio = float(fields[49]) if len(fields) > 49 and fields[49] else 0.0
                            
                            chunk_results.append({
                                'code': full_code,
                                'name': fields[1],
                                'price': price,
                                'pct_change': pct,
                                'volume': vol,
                                'turnover_rate': turnover_rate,
                                'volume_ratio': volume_ratio
                            })
                        except:
                            continue
                return chunk_results
        except Exception as e:
            # logger.debug(f"Chunk fetch failed: {e}")
            pass
        return []

    # 并发请求
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(fetch_chunk, chunk) for chunk in chunks]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                realtime_data.extend(res)
                
    if not realtime_data:
        logger.error("腾讯接口扫描未返回任何有效数据。")
        return pd.DataFrame()
        
    return pd.DataFrame(realtime_data)

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
    print("--- 测试 fetch_all_stock_spot_realtime (Database + Tencent) ---")
    # 注意：测试前确保数据库已填充数据
    spot_df = fetch_all_stock_spot_realtime()
    if not spot_df.empty:
        print(f"成功获取 {len(spot_df)} 条全市场数据，前5只如下:")
        print(spot_df.head())
        print("字段:", spot_df.columns)
    else:
        print("全市场行情获取失败 (可能是数据库为空)。")
