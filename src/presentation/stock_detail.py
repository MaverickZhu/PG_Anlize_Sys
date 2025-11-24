import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import redis
import json
from src.config import config
from src.data_acquisition import data_fetcher

# --- Redis 连接 ---
def get_redis_client():
    return redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB,
        decode_responses=True
    )

def get_stock_realtime_info(stock_code):
    """从 Redis 获取单只股票的实时详情"""
    r = get_redis_client()
    data_str = r.get(f"quote:{stock_code}")
    if data_str:
        return json.loads(data_str)
    return None

def render_order_book(data):
    """渲染五档盘口"""
    # 卖盘 (Ask) - 倒序显示 (卖5 -> 卖1)
    asks = []
    for i in range(5, 0, -1):
        asks.append({
            "Label": f"卖{i}",
            "Price": data.get(f"ask{i}", 0),
            "Volume": data.get(f"ask{i}_vol", 0) / 100 # 手
        })
    
    # 买盘 (Bid)
    bids = []
    for i in range(1, 6):
        bids.append({
            "Label": f"买{i}",
            "Price": data.get(f"bid{i}", 0),
            "Volume": data.get(f"bid{i}_vol", 0) / 100 # 手
        })
        
    # 创建两列布局
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📉 卖盘")
        for item in asks:
            if item['Price'] > 0:
                st.markdown(f"**{item['Label']}**: <span style='color:green'>{item['Price']:.2f}</span> | {int(item['Volume'])}", unsafe_allow_html=True)
            else:
                st.markdown(f"**{item['Label']}**: -- | --")

    with col2:
        st.markdown("#### 📈 买盘")
        for item in bids:
            if item['Price'] > 0:
                st.markdown(f"**{item['Label']}**: <span style='color:red'>{item['Price']:.2f}</span> | {int(item['Volume'])}", unsafe_allow_html=True)
            else:
                st.markdown(f"**{item['Label']}**: -- | --")

def render_kline_chart(stock_code):
    """绘制简单的K线图 (需连接 akshare 获取历史数据)"""
    try:
        df = data_fetcher.fetch_stock_daily_kline(stock_code, start_date="20240101")
        if df.empty:
            st.warning("暂无历史K线数据")
            return

        # 创建 Plotly 图表
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.03, subplot_titles=('K线图', '成交量'), 
                            row_heights=[0.7, 0.3])

        # K线 Trace
        fig.add_trace(go.Candlestick(
            x=df['time'],
            open=df['open'], high=df['high'],
            low=df['low'], close=df['close'],
            name='K线'
        ), row=1, col=1)

        # 成交量 Trace
        colors = ['red' if row['close'] > row['open'] else 'green' for index, row in df.iterrows()]
        fig.add_trace(go.Bar(
            x=df['time'], y=df['volume'],
            marker_color=colors,
            name='成交量'
        ), row=2, col=1)

        # 布局设置
        fig.update_layout(
            height=600,
            xaxis_rangeslider_visible=False,
            title=f"{stock_code} 日线趋势"
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"K线图加载失败: {e}")

def render_minute_chart(stock_code):
    """绘制分时图 (Debug模式)"""
    try:
        # 获取分钟数据
        df = data_fetcher.fetch_stock_minute_data(stock_code, period='1')
        if df.empty:
            st.warning("API返回数据为空")
            return

        # 筛选最新日期
        latest_date = df['time'].dt.date.max()
        df_today = df[df['time'].dt.date == latest_date].copy()
        
        if df_today.empty:
            st.warning(f"暂无 {latest_date} 数据")
            return
            
        # --- DEBUG 信息 (调试完成后可删除) ---
        with st.expander("🔍 调试数据 (点击展开)", expanded=False):
            st.write(f"最新日期: {latest_date}")
            st.write(f"数据行数: {len(df_today)}")
            st.write("数据预览:", df_today.head())
            st.write("数据类型:", df_today.dtypes)
        # ----------------------------------

        # 创建图表 - 使用 specs 精确控制
        fig = make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=(f'价格 ({latest_date})', '成交量'),
            row_heights=[0.7, 0.3], # 上面占70%，下面占30%
            specs=[[{"secondary_y": False}], [{"secondary_y": False}]]
        )

        # 1. 价格线
        fig.add_trace(go.Scatter(
            x=df_today['time'], 
            y=df_today['close'],
            mode='lines',
            name='价格',
            line=dict(color='#007BFF', width=2)
        ), row=1, col=1)
        
        # 2. 均价线
        # 确保数值计算安全
        vol_sum = df_today['volume'].cumsum()
        amt_sum = (df_today['close'] * df_today['volume']).cumsum()
        # 避免除零
        vwap = amt_sum / vol_sum.replace(0, 1) 
        
        fig.add_trace(go.Scatter(
            x=df_today['time'], 
            y=vwap,
            mode='lines',
            name='均价',
            line=dict(color='#FF9900', width=1.5, dash='dash')
        ), row=1, col=1)

        # 3. 成交量
        colors = ['red' if c >= o else 'green' for c, o in zip(df_today['close'], df_today['open'])]
        fig.add_trace(go.Bar(
            x=df_today['time'], 
            y=df_today['volume'],
            marker_color=colors,
            name='成交量'
        ), row=2, col=1)

        fig.update_layout(
            height=500,
            margin=dict(l=10, r=10, t=30, b=10),
            hovermode="x unified",
            xaxis_rangeslider_visible=False
        )
        
        # 格式化 X 轴
        fig.update_xaxes(tickformat="%H:%M", row=2, col=1)
        
        # 自动调整 Y 轴范围 (重要)
        fig.update_yaxes(autorange=True, fixedrange=False, row=1, col=1)
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"分时图绘制出错: {e}")
        st.exception(e) # 打印详细堆栈

def render_stock_detail_page():
    """个股详情页主入口"""
    # 从 URL 参数获取股票代码
    query_params = st.query_params
    stock_code = query_params.get("code", None)

    if not stock_code:
        st.info("👈 请从左侧或主页选择一只股票查看详情")
        return

    # 获取实时数据
    realtime_data = get_stock_realtime_info(stock_code)
    
    if not realtime_data:
        st.error(f"未找到股票 {stock_code} 的实时数据，可能未在监控列表中。")
        return

    # --- 页面头部 ---
    st.title(f"{realtime_data['name']} ({stock_code})")
    
    # 核心指标栏
    kp1, kp2, kp3, kp4 = st.columns(4)
    kp1.metric("当前价", realtime_data['price'], 
               f"{realtime_data['change_pct']}%", 
               delta_color="normal" if realtime_data['change_pct'] > 0 else "inverse")
    kp2.metric("今开", realtime_data['open'])
    kp3.metric("最高", realtime_data['high'])
    kp4.metric("最低", realtime_data['low'])
    
    st.divider()

    # --- 主体内容 ---
    col_chart, col_book = st.columns([2, 1])
    
    with col_chart:
        st.subheader("📊 价格走势")
        
        # 使用 Tabs 切换分时图和日K线
        tab1, tab2 = st.tabs(["🕒 分时图", "📅 日K线"])
        
        with tab1:
            render_minute_chart(stock_code)
            
        with tab2:
            render_kline_chart(stock_code)
        
    with col_book:
        st.subheader("📑 深度盘口")
        render_order_book(realtime_data)

    # --- 底部策略区 ---
    st.divider()
    st.subheader("🤖 策略诊断")
    st.info("此处将展示 AI 对该股票的深度策略分析报告 (RSI/MACD/资金流向)...")
    # TODO: 调用 CompositeStrategy 计算该个股的详细得分并展示

if __name__ == '__main__':
    st.set_page_config(layout="wide")
    render_stock_detail_page()
