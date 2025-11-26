from typing import List, Dict
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from . import models, database
from src.logger import logger

def get_or_create_stock(db: Session, stock_code: str, stock_name: str, market: str, ipo_date: pd.Timestamp):
    """
    根据股票代码获取或创建股票记录。
    如果股票已存在，则返回现有记录；如果不存在，则创建新记录。

    :param db: 数据库会话
    :param stock_code: 股票代码
    :param stock_name: 股票名称
    :param market: 交易所
    :param ipo_date: 上市日期
    :return: Stock ORM 对象
    """
    instance = db.query(models.Stock).filter(models.Stock.code == stock_code).first()
    if instance:
        return instance
    else:
        logger.debug(f"数据库中不存在股票 {stock_code}，正在创建新记录...")
        new_stock = models.Stock(
            code=stock_code,
            name=stock_name,
            market=market,
            ipo_date=ipo_date.date() if pd.notna(ipo_date) else None
        )
        db.add(new_stock)
        db.commit()
        db.refresh(new_stock)
        logger.info(f"成功创建新股票记录: {stock_code} - {stock_name}")
        return new_stock

def bulk_save_stocks(db: Session, stocks_data: List[dict]):
    """
    批量保存股票列表信息 (Upsert)。
    如果股票已存在，更新名称等信息。
    """
    if not stocks_data:
        return

    try:
        stmt = pg_insert(models.Stock).values(stocks_data)
        
        update_dict = {
            'name': stmt.excluded.name,
            'market': stmt.excluded.market
        }
        
        stmt = stmt.on_conflict_do_update(
            index_elements=['code'],
            set_=update_dict
        )
        
        db.execute(stmt)
        db.commit()
        logger.info(f"成功批量更新 {len(stocks_data)} 只股票信息。")

    except Exception as e:
        logger.error(f"批量保存股票信息失败: {e}")
        db.rollback()

def get_all_stocks(db: Session) -> List[models.Stock]:
    """
    获取数据库中所有股票的基础信息。
    """
    try:
        return db.query(models.Stock).all()
    except Exception as e:
        logger.error(f"获取所有股票失败: {e}")
        return []

def get_stock_names(db: Session, codes: List[str]) -> Dict[str, str]:
    """
    批量获取股票代码对应的名称。
    :param db:
    :param codes: 股票代码列表
    :return: 字典 {code: name}
    """
    if not codes:
        return {}
    try:
        results = db.query(models.Stock.code, models.Stock.name)\
            .filter(models.Stock.code.in_(codes)).all()
        return {row.code: row.name for row in results}
    except Exception as e:
        logger.error(f"获取股票名称失败: {e}")
        return {}

def bulk_save_daily_kline(db: Session, kline_data: List[dict]):
    """
    批量保存日线行情数据。
    使用 PostgreSQL 的 ON CONFLICT DO NOTHING 子句，
    如果主键（time, code）冲突，则忽略插入，避免重复数据。

    :param db: 数据库会话
    :param kline_data: 字典列表，每个字典代表一行k线数据
    """
    if not kline_data:
        logger.warning("尝试批量保存K线数据，但列表为空。")
        return

    try:
        # 使用 SQLAlchemy Core 的 insert() 结合 PostgreSQL 的 on_conflict_do_nothing
        stmt = pg_insert(models.StockDailyKline).values(kline_data)
        
        # ON CONFLICT DO NOTHING
        # 当 'pk_stock_daily_kline' (即 time 和 code 的复合主键) 冲突时，不执行任何操作。
        stmt = stmt.on_conflict_do_nothing(
            index_elements=['time', 'code']
        )
        
        db.execute(stmt)
        db.commit()
        logger.info(f"成功批量保存或忽略 {len(kline_data)} 条K线数据。")

    except Exception as e:
        logger.error(f"批量保存K线数据时发生错误: {e}")
        db.rollback()
        raise

def bulk_upsert_daily_kline(db: Session, kline_data: List[dict]):
    """
    批量更新或插入日线行情 (Upsert)。
    适用于实时数据持久化：如果记录存在（今天的数据），则更新价格和成交量。
    """
    if not kline_data:
        return

    try:
        stmt = pg_insert(models.StockDailyKline).values(kline_data)
        
        # 定义当主键冲突时需要更新的字段
        update_dict = {
            'open': stmt.excluded.open,
            'high': stmt.excluded.high,
            'low': stmt.excluded.low,
            'close': stmt.excluded.close,
            'volume': stmt.excluded.volume,
            'turnover': stmt.excluded.turnover
        }
        
        # DO UPDATE SET ...
        stmt = stmt.on_conflict_do_update(
            index_elements=['time', 'code'], # 复合主键
            set_=update_dict
        )
        
        db.execute(stmt)
        db.commit()
        logger.debug(f"成功刷新(Upsert) {len(kline_data)} 条实时K线数据。")

    except Exception as e:
        logger.error(f"批量UpsertK线数据错误: {e}")
        db.rollback()
        raise

def save_signals(db: Session, signals_data: List[dict]):
    """
    批量保存生成的交易信号。
    这里不做去重，因为同一天同一股票可能有不同策略的信号。
    
    :param db: 数据库会话
    :param signals_data: 字典列表
    """
    if not signals_data:
        return

    try:
        db.bulk_insert_mappings(models.SignalRecord, signals_data)
        db.commit()
        logger.info(f"成功保存 {len(signals_data)} 条策略信号。")
    except Exception as e:
        logger.error(f"保存策略信号失败: {e}")
        db.rollback()

def get_signal_records(db: Session, limit: int = 100) -> List[models.SignalRecord]:
    """
    获取最近的历史信号记录。
    
    :param db: 数据库会话
    :param limit: 返回记录的最大数量
    :return: SignalRecord 对象列表
    """
    try:
        # 按时间倒序排列
        signals = db.query(models.SignalRecord).order_by(models.SignalRecord.time.desc()).limit(limit).all()
        return signals
    except Exception as e:
        logger.error(f"查询信号记录失败: {e}")
        return []

def add_watchlist_item(db: Session, code: str, notes: str = None, initial_price: float = None):
    """
    添加自选股到数据库。
    如果已存在则忽略。
    """
    try:
        # 使用 upsert 或先查后插，这里简单用 upsert (do nothing on conflict)
        stmt = pg_insert(models.UserWatchlist).values(
            code=code,
            notes=notes,
            initial_price=initial_price
        )
        # 如果已存在，什么都不做 (或者可以更新 notes)
        stmt = stmt.on_conflict_do_nothing(index_elements=['code'])
        
        db.execute(stmt)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"添加自选股失败 {code}: {e}")
        db.rollback()
        return False

def remove_watchlist_item(db: Session, code: str):
    """
    从数据库删除自选股。
    """
    try:
        db.query(models.UserWatchlist).filter(models.UserWatchlist.code == code).delete()
        db.commit()
        return True
    except Exception as e:
        logger.error(f"删除自选股失败 {code}: {e}")
        db.rollback()
        return False

def get_watchlist_items(db: Session) -> List[models.UserWatchlist]:
    """
    获取所有自选股记录。
    """
    try:
        return db.query(models.UserWatchlist).all()
    except Exception as e:
        logger.error(f"获取自选股列表失败: {e}")
        return []
