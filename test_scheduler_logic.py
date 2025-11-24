from src.scheduling.scheduler import update_stock_list_job, daily_sync_watchlist_job
from src.data_storage.watchlist_manager import watchlist_manager
from src.logger import logger

print("--- Testing Update Stock List Job ---")
# This might take a while if it fetches all stocks
# update_stock_list_job() 

print("\n--- Testing Daily Watchlist Sync Job ---")
# Ensure we have something in the watchlist
watchlist_manager.add_stock("sh600519") # MaoTai
watchlist_manager.add_stock("sz000001") # PingAn

try:
    daily_sync_watchlist_job()
    print("Sync job executed successfully (check logs for details).")
except Exception as e:
    print(f"Sync job failed: {e}")

