from sqlalchemy import (Column, String, Date, TIMESTAMP, BIGINT,
                          Float, PrimaryKeyConstraint, Index)
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

# 注意：将这张普通表转换为 TimescaleDB 超表的操作，通常需要在表创建后，
# 通过执行一条特殊的SQL命令来完成。我们可以在 `init_db` 中加入这个逻辑。
# SQL: SELECT create_hypertable('stock_daily_kline', 'time'); 