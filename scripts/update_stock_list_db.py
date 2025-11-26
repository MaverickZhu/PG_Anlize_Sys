import sys
import os

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_acquisition import data_fetcher
from src.logger import logger

if __name__ == "__main__":
    logger.info("手动触发数据库股票列表更新...")
    data_fetcher.update_stock_list_to_db()
    logger.info("手动更新完成。")
