import streamlit as st
import pandas as pd
import redis
import json
import time
import numpy as np
import os
from datetime import datetime
from src.config import config
from src.presentation import stock_detail, signal_history, top_picks, multifactor_picks
from src.data_storage.watchlist_manager import watchlist_manager
from src.data_storage import database, crud # 新增导入
from src.data_acquisition import data_fetcher # 新增导入

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
    /* 增加顶部空白，防止标题被 Streamlit 菜单栏遮挡 */
    .block-container {
        padding-top: 4rem;
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

# --- 静态股票名称加载 (从数据库加载) ---
@st.cache_resource(ttl=3600) # 缓存 1 小时，避免频繁查库
def load_stock_name_map_from_db():
    """
    从本地数据库加载全量股票名称，并构建多维索引。
    数据源：PostgreSQL 'stock_basic' 表 (models.Stock)
    确保无论代码什么格式都能找到名称。
    """
    name_map = {}
    try:
        # 使用独立的 session 进行查询
        with database.SessionLocal() as db:
            all_stocks = crud.get_all_stocks(db)
            # print(f"DEBUG: Loaded {len(all_stocks)} stocks from database for name mapping.")
            
            for stock in all_stocks:
                if not stock.code or not stock.name:
                    continue
                    
                code = str(stock.code).strip() # e.g. sh600000
                name = str(stock.name).strip()
                
                # 1. 原始格式
                name_map[code] = name
                
                # 2. 纯数字格式 (去前缀)
                # 假设数据库存的是带前缀的标准代码 (sh600000)
                clean_code = code.lower().replace("sh", "").replace("sz", "").replace(".", "")
                if clean_code:
                    name_map[clean_code] = name
                    
                    # 3. 各种变体索引 (方便前端怎么传都能找到)
                    # 生成 .SH/.SZ 后缀
                    name_map[f"{clean_code}.SH"] = name
                    name_map[f"{clean_code}.SZ"] = name
                    name_map[f"{clean_code}.sh"] = name
                    name_map[f"{clean_code}.sz"] = name
                    # 生成 sh/sz 前缀
                    name_map[f"sh{clean_code}"] = name
                    name_map[f"sz{clean_code}"] = name
                    name_map[f"SH{clean_code}"] = name
                    name_map[f"SZ{clean_code}"] = name
                    
    except Exception as e:
        print(f"Error loading stock names from DB: {e}")
    
    return name_map

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

            # 修复：Streamlit 序列化 DataFrame 到 Arrow 时，datetime64 混入 object 列可能触发 pyarrow ArrowInvalid。
            # 这里将 time 统一转为字符串，避免 Styler + datetime 的兼容性问题。
            if 'time' in filtered_df.columns:
                filtered_df['time'] = filtered_df['time'].astype(str)
            
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

def on_watchlist_click(stock):
    """侧边栏自选股点击回调"""
    st.session_state['selected_stock'] = stock
    st.session_state['navigation_radio'] = "个股详情"

def get_watchlist_names(watchlist_codes, redis_client):
    """
    获取自选股代码对应的中文名称。
    策略：内存静态字典(基于数据库) -> Redis实时数据 -> 实时API兜底
    """
    if not watchlist_codes:
        return {}
        
    name_map = {}
    
    # 0. 优先使用内存静态字典 (从数据库加载)
    # 这是最快且最准确的方式
    static_map = load_stock_name_map_from_db()
    
    missing_codes = []
    for code in watchlist_codes:
        # 尝试直接匹配 (已包含各种变体)
        if code in static_map:
            name_map[code] = static_map[code]
        else:
            # 再次尝试大小写转换 (虽然 dict 里已经有了，但以防万一)
            upper_code = code.upper()
            if upper_code in static_map:
                name_map[code] = static_map[upper_code]
            else:
                missing_codes.append(code)
                
    # 如果全都找到了，直接返回
    if not missing_codes:
        return name_map

    # 1. 批量从 Redis 获取 (针对新股或 DB 未及时更新的)
    keys = [f"quote:{code}" for code in missing_codes]
    values = redis_client.mget(keys)
    
    still_missing = []
    for code, val in zip(missing_codes, values):
        found = False
        if val:
            try:
                data = json.loads(val)
                name = data.get('name')
                if name and name != code: 
                    name_map[code] = name
                    found = True
            except:
                pass
        
        if not found:
            still_missing.append(code)
            
    # 2. 实时API兜底 (最后的手段)
    if still_missing:
        for code in still_missing:
            try:
                # 尝试API兜底
                info = data_fetcher.fetch_single_stock_spot(code)
                if info and 'name' in info:
                    name = info['name']
                    name_map[code] = name
                    
                    # 注意：这里我们不写回数据库，以免频繁 IO 或写入不完整数据
                    # 如果需要持久化，应依赖每日定时任务更新 Stock 表
                else:
                    name_map[code] = code 
            except Exception:
                name_map[code] = code
            
    # 3. 最终兜底
    for code in watchlist_codes:
        if code not in name_map:
            name_map[code] = code
            
    return name_map

def main():
    st.sidebar.title("🧭 导航")
    
    # 页面选项
    page_options = ["全市场监控", "AI 优选前十榜", "多因子选股", "个股详情", "历史信号"]

    # 获取当前 URL 参数，初始化默认页面
    # 仅在 session_state 未初始化时执行一次
    if "navigation_radio" not in st.session_state:
        query_params = st.query_params
        default_index = 0
        if query_params.get("page") == "detail":
            default_index = 2 # 个股详情的索引
        st.session_state["navigation_radio"] = page_options[default_index]
    
    # 如果有 selected_stock (通常来自回调设置)，更新 URL 并清除它
    # 这一步是为了让 URL 与 state 保持同步
    if 'selected_stock' in st.session_state:
        stock_code = st.session_state['selected_stock']
        st.query_params["page"] = "detail"
        st.query_params["code"] = stock_code
        # 注意：我们不需要 pop，因为个股详情页可能会用到它，或者我们在那里再清理
        # 这里主要是为了更新 URL
        
    # 绑定 key，实现双向绑定：用户点击更新 state，代码修改 state 更新组件
    page = st.sidebar.radio("Go to", page_options, key="navigation_radio")

    # --- 自选股列表 (在侧边栏) ---
    st.sidebar.divider()
    st.sidebar.subheader("⭐ 我的自选")
    watchlist = list(watchlist_manager.get_watchlist()) # 转为列表
    
    if watchlist:
        # 获取名称映射
        redis_client = get_redis_client()
        name_map = get_watchlist_names(watchlist, redis_client)

        for stock_code in watchlist:
            stock_name = name_map.get(stock_code, stock_code)
            display_name = f"{stock_name}" # 只显示名称

            col1, col2 = st.sidebar.columns([0.7, 0.3])
            with col1:
                st.button(
                    display_name, 
                    key=f"wl_{stock_code}",
                    on_click=on_watchlist_click,
                    args=(stock_code, ),
                    help=f"代码: {stock_code}" # hover 显示代码
                )
            with col2:
                # 简易删除按钮
                if st.button("✖", key=f"rm_{stock_code}"):
                    watchlist_manager.remove_stock(stock_code)
                    st.rerun()
    else:
        st.sidebar.info("暂无自选股")

    # --- 页面渲染 ---
    if page == "全市场监控":
        render_dashboard()
        
    elif page == "AI 优选前十榜":
        top_picks.render_top_picks_page()

    elif page == "多因子选股":
        multifactor_picks.render_multifactor_picks_page()
        
    elif page == "个股详情":
        # 获取代码
        query_params = st.query_params
        current_code = query_params.get("code", "sh600519")
        
        # 优先使用 session_state 中的 selected_stock (如果存在)
        if 'selected_stock' in st.session_state:
            current_code = st.session_state['selected_stock']
            
        code_input = st.sidebar.text_input("输入股票代码 (e.g. sh600519)", value=current_code)
        
        # 如果输入框变了，更新 URL 和 state
        if code_input != current_code:
            st.query_params["code"] = code_input
            st.session_state['selected_stock'] = code_input
            st.rerun()
            
        stock_detail.render_stock_detail_page()
        
    elif page == "历史信号":
        signal_history.render_signal_history_page()

if __name__ == '__main__':
    main()
