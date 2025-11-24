from sqlalchemy.orm import Session
from src.data_storage import crud, database
from src.data_acquisition import data_fetcher
from src.logger import logger

def sync_all_stocks_and_kline():
    """
    同步所有A股的股票列表和它们的日线行情数据。
    这是一个核心的、完整的同步流程。
    """
    logger.info("========== 开始执行全量数据同步任务 ==========")

    # 1. 获取数据库会话
    db: Session = next(database.get_db())

    # 2. 获取所有股票列表
    stocks_df = data_fetcher.fetch_all_stock_list()
    if stocks_df.empty:
        logger.error("获取股票列表失败，无法继续同步。任务终止。")
        return

    total_stocks = len(stocks_df)
    logger.info(f"共获取到 {total_stocks} 只股票，将开始逐一处理。")

    # 3. 遍历每只股票，同步其信息和日K线数据
    for index, row in stocks_df.iterrows():
        stock_code = row['code']
        stock_name = row['name']
        
        # 构造一个临时的 market 和 ipo_date
        # TODO: 后续可以从更详细的数据源获取这些信息
        market = 'SH' if stock_code.startswith('6') else 'SZ'
        ipo_date = None # ak.stock_individual_info_em(symbol=stock_code.split('.')[0])['上市日期'].iloc[0]

        logger.info(f"--- [{index + 1}/{total_stocks}] 正在处理: {stock_code} {stock_name} ---")

        # 3.1 在 'stocks' 表中获取或创建记录
        crud.get_or_create_stock(db, stock_code=stock_code, stock_name=stock_name, market=market, ipo_date=ipo_date)

        # 3.2 获取该股票的日K线
        # 为了演示，我们可以先同步最近一年的数据，避免首次运行时间过长
        # start_date="20230101"
        kline_df = data_fetcher.fetch_stock_daily_kline(stock_code=stock_code)
        
        if kline_df.empty:
            logger.warning(f"未能获取 {stock_code} 的K线数据，跳过保存。")
            continue

        # 3.3 将DataFrame转换为字典列表，然后批量保存
        kline_data_list = kline_df.to_dict(orient='records')
        crud.bulk_save_daily_kline(db, kline_data=kline_data_list)

    logger.info("========== 全量数据同步任务执行完毕 ==========")


if __name__ == '__main__':
    # 提供一个直接运行此脚本的入口
    # 确保数据库已启动并初始化
    sync_all_stocks_and_kline() 