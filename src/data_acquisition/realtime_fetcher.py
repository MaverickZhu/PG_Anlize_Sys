import time
import json
import redis
import random
import requests
import pandas as pd
import akshare as ak
from datetime import datetime
from src.config import config
from src.logger import logger

class RealtimeDataFetcher:
    """
    实时行情获取器 (新浪财经版)。
    
    由于东方财富全量接口不可用，我们切换为使用新浪财经接口。
    策略：
    1. 获取全市场代码列表。
    2. 将代码分批（每批约80个）。
    3. 循环请求新浪接口并解析数据。
    4. 推送到 Redis。
    """

    def __init__(self, redis_host=None, redis_port=None, redis_db=None):
        """初始化并连接 Redis"""
        try:
            host = redis_host or config.REDIS_HOST
            port = redis_port or config.REDIS_PORT
            db = redis_db or config.REDIS_DB

            self.redis_client = redis.Redis(
                host=host, port=port, db=db, decode_responses=True
            )
            self.redis_client.ping()
            logger.info("成功连接到 Redis 服务器。")
            
            # 缓存股票代码列表，避免每次都重新获取
            self.all_stock_codes = []
            self._refresh_stock_list()

        except redis.ConnectionError as e:
            logger.critical(f"无法连接到 Redis: {e}")
            raise

    def _refresh_stock_list(self):
        """获取全市场A股代码列表"""
        try:
            logger.info("正在初始化/刷新全市场股票代码列表...")
            # 使用 ak.stock_info_a_code_name() 获取所有A股代码和名称
            # 这是一个比较基础的接口，通常比较稳定
            df = ak.stock_info_a_code_name()
            
            codes = []
            for code in df['code']:
                code = str(code)
                # 根据代码判断交易所前缀
                # 60, 68 开头 -> sh (沪市主板, 科创板)
                # 00, 30 开头 -> sz (深市主板, 创业板)
                # 北交所 (8x, 4x) 新浪接口支持可能不同，暂时跳过或需要测试 bj 前缀
                if code.startswith('6'):
                    codes.append(f"sh{code}")
                elif code.startswith('0') or code.startswith('3'):
                    codes.append(f"sz{code}")
                # 暂时忽略北交所，以免新浪接口报错
                
            self.all_stock_codes = codes
            logger.info(f"股票列表刷新完成，共 {len(codes)} 只股票 (已过滤北交所)。")
            
        except Exception as e:
            logger.error(f"刷新股票列表失败: {e}")
            # 尝试备用方案：如果 Akshare 获取失败，可以使用硬编码的测试列表，
            # 保证程序不崩溃，至少能跑通一部分
            if not self.all_stock_codes:
                logger.warning("使用备用测试列表启动...")
                self.all_stock_codes = ['sh600519', 'sz000001', 'sz300750', 'sh601318']

    def fetch_realtime_quotes(self):
        """
        分批获取全市场实时行情。
        """
        if not self.all_stock_codes:
            self._refresh_stock_list()

        # 每次处理 80 只股票 (防止URL过长)
        BATCH_SIZE = 80
        total_stocks = len(self.all_stock_codes)
        all_data = []
        
        start_time = time.time()
        
        # 使用 requests Session 以复用连接，提升速度
        session = requests.Session()
        session.headers.update({'Referer': 'http://finance.sina.com.cn/'})

        for i in range(0, total_stocks, BATCH_SIZE):
            batch_codes = self.all_stock_codes[i : i + BATCH_SIZE]
            try:
                data = self._fetch_batch_sina(session, batch_codes)
                all_data.extend(data)
            except Exception as e:
                logger.warning(f"批次 {i//BATCH_SIZE + 1} 获取失败: {e}")
                continue
            
            # 极短的停顿，防止被封
            # time.sleep(0.01) 

        elapsed = time.time() - start_time
        
        if not all_data:
            logger.warning("本轮未获取到任何有效行情数据。")
            return

        df = pd.DataFrame(all_data)
        logger.info(f"全市场轮询完成: 获取 {len(df)} 条数据, 耗时 {elapsed:.2f}s。正在推送...")
        
        self._push_to_redis(df)

    def _fetch_batch_sina(self, session, codes):
        """请求新浪接口并解析结果"""
        url = f"http://hq.sinajs.cn/list={','.join(codes)}"
        resp = session.get(url, timeout=3)
        
        results = []
        if resp.status_code != 200:
            return results

        # 解析响应文本
        # 格式: var hq_str_sh601006="大秦铁路,6.670,6.680,6.690,6.720,6.660,6.680,6.690,25328063,169344164.000,...";
        lines = resp.text.strip().split('\n')
        for line in lines:
            if not line or '=""' in line: # 忽略空数据
                continue
                
            try:
                # 提取代码
                eq_idx = line.find('=')
                code_with_prefix = line[11:eq_idx] # var hq_str_shxxxxxx
                
                # 提取数据部分
                data_str = line[eq_idx+2 : -2] # 去掉 =" 和 ";
                fields = data_str.split(',')
                
                if len(fields) < 30:
                    continue
                    
                # 构造数据字典
                # 0:名称, 1:开盘, 2:昨收, 3:最新, 4:最高, 5:最低
                item = {
                    'code': code_with_prefix[2:] + ('.SH' if code_with_prefix.startswith('sh') else '.SZ'), # 转换为 000001.SZ 格式
                    'name': fields[0],
                    'price': float(fields[3]),
                    'open': float(fields[1]),
                    'pre_close': float(fields[2]),
                    'high': float(fields[4]),
                    'low': float(fields[5]),
                    'volume': float(fields[8]), # 股数
                    'turnover': float(fields[9]), # 金额
                    'time': f"{fields[30]} {fields[31]}", # 日期 + 时间
                    
                    # --- 五档盘口 (Bid/Ask) ---
                    # 买盘 (Bid)
                    'bid1_vol': float(fields[10]), 'bid1': float(fields[11]),
                    'bid2_vol': float(fields[12]), 'bid2': float(fields[13]),
                    'bid3_vol': float(fields[14]), 'bid3': float(fields[15]),
                    'bid4_vol': float(fields[16]), 'bid4': float(fields[17]),
                    'bid5_vol': float(fields[18]), 'bid5': float(fields[19]),
                    
                    # 卖盘 (Ask)
                    'ask1_vol': float(fields[20]), 'ask1': float(fields[21]),
                    'ask2_vol': float(fields[22]), 'ask2': float(fields[23]),
                    'ask3_vol': float(fields[24]), 'ask3': float(fields[25]),
                    'ask4_vol': float(fields[26]), 'ask4': float(fields[27]),
                    'ask5_vol': float(fields[28]), 'ask5': float(fields[29]),
                }
                
                # 计算涨跌幅
                if item['pre_close'] > 0:
                    item['change_pct'] = round((item['price'] - item['pre_close']) / item['pre_close'] * 100, 2)
                else:
                    item['change_pct'] = 0.0
                    
                results.append(item)
                
            except Exception:
                continue
                
        return results

    def _push_to_redis(self, df: pd.DataFrame):
        """将行情数据写入 Redis"""
        pipe = self.redis_client.pipeline()
        count = 0
        for _, row in df.iterrows():
            key = f"quote:{row['code']}"
            # 转换为JSON字符串
            # 注意：Pandas Series 转 dict 后类型可能需要处理，这里简单处理
            data = row.to_dict()
            pipe.setex(key, 60, json.dumps(data))
            count += 1
        pipe.execute()
        logger.info(f"已推 {count} 条数据至Redis")

    def run(self, interval: int = 3):
        """启动服务"""
        logger.info(f"🚀 启动实时采集 (新浪源), PID: {pd.io.common.os.getpid()}")
        try:
            while True:
                self.fetch_realtime_quotes()
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("🛑 停止服务")

if __name__ == '__main__':
    fetcher = RealtimeDataFetcher()
    fetcher.run(interval=3)
