import streamlit as st
import pandas as pd
import redis
import json
import time
import numpy as np
from datetime import datetime
from src.config import config
from src.presentation import stock_detail, signal_history
from src.data_storage.watchlist_manager import watchlist_manager

# --- 页面配置 (必须是第一个 st 命令) ---
st.set_page_config(
    page_title="PG_Anlize_Sys | 智能量化看板",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="auto" # 移动端自动折叠
)

# --- CSS 样式优化 (针对移动端) ---
st.markdown("""
    <style>
    /* 缩小移动端顶部的空白 */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    /* 优化 Metrics 在小屏幕的显示 */
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
    }
    /* 调整表格字体 */
    div[data-testid="stDataFrame"] {
        font-size: 0.8rem;
    }
    </style>
""", unsafe_allow_html=True)

# --- Redis 连接 ---
@st.cache_resource
def get_redis_client():
    return redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB,
        decode_responses=True
    )

def get_realtime_data_from_redis(client):
    keys = client.keys('quote:*')
    if not keys:
        return pd.DataFrame()
    
    # 批量获取
    values = client.mget(keys)
    data_list = [json.loads(v) for v in values if v]
    return pd.DataFrame(data_list)

def calculate_snapshot_score(df):
    """
    基于实时快照计算简易策略评分 (0-100分)。
    注意：这是基于纯快照的策略，不包含历史K线信息。
    """
    if df.empty:
        return df

    # 1. 趋势分 (30分): 涨幅越高分数越高
    # 涨停(10%)得30分, 跌停(-10%)得0分, 0%得15分
    df['score_trend'] = (df['change_pct'] + 10) * 1.5
    df['score_trend'] = df['score_trend'].clip(0, 30)

    # 2. 日内强弱分 (30分): 收盘价在日内最高最低间的位置
    # (Close - Low) / (High - Low)
    # 如果 High == Low (一字板或刚开盘), 设为 0.5
    range_val = df['high'] - df['low']
    df['pos_in_day'] = 0.5
    mask = range_val > 0
    df.loc[mask, 'pos_in_day'] = (df['price'] - df['low']) / range_val
    df['score_pos'] = df['pos_in_day'] * 30

    # 3. 活跃度分 (40分): 换手率越高分数越高 (简化版，假设 turnover_rate 存在或用成交额估算)
    # 由于快照里没有流通盘数据，我们暂时用成交额(turnover)的对数来模拟活跃度
    # log10(1亿) = 8. 假设 10亿成交额为满分。
    # 这是一个粗略的近似。
    # 避免 log(0)
    df['log_turnover'] = np.log10(df['turnover'] + 1)
    # 假设 5 (10万) 是低点，9 (10亿) 是高点
    df['score_active'] = (df['log_turnover'] - 5) * 10
    df['score_active'] = df['score_active'].clip(0, 40)

    # 总分
    df['total_score'] = df['score_trend'] + df['score_pos'] + df['score_active']
    df['total_score'] = df['total_score'].round(1)
    
    return df

def style_dataframe(df):
    """样式优化"""
    def _color_change(val):
        try:
            val = float(val)
            return 'color: red' if val > 0 else 'color: green' if val < 0 else ''
        except: return ''
        
    def _highlight_score(val):
        try:
            val = float(val)
            if val >= 80: return 'background-color: #ffcccc; color: black' # 强力买入背景
            if val <= 30: return 'background-color: #ccffcc; color: black' # 强力卖出背景
            return ''
        except: return ''

    return df.style.applymap(_color_change, subset=['change_pct'])\
                   .applymap(_highlight_score, subset=['total_score'])

def render_dashboard():
    st.title("⚡ PG_Anlize_Sys: 智能实时量化看板")
    
    redis_client = get_redis_client()
    
    # --- 侧边栏筛选器 ---
    st.sidebar.header("🔍 策略筛选")
    min_score = st.sidebar.slider("最低综合评分", 0, 100, 60)
    min_change = st.sidebar.number_input("最低涨幅 (%)", value=-10.0, step=0.5)
    
    auto_refresh = st.sidebar.checkbox("开启实时刷新 (3s)", value=True)

    metrics_placeholder = st.empty()
    table_placeholder = st.empty()

    while True:
        # 1. 获取并计算
        df = get_realtime_data_from_redis(redis_client)
        
        if not df.empty:
            df['price'] = df['price'].astype(float)
            df['change_pct'] = df['change_pct'].astype(float)
            df['turnover'] = df['turnover'].astype(float)
            
            # 计算策略评分
            df = calculate_snapshot_score(df)
            
            # 2. 筛选
            filtered_df = df[
                (df['total_score'] >= min_score) & 
                (df['change_pct'] >= min_change)
            ]
            
            # 排序：按分数降序
            filtered_df = filtered_df.sort_values(by='total_score', ascending=False)

            # 3. 更新指标
            with metrics_placeholder.container():
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("全市场监控", len(df))
                kpi2.metric("入选股票", len(filtered_df))
                
                avg_change = df['change_pct'].mean()
                kpi3.metric("市场热度 (均涨跌)", f"{avg_change:.2f}%", 
                           delta_color="normal" if avg_change > 0 else "inverse")
                
                # 最高分股票
                top_stock = filtered_df.iloc[0]['name'] if not filtered_df.empty else "N/A"
                kpi4.metric("当前票王", top_stock)

            # 4. 更新表格
            show_cols = ['code', 'name', 'price', 'change_pct', 'total_score', 'score_trend', 'score_pos', 'score_active', 'time']
            
            table_placeholder.dataframe(
                style_dataframe(filtered_df[show_cols]),
                use_container_width=True,
                hide_index=True,
                height=800
            )
        else:
            table_placeholder.info("等待实时数据流入... 请确保采集器正在运行。")

        if not auto_refresh:
            break
        time.sleep(3)

def main():
    st.sidebar.title("🧭 导航")
    
    # 获取当前 URL 参数
    query_params = st.query_params
    default_page = "全市场监控"
    if query_params.get("page") == "detail":
        default_page = "个股详情"
        
    # 导航单选框
    page_options = ["全市场监控", "个股详情", "历史信号"]
    # 找到默认页面的索引
    try:
        index = page_options.index(default_page)
    except:
        index = 0
        
    page = st.sidebar.radio("Go to", page_options, index=index)

    # --- 自选股列表 (在侧边栏) ---
    st.sidebar.divider()
    st.sidebar.subheader("⭐ 我的自选")
    watchlist = watchlist_manager.get_watchlist()
    
    if watchlist:
        for stock in watchlist:
            # 获取股票名称 (需要从Redis查一下，简单起见先只显示代码，或尝试获取详情)
            # 为了性能，这里直接显示代码，点击后跳转
            col1, col2 = st.sidebar.columns([0.7, 0.3])
            with col1:
                if st.button(f"{stock}", key=f"wl_{stock}"):
                    # 点击跳转到详情页
                    st.query_params["page"] = "detail"
                    st.query_params["code"] = stock
                    st.rerun()
            with col2:
                # 简易删除按钮
                if st.button("✖", key=f"rm_{stock}"):
                    watchlist_manager.remove_stock(stock)
                    st.rerun()
    else:
        st.sidebar.info("暂无自选股")

    # --- 页面渲染 ---
    if page == "全市场监控":
        # 清除详情页的参数，保持 URL 干净
        if query_params.get("page") == "detail":
            st.query_params.clear()
        render_dashboard()
        
    elif page == "个股详情":
        # 获取代码
        current_code = query_params.get("code", "sh600519")
        code_input = st.sidebar.text_input("输入股票代码 (e.g. sh600519)", value=current_code)
        
        # 如果输入框变了，更新 URL
        if code_input != current_code:
            st.query_params["code"] = code_input
            st.rerun()
            
        stock_detail.render_stock_detail_page()
        
    elif page == "历史信号":
        # 清除参数
        if query_params.get("page"):
            st.query_params.clear()
        signal_history.render_signal_history_page()

if __name__ == '__main__':
    main()
