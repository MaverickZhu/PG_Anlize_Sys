import redis
from src.config import config
from src.logger import logger

class WatchlistManager:
    """
    自选股管理器 (基于 Redis Set)
    """
    def __init__(self):
        self.redis_client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            decode_responses=True
        )
        self.key = "user:watchlist:default" # 默认用户的自选股Key

    def add_stock(self, stock_code: str):
        """添加股票到自选"""
        try:
            # 存入 Redis Set
            self.redis_client.sadd(self.key, stock_code)
            logger.info(f"Added {stock_code} to watchlist.")
            return True
        except Exception as e:
            logger.error(f"Failed to add stock: {e}")
            return False

    def remove_stock(self, stock_code: str):
        """从自选移除股票"""
        try:
            self.redis_client.srem(self.key, stock_code)
            logger.info(f"Removed {stock_code} from watchlist.")
            return True
        except Exception as e:
            logger.error(f"Failed to remove stock: {e}")
            return False

    def get_watchlist(self) -> list:
        """获取所有自选股代码"""
        try:
            stocks = self.redis_client.smembers(self.key)
            return list(stocks)
        except Exception as e:
            logger.error(f"Failed to get watchlist: {e}")
            return []

    def is_in_watchlist(self, stock_code: str) -> bool:
        """检查是否已收藏"""
        try:
            return self.redis_client.sismember(self.key, stock_code)
        except Exception as e:
            return False

# 单例实例
watchlist_manager = WatchlistManager()

