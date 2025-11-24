import streamlit as st
import pandas as pd
from src.data_storage import database, crud

def render_signal_history_page():
    """
    渲染历史信号查询页面。
    """
    st.title("📜 历史策略信号")
    st.markdown("这里展示了系统每日自动扫描捕捉到的买入/卖出信号。")

    # 1. 获取数据
    db = next(database.get_db())
    try:
        signals = crud.get_signal_records(db, limit=200)
    finally:
        db.close()

    if not signals:
        st.info("暂无历史信号记录。请等待每日策略扫描任务运行。")
        return

    # 2. 转换为 DataFrame 以便展示
    data = []
    for sig in signals:
        data.append({
            "时间": sig.time,
            "代码": sig.code,
            "策略": sig.strategy_name,
            "类型": sig.signal_type,
            "触发价": sig.price,
            "描述": sig.description
        })
    
    df = pd.DataFrame(data)
    
    # 3. 样式优化
    def color_signal(val):
        if val == 'BUY':
            return 'color: red; font-weight: bold'
        elif val == 'SELL':
            return 'color: green; font-weight: bold'
        return ''

    st.dataframe(
        df.style.applymap(color_signal, subset=['类型'])
                .format({"触发价": "{:.2f}", "时间": "{:%Y-%m-%d %H:%M}"}),
        use_container_width=True,
        height=600
    )

