from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from src.logger import logger
from src.data_storage import database, crud
from src.data_acquisition import data_fetcher
from src.data_storage.watchlist_manager import watchlist_manager
from datetime import datetime, timedelta

def update_stock_list_job():
    """
    每日任务：更新A股股票列表到数据库。
    调用 data_fetcher 中的封装函数。
    通常在盘后或夜间运行 (e.g., 17:30)。
    """
    logger.info("SCHEDULER: [Start] Updating stock list database...")
    try:
        data_fetcher.update_stock_list_to_db()
        logger.info("SCHEDULER: [End] Stock list update task finished.")
    except Exception as e:
        logger.error(f"SCHEDULER: Error updating stock list: {e}")

def daily_sync_watchlist_job():
    """
    每日任务：同步自选股的日线历史数据。
    通常在收盘后运行 (e.g., 17:00)，确保数据库中有完整的日K线用于回测和分析。
    """
    logger.info("SCHEDULER: [Start] Syncing watchlist history...")
    try:
        watchlist = watchlist_manager.get_watchlist()
        if not watchlist:
            logger.info("SCHEDULER: Watchlist is empty, nothing to sync.")
            return

        db = next(database.get_db())
        
        # 同步最近 5 天的数据，以防遗漏
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d")
        
        for stock_code in watchlist:
            try:
                logger.info(f"SCHEDULER: Syncing {stock_code}...")
                df = data_fetcher.fetch_stock_daily_kline(stock_code, start_date=start_date, end_date=end_date)
                
                if not df.empty:
                    # 转换为 list of dicts
                    records = df.to_dict('records')
                    crud.bulk_upsert_daily_kline(db, records)
            except Exception as e:
                logger.error(f"SCHEDULER: Failed to sync {stock_code}: {e}")
                
        db.close()
        logger.info("SCHEDULER: [End] Watchlist sync completed.")

    except Exception as e:
        logger.error(f"SCHEDULER: Error syncing watchlist: {e}")

def daily_strategy_scan_job():
    """
    每日任务：扫描自选股，运行策略并保存信号。
    通常在数据同步后运行 (e.g., 17:30)。
    """
    logger.info("SCHEDULER: [Start] Running daily strategy scan...")
    from src.strategy_engine.composite_strategy import CompositeStrategy
    from src.signals.signal_generator import generate_signals_from_dataframe
    from src.notification import EmailNotifier
    
    try:
        watchlist = watchlist_manager.get_watchlist()
        if not watchlist:
            logger.info("SCHEDULER: Watchlist is empty, skipping scan.")
            return

        strategy = CompositeStrategy()
        db = next(database.get_db())
        
        all_signals = []
        
        # 获取足够长的历史数据以计算指标 (如300天)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=300)).strftime("%Y%m%d")
        today_str = datetime.now().strftime("%Y-%m-%d")

        for stock_code in watchlist:
            try:
                # 1. 获取历史K线
                df = data_fetcher.fetch_stock_daily_kline(stock_code, start_date=start_date, end_date=end_date)
                if df.empty:
                    continue
                    
                # 2. 运行策略
                result_df = strategy.apply(df)
                
                # 3. 检查今日信号
                # 注意：result_df 的索引可能是整数，也可能是时间，取决于 fetcher
                # 这里我们假设最后一行是最新的，并且时间是今天
                latest = result_df.iloc[-1]
                latest_date_str = str(latest['time']).split(' ')[0] # 提取日期部分
                
                # 只保存今天的信号
                if latest_date_str == today_str and latest['signal'] != 0:
                    logger.info(f"SCHEDULER: Found signal for {stock_code}: {latest['signal']}")
                    
                    signal_type = 'BUY' if latest['signal'] == 1 else 'SELL'
                    desc = latest.get('signal_desc', '')
                    
                    all_signals.append({
                        'time': latest['time'],
                        'code': stock_code,
                        'strategy_name': strategy.name,
                        'signal_type': signal_type,
                        'price': float(latest['close']),
                        'description': desc
                    })
                    
            except Exception as e:
                logger.error(f"SCHEDULER: Error scanning {stock_code}: {e}")

        # 4. 批量保存信号
        if all_signals:
            crud.save_signals(db, all_signals)
            logger.info(f"SCHEDULER: Saved {len(all_signals)} new signals.")
            
            # 5. 发送通知
            try:
                logger.info("SCHEDULER: Sending notification email...")
                notifier = EmailNotifier()
                notifier.send_signals_report(all_signals)
            except Exception as ne:
                logger.error(f"SCHEDULER: Failed to send notification: {ne}")
                
        else:
            logger.info("SCHEDULER: No new signals found today.")
            
        db.close()
        logger.info("SCHEDULER: [End] Strategy scan completed.")

    except Exception as e:
        logger.error(f"SCHEDULER: Error in strategy scan job: {e}")

def start_scheduler():
    """
    初始化并启动 APScheduler。
    """
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    logger.info("调度器已成功初始化。")

    # 1. 每日 17:30 更新股票列表
    # 在收盘后进行，以确保列表是最新的
    scheduler.add_job(
        update_stock_list_job, 
        CronTrigger(hour=17, minute=30),
        id='update_stock_list'
    )

    # 2. 每日 17:00 同步自选股数据
    scheduler.add_job(
        daily_sync_watchlist_job, 
        CronTrigger(hour=17, minute=0),
        id='sync_watchlist'
    )
    
    # 3. 每日 18:00 运行策略扫描 (推迟到列表更新后)
    scheduler.add_job(
        daily_strategy_scan_job,
        CronTrigger(hour=18, minute=0),
        id='strategy_scan'
    )
    
    logger.info("已添加定时任务: sync_watchlist (17:00), update_stock_list (17:30), strategy_scan (18:00)")
    logger.info("调度器正在运行... 按下 Ctrl+C 可以退出。")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器已被手动停止。")
        scheduler.shutdown()

if __name__ == '__main__':
    start_scheduler()
