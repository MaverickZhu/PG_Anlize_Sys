from src.data_storage.database import init_db, engine
from src.data_storage import models

if __name__ == "__main__":
    print("正在初始化/更新数据库表结构...")
    # 确保所有模型都已导入，init_db 会调用 Base.metadata.create_all
    init_db()
    print("数据库表结构更新完成。")

