import redis
from typing import Set, List
from src.config import config
from src.logger import logger
from src.data_storage import database, crud, models

class WatchlistManager:
    def __init__(self):
        # Redis 连接
        self.redis_client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            decode_responses=True
        )
        self.key = "user:watchlist"
        
        # 初始化时，尝试从数据库同步一次，确保 Redis 是暖的
        # 这样重启应用后，自选股能自动从 DB 恢复到 Redis
        self._sync_from_db()

    def _sync_from_db(self):
        """
        从数据库加载数据到 Redis 缓存。
        """
        try:
            with database.SessionLocal() as db:
                items = crud.get_watchlist_items(db)
                codes = [item.code for item in items]
                
                if codes:
                    # 清空 Redis 并重新填充
                    # 使用 pipeline 保证原子性
                    pipe = self.redis_client.pipeline()
                    pipe.delete(self.key)
                    pipe.sadd(self.key, *codes)
                    pipe.execute()
                    logger.info(f"已从数据库恢复 {len(codes)} 个自选股到 Redis。")
                else:
                    # DB 为空，确保 Redis 也为空
                    self.redis_client.delete(self.key)
                    
        except Exception as e:
            logger.error(f"从数据库同步自选股失败: {e}")
            # 如果数据库连接失败，至少不要 crash，Redis 可能还有旧数据

    def add_stock(self, stock_code: str) -> bool:
        """
        添加自选股 (Write-Through: DB -> Redis)
        """
        if not stock_code:
            return False
            
        # 1. 写入数据库 (Source of Truth)
        try:
            with database.SessionLocal() as db:
                # 可以在这里添加获取当前价格的逻辑作为 initial_price，暂时先留空
                success = crud.add_watchlist_item(db, stock_code)
                if not success:
                    logger.warning(f"添加自选股到数据库失败: {stock_code}")
                    return False
        except Exception as e:
            logger.error(f"DB 操作异常: {e}")
            return False
            
        # 2. 写入 Redis (Cache)
        try:
            self.redis_client.sadd(self.key, stock_code)
            logger.info(f"已添加自选股: {stock_code}")
            return True
        except Exception as e:
            logger.error(f"Redis 操作异常: {e}")
            # 此时 DB 已有但 Redis 没有，数据不一致。
            # 下次重启或调用 _sync_from_db 会修复。
            return True # 只要 DB 成功，我们认为操作成功

    def remove_stock(self, stock_code: str) -> bool:
        """
        移除自选股 (Write-Through: DB -> Redis)
        """
        # 1. 移除数据库
        try:
            with database.SessionLocal() as db:
                crud.remove_watchlist_item(db, stock_code)
        except Exception as e:
            logger.error(f"DB 移除失败: {e}")
            return False
            
        # 2. 移除 Redis
        try:
            self.redis_client.srem(self.key, stock_code)
            logger.info(f"已移除自选股: {stock_code}")
            return True
        except Exception as e:
            logger.error(f"Redis 移除失败: {e}")
            return True

    def get_watchlist(self) -> Set[str]:
        """
        获取自选股列表 (Cache-Aside: Read Redis -> Fallback DB)
        """
        try:
            # 1. 尝试读 Redis
            members = self.redis_client.smembers(self.key)
            if members:
                return members
                
            # 2. 如果 Redis 为空，查 DB 确认一下
            # 注意：如果用户真的清空了自选股，Redis为空，DB也为空，这里会多查一次DB
            # 可以优化，但对于当前规模没问题
            with database.SessionLocal() as db:
                items = crud.get_watchlist_items(db)
                codes = {item.code for item in items}
                
                if codes:
                    # 回填 Redis
                    self.redis_client.sadd(self.key, *codes)
                    return codes
                else:
                    return set()
                    
        except Exception as e:
            logger.error(f"获取自选股失败: {e}")
            return set()

    def is_in_watchlist(self, stock_code: str) -> bool:
        """
        检查是否在自选股中
        """
        try:
            return self.redis_client.sismember(self.key, stock_code)
        except Exception as e:
            logger.error(f"检查自选股失败: {e}")
            return False

# 单例实例
watchlist_manager = WatchlistManager()
