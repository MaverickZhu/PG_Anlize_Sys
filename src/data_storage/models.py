from sqlalchemy import (Column, String, Date, TIMESTAMP, BIGINT,
                          Float, PrimaryKeyConstraint, Index, Text)
from sqlalchemy.sql import func
from .database import Base

class Stock(Base):
    """
    股票基础信息模型，对应 `stocks` 表。
    """
    __tablename__ = 'stocks'

    code = Column(String(16), primary_key=True, comment="股票代码，例如 '000001.SZ'")
    name = Column(String(32), nullable=False, comment="股票名称")
    market = Column(String(8), comment="所属交易所")
    ipo_date = Column(Date, comment="上市日期")
    status = Column(String(16), default='listed', comment="上市状态, e.g., 'listed', 'delisted'")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), comment="记录创建时间")
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), comment="记录更新时间")

    def __repr__(self):
        return f"<Stock(code='{self.code}', name='{self.name}')>"

class StockDailyKline(Base):
    """
    股票日线行情模型，对应 `stock_daily_kline` 表。
    这张表将被创建为 TimescaleDB 的超表 (Hypertable)。
    """
    __tablename__ = 'stock_daily_kline'

    time = Column(TIMESTAMP(timezone=True), nullable=False, comment="K线日期")
    code = Column(String(16), nullable=False, comment="股票代码")
    open = Column(Float, comment="开盘价")
    high = Column(Float, comment="最高价")
    low = Column(Float, comment="最低价")
    close = Column(Float, comment="收盘价")
    volume = Column(BIGINT, comment="成交量（股）")
    turnover = Column(Float, comment="成交额（元）")

    # 定义复合主键
    __table_args__ = (
        PrimaryKeyConstraint('time', 'code', name='pk_stock_daily_kline'),
    )

    def __repr__(self):
        return f"<StockDailyKline(time='{self.time}', code='{self.code}', close='{self.close}')>"

class SignalRecord(Base):
    """
    策略信号记录表，对应 `signal_records` 表。
    存储每次策略运行产生的关键信号（买入/卖出）。
    """
    __tablename__ = 'signal_records'

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="主键ID")
    time = Column(TIMESTAMP(timezone=True), nullable=False, comment="信号产生时间")
    code = Column(String(16), nullable=False, index=True, comment="股票代码")
    strategy_name = Column(String(64), nullable=False, comment="策略名称")
    signal_type = Column(String(16), nullable=False, comment="信号类型: BUY, SELL")
    price = Column(Float, comment="信号触发时的价格")
    description = Column(String(255), comment="信号详细描述")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), comment="记录创建时间")

    def __repr__(self):
        return f"<SignalRecord(time='{self.time}', code='{self.code}', type='{self.signal_type}')>"

class UserWatchlist(Base):
    """
    用户自选股表，对应 `user_watchlist` 表。
    支持持久化存储和未来分析。
    """
    __tablename__ = 'user_watchlist'

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    code = Column(String(16), nullable=False, unique=True, comment="股票代码")
    added_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), comment="加入时间")
    notes = Column(Text, nullable=True, comment="投资备注/标签")
    initial_price = Column(Float, nullable=True, comment="加入时的参考价格")
    
    # 索引，方便查询
    __table_args__ = (
        Index('idx_watchlist_added_at', 'added_at'),
    )

    def __repr__(self):
        return f"<UserWatchlist(code='{self.code}', added_at='{self.added_at}')>"
