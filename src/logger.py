import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from src.config import config

# --- Logger Configuration ---

# 1. 从配置模块获取日志级别和文件路径
LOG_LEVEL = config.LOG_LEVEL
LOG_FILE_PATH = config.LOG_FILE_PATH

# 2. 确保日志文件所在的目录存在
# 这是很关键的一步，否则在初次运行时会因为目录不存在而报错
log_dir = os.path.dirname(LOG_FILE_PATH)
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 3. 创建一个 logger 实例
# 使用'PG_Anlize_Sys'作为logger的名称，可以防止与项目/库的根logger冲突
logger = logging.getLogger("PG_Anlize_Sys")
logger.setLevel(LOG_LEVEL)

# 4. 设置统一的日志格式
# [时间] - [Logger名称] - [日志级别] - [消息]
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 5. 创建并配置控制台处理器 (StreamHandler)
# 将日志输出到标准输出（例如，您的终端）
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# 6. 创建并配置日志文件处理器 (TimedRotatingFileHandler)
# 'when='midnight'' 表示每天午夜轮换一次日志文件
# 'backupCount=7' 表示保留最近7天的日志
# 这是一种很好的实践，可以有效管理日志文件大小
file_handler = TimedRotatingFileHandler(
    filename=LOG_FILE_PATH,
    when='midnight',
    interval=1,
    backupCount=7,
    encoding='utf-8'
)
file_handler.setFormatter(formatter)

# 7. 将处理器添加到 logger
# 通过检查 logger.handlers 列表，可以避免因重复导入而多次添加处理器
if not logger.handlers:
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

# --- Logger Test ---
if __name__ == '__main__':
    # 这个脚本可以直接运行，以测试日志记录是否正常工作
    logger.debug("这是一条 DEBUG 级别的日志，通常用于详细的诊断信息。")
    logger.info("这是一条 INFO 级别的日志，用于记录程序正常运行的事件。")
    logger.warning("这是一条 WARNING 级别的日志，表示发生了预期之外的事情，但程序仍可运行。")
    logger.error("这是一条 ERROR 级别的日志，表示由于一个较严重的问题，程序的某些功能可能无法正常工作。")
    logger.critical("这是一条 CRITICAL 级别的日志，表示发生了严重的错误，程序可能无法继续运行。")

    print(f"\n日志测试完成。日志已记录到控制台，并同时写入到文件: '{LOG_FILE_PATH}'") 