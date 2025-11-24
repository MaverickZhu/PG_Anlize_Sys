import time
import json
import redis
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session

from src.config import config
from src.logger import logger
from src.data_storage import database, crud

class PersistenceService:
    """
    数据持久化服务。
    负责定期将 Redis 中的实时行情数据同步（Upsert）到 PostgreSQL/TimescaleDB。
    """

    def __init__(self):
        # 连接 Redis
        try:
            self.redis_client = redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                db=config.REDIS_DB,
                decode_responses=True
            )
            self.redis_client.ping()
            logger.info("持久化服务: Redis 连接成功。")
        except Exception as e:
            logger.critical(f"持久化服务: Redis 连接失败: {e}")
            raise

        # 数据库会话工厂
        self.SessionLocal = database.SessionLocal

    def sync_to_db(self):
        """执行一次从 Redis 到 DB 的同步"""
        start_time = time.time()
        
        # 1. 获取 Redis 中所有行情 keys
        keys = self.redis_client.keys('quote:*')
        if not keys:
            logger.info("Redis 中暂无行情数据，跳过同步。")
            return

        # 2. 批量获取数据
        values = self.redis_client.mget(keys)
        
        kline_data = []
        for v in values:
            if not v: continue
            try:
                data = json.loads(v)
                # 数据转换: Redis JSON -> DB Schema
                # 注意: Redis 里的 time 是字符串 "2023-10-27 14:30:00"
                # 我们需要将其解析为 datetime 对象
                
                # 处理日期：对于日线表，关键是日期部分。
                # 如果我们希望每天只有一条记录不断更新，
                # 那么入库的时间应该统一为当天的某个时刻（如0点），或者保留最新时刻。
                # 为了方便 Upsert（根据 time, code 主键），我们需要确保同一天的时间戳是一致的。
                # 这里我们取交易日期的 00:00:00 作为主键的一部分。
                trade_time_str = data.get('time')
                if not trade_time_str: continue
                
                trade_dt = pd.to_datetime(trade_time_str)
                trade_date = trade_dt.normalize() # 截断到日，时间为 00:00:00
                
                item = {
                    'time': trade_date, # 复合主键之一
                    'code': data['code'], # 复合主键之一
                    'open': float(data['open']),
                    'high': float(data['high']),
                    'low': float(data['low']),
                    'close': float(data['price']), # 最新价作为收盘价
                    'volume': int(float(data['volume'])),
                    'turnover': float(data['turnover'])
                }
                kline_data.append(item)
            except Exception as e:
                # 忽略个别解析错误
                continue

        if not kline_data:
            return

        # 3. 写入数据库 (Upsert)
        db: Session = self.SessionLocal()
        try:
            crud.bulk_upsert_daily_kline(db, kline_data)
            elapsed = time.time() - start_time
            logger.info(f"持久化完成: 同步了 {len(kline_data)} 条记录，耗时 {elapsed:.2f}s。")
        except Exception as e:
            logger.error(f"持久化失败: {e}")
        finally:
            db.close()

    def run(self, interval: int = 60):
        """启动持久化循环"""
        logger.info(f"🚀 启动持久化服务 (每 {interval} 秒同步一次)...")
        try:
            while True:
                self.sync_to_db()
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("🛑 持久化服务已停止。")

if __name__ == '__main__':
    service = PersistenceService()
    # 每 10 秒同步一次 (测试用，生产环境可设为 60秒)
    service.run(interval=10)

