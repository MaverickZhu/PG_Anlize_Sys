from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from src.config import config
from src.logger import logger

# 这一步是关键：导入模型，以便 Base 可以注册它们
# from src.data_storage import models  <-- 移除此行以修复循环导入问题

# 1. 创建数据库引擎
#    - `create_engine` 是 SQLAlchemy 的核心，用于与数据库建立连接。
#    - `echo=False` 在生产环境中关闭详细的SQL日志，但在调试时可以设为True。
try:
    engine = create_engine(
        config.DATABASE_URI,
        echo=False
    )
    logger.info("数据库引擎创建成功。")
except Exception as e:
    logger.critical(f"数据库引擎创建失败: {e}")
    raise

# 2. 创建一个会话工厂 (Session Factory)
#    - `sessionmaker` 创建一个 Session 类的工厂。
#    - `autocommit=False` 和 `autoflush=False` 是推荐的默认设置，
#      这意味着你需要显式地调用 `db.commit()` 来保存更改。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
logger.info("数据库会话工厂创建成功。")

# 3. 创建一个声明性基类 (Declarative Base)
#    - 我们所有的数据模型类都将继承这个 Base 类。
Base = declarative_base()

def init_db():
    """
    初始化数据库。
    此函数会连接到数据库，并根据所有继承自 Base 的模型类创建对应的表。
    如果表已存在，不会重复创建。
    同时，它会尝试将 stock_daily_kline 表转换为 TimescaleDB 的超表。
    """
    try:
        logger.info("正在初始化数据库，准备创建数据表...")
        # `Base.metadata.create_all` 会检查并创建所有尚未存在的表
        Base.metadata.create_all(bind=engine)
        logger.info("数据表创建成功（或已存在）。")

        # --- TimescaleDB 超表转换 ---
        logger.info("正在尝试将 'stock_daily_kline' 转换为超表...")
        with engine.connect() as connection:
            try:
                # 尝试执行创建超表的SQL命令
                # IF NOT EXISTS 可以防止在表已经是超表时报错
                connection.execute(text("SELECT create_hypertable('stock_daily_kline', 'time', if_not_exists => TRUE);"))
                connection.commit()
                logger.info("'stock_daily_kline' 已成功转换为超表（或已是超表）。")
            except ProgrammingError as e:
                # 如果 TimescaleDB 扩展不存在，会抛出 ProgrammingError
                if 'function create_hypertable' in str(e).lower():
                    logger.warning("TimescaleDB扩展似乎未安装或未启用。'create_hypertable' 函数不存在。")
                    logger.warning("请在数据库中执行: CREATE EXTENSION IF NOT EXISTS timescaledb;")
                else:
                    logger.error(f"转换超表时发生SQL错误: {e}")
                    raise
            except Exception as e:
                logger.error(f"转换超表时发生未知错误: {e}")
                raise

        logger.info("数据库初始化流程完成。")

    except Exception as e:
        logger.error(f"数据库初始化过程中发生严重错误: {e}")
        raise

def get_db():
    """
    一个依赖注入函数，用于获取数据库会d话。
    它确保每个请求/操作都使用独立的会话，并在结束后正确关闭。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == '__main__':
    # 这个脚本可以直接运行来初始化数据库
    print("正在手动执行数据库初始化...")
    logger.info("正在手动执行数据库初始化...")
    # 在 __main__ 中导入，避免循环依赖问题
    from src.data_storage.models import Stock, StockDailyKline, SignalRecord
    init_db()
    print("数据库初始化流程执行完毕。") 