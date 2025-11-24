import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
# 这使得我们可以在 .env 文件中存放敏感信息，而不用硬编码在代码里
load_dotenv()

class Config:
    """
    项目的主配置类。
    配置项可以从环境变量中获取，或者直接在此处设置默认值。
    """

    # --- 核心配置 ---
    # DEBUG 模式，开发环境下建议开启
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')

    # --- 数据库配置 (PostgreSQL) ---
    # 从环境变量获取数据库连接信息，提供默认值以备本地开发使用
    DB_USER = os.environ.get('DB_USER', 'postgres')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'password')
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '15432')
    DB_NAME = os.environ.get('DB_NAME', 'pg_anlize_sys')

    # 构造数据库连接URI
    # 注意: f-string中的内容只有在方法被调用时才会被求值
    @property
    def DATABASE_URI(self):
        """生成并返回数据库连接字符串"""
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # --- Redis 配置 ---
    REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.environ.get('REDIS_PORT', 16380))
    REDIS_DB = int(os.environ.get('REDIS_DB', 0))

    # --- 数据源 API 配置 ---
    # 将来需要用到的API Key等，可以从环境变量获取
    # TUSHARE_API_KEY = os.environ.get('TUSHARE_API_KEY', 'your_tushare_api_key_here')

    # --- 日志配置 ---
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    LOG_FILE_PATH = os.environ.get('LOG_FILE_PATH', 'logs/app.log')

    # --- 通知配置 (Email) ---
    # 默认使用 126/163/QQ 邮箱的 SMTP 服务
    # 示例: smtp.126.com, 465 (SSL) 或 25
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.example.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 465))
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'True').lower() in ('true', '1', 't')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '') # 授权码
    MAIL_SENDER = os.environ.get('MAIL_SENDER', MAIL_USERNAME)
    MAIL_RECEIVER = os.environ.get('MAIL_RECEIVER', '') # 接收通知的邮箱


# 实例化配置对象，以便在项目的其他地方直接导入使用
config = Config()

if __name__ == '__main__':
    # 这个简单的测试脚本可以验证配置是否被正确加载
    print("--- PG_Anlize_Sys 配置信息 ---")
    print(f"调试模式 (DEBUG): {config.DEBUG}")
    print(f"日志级别 (LOG_LEVEL): {config.LOG_LEVEL}")
    print(f"日志文件路径 (LOG_FILE_PATH): {config.LOG_FILE_PATH}")
    print(f"数据库主机 (DB_HOST): {config.DB_HOST}")
    print(f"数据库名称 (DB_NAME): {config.DB_NAME}")
    print(f"数据库连接URI: {config.DATABASE_URI}")
    # print(f"Tushare API Key: {config.TUSHARE_API_KEY}")
    print("---------------------------------")
    if not os.getenv('DB_PASSWORD'):
        print("\n提醒: 未在环境变量中找到 DB_PASSWORD，正在使用默认值。") 