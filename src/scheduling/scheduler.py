from apscheduler.schedulers.blocking import BlockingScheduler
from src.logger import logger

def daily_scan_job():
    """
    这是调度器将要运行的主要任务。
    
    在当前阶段，它只记录一条日志来证明其正在运行。
    在未来，它将触发完整的分析流程：
    1. 从数据库读取所有股票的最新K线数据。
    2. 对每只股票应用我们选定的策略（例如DMA策略）。
    3. 从策略结果中生成信号。
    4. 将产生的信号存入数据库或通过其他方式通知用户。
    """
    logger.info("SCHEDULER: ===> [JOB START] Daily scan job is running... <===")
    
    # --- 未来的业务逻辑将在这里实现 ---
    #
    # 示例:
    # 1. db = next(database.get_db())
    # 2. all_stocks = crud.get_all_stocks(db)
    # 3. for stock in all_stocks:
    # 4.    kline = crud.get_kline(db, stock.code)
    # 5.    strategy = DmaStrategy()
    # 6.    result_df = strategy.apply(kline)
    # 7.    signals = generate_signals_from_dataframe(result_df, stock.code, strategy.name)
    # 8.    crud.save_signals(db, signals)
    #
    
    logger.info("SCHEDULER: ===> [JOB END] Daily scan job finished. <===")


def start_scheduler():
    """
    初始化并启动 APScheduler。
    这是一个阻塞式调度器，意味着它会一直运行在前台，直到程序被手动停止。
    """
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    logger.info("调度器已成功初始化。")

    # 添加要调度的任务
    # 为了方便开发和测试，我们暂时设置为每分钟运行一次。
    # 在生产环境中，可以将其修改为每天固定时间运行，例如：
    # scheduler.add_job(daily_scan_job, 'cron', hour=16, minute=30, day_of_week='mon-fri')
    scheduler.add_job(daily_scan_job, 'interval', minutes=1, id='daily_scan_job')
    
    logger.info("任务 'daily_scan_job' 已被调度，将每分钟运行一次。")
    logger.info("调度器正在运行... 按下 Ctrl+C 可以退出。")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器已被手动停止。")
        scheduler.shutdown()

if __name__ == '__main__':
    # 该脚本可以被直接运行，以启动调度器。
    start_scheduler() 