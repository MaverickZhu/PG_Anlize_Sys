import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import redis
import json
import concurrent.futures
from src.config import config
from src.data_acquisition import data_fetcher, deep_analysis_fetcher
from src.data_storage.watchlist_manager import watchlist_manager
from src.strategy_engine.composite_strategy import CompositeStrategy
from src.strategy_engine.backtest_engine import run_backtest
from datetime import datetime, timedelta

# --- Redis 连接 ---
def get_redis_client():
    return redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB,
        decode_responses=True
    )

def get_stock_realtime_info(stock_code):
    """
    从 Redis 获取单只股票的实时详情。
    如果 Redis 中没有数据 (如未开启采集器)，则尝试直接调用 API 获取。
    """
    # 1. 尝试从 Redis 获取
    try:
        r = get_redis_client()
        data_str = r.get(f"quote:{stock_code}")
        if data_str:
            return json.loads(data_str)
    except Exception as e:
        # Redis 连接失败，不阻塞，尝试直接API
        pass
        
    # 2. 如果 Redis 为空，调用实时 API
    # 使用 data_fetcher 新增的单股查询接口
    spot_data = data_fetcher.fetch_stock_spot_realtime(stock_code)
    if spot_data:
        return spot_data
        
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

def render_capital_flow(stock_code):
    """渲染资金流向分析 (基于东财实时接口)"""
    try:
        # 获取实时资金流数据
        money_flow = data_fetcher.fetch_stock_money_flow_realtime(stock_code)
        
        if not money_flow:
            st.warning("暂无实时资金流向数据")
            return

        # 数据单位转换 (元 -> 万/亿)
        def format_money(val):
            if abs(val) > 100000000:
                return f"{val/100000000:.2f} 亿"
            else:
                return f"{val/10000:.2f} 万"

        # --- 可视化 ---
        st.subheader("💰 资金流向分析 (Capital Flow Analysis)")
        
        tab_today, tab_trend = st.tabs(["📅 当日资金流 (实时)", "📈 近30日主力趋势"])
        
        with tab_today:
            # 1. 主力/散户净流入概览
            col_main, col_retail = st.columns(2)
            
            main_net = money_flow.get('main_net_inflow', 0)
            retail_net = money_flow.get('retail_net_inflow', 0)
            
            col_main.metric("主力净流入", format_money(main_net), 
                           delta=format_money(main_net), delta_color="normal")
            col_retail.metric("散户净流入", format_money(retail_net), 
                             delta=format_money(retail_net), delta_color="inverse") # 散户流入通常被视为反向指标(inverse)
            
            st.divider()
            
            # 2. 详细资金净流入分布
            # 由于接口只返回净流入，我们直接展示净流入的柱状图
            
            categories = ['超大单', '大单', '中单', '小单']
            net_flows = [
                money_flow.get('super_large_net', 0),
                money_flow.get('large_net', 0),
                money_flow.get('medium_net', 0),
                money_flow.get('small_net', 0)
            ]
            
            colors = ['red' if v > 0 else 'green' for v in net_flows]
            
            fig_net = go.Figure(go.Bar(
                x=categories,
                y=net_flows,
                marker_color=colors,
                text=[format_money(v) for v in net_flows],
                textposition='auto'
            ))
            
            fig_net.update_layout(
                title="各单净流入详情 (正=流入，负=流出)",
                height=400,
                yaxis_title="净流入金额 (元)"
            )
            st.plotly_chart(fig_net, use_container_width=True)

        with tab_trend:
            render_history_money_flow(stock_code)

    except Exception as e:
        st.error(f"资金流向分析失败: {e}")

def render_history_money_flow(stock_code):
    """
    渲染历史主力资金流向 (近似估算)
    使用日线数据的 Price Change * Volume 近似计算。
    更精确的算法通常需要 Level-2 数据，这里使用 CMF (Chaikin Money Flow) 思想的简化版。
    """
    try:
        # 获取最近 60 天日线数据
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
        df = data_fetcher.fetch_stock_daily_kline(stock_code, start_date=start_date, end_date=end_date)
        
        if df.empty:
            st.warning("暂无历史数据计算资金趋势")
            return
            
        # 计算每日近似净流入 (Money Flow Volume)
        # 经典公式 MFV = Volume * ((Close - Low) - (High - Close)) / (High - Low)
        # 如果 High == Low (一字板), MFV = 0 或 Volume * (1 if Close > PrevClose else -1)
        
        mfv_list = []
        for i, row in df.iterrows():
            h, l, c, v = row['high'], row['low'], row['close'], row['volume']
            if h == l:
                mfv = 0 # 无法判断
            else:
                multiplier = ((c - l) - (h - c)) / (h - l)
                mfv = v * multiplier * c # 乘以价格变成金额近似
            mfv_list.append(mfv)
            
        df['net_flow_amount'] = mfv_list
        
        # 绘制柱状图
        fig = go.Figure()
        
        # 颜色：红进绿出
        colors = ['red' if v >= 0 else 'green' for v in df['net_flow_amount']]
        
        fig.add_trace(go.Bar(
            x=df['time'],
            y=df['net_flow_amount'],
            marker_color=colors,
            name='主力净流入(估)'
        ))
        
        # 添加 5日 累计净流入曲线
        df['cum_5d'] = df['net_flow_amount'].rolling(5).sum()
        fig.add_trace(go.Scatter(
            x=df['time'],
            y=df['cum_5d'],
            mode='lines',
            name='5日累计净流入',
            line=dict(color='blue', width=2)
        ))
        
        fig.update_layout(
            title="近30日主力资金流向趋势 (近似)",
            height=350,
            yaxis_title="净流入金额 (估算)",
            xaxis_rangeslider_visible=False
        )
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"历史资金趋势计算失败: {e}")

def render_deep_analysis(stock_code):
    """渲染深度多维分析面板"""
    st.subheader("🧠 深度多维分析报告 (AI Diagnosis)")
    st.info("点击下方按钮，AI 将全网搜集该股的行业、资金、新闻、股东等七大维度数据并进行分析。")
    
    if st.button("🚀 生成/刷新深度分析报告", type="primary", use_container_width=True):
        with st.spinner("🔍 正在全网搜集数据 (行业、资金、新闻、股东、量化)..."):
            try:
                # 并行获取数据
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    f1 = executor.submit(deep_analysis_fetcher.fetch_individual_info, stock_code)
                    f2 = executor.submit(deep_analysis_fetcher.fetch_stock_news, stock_code)
                    f3 = executor.submit(deep_analysis_fetcher.fetch_top_holders, stock_code)
                    f4 = executor.submit(deep_analysis_fetcher.fetch_capital_flow_history, stock_code)
                    
                    info = f1.result()
                    news = f2.result()
                    holders = f3.result()
                    flow_history = f4.result()

                # --- 1. 行业与基本面 ---
                st.markdown("#### 1. 🏭 行业与基本面")
                i1, i2, i3, i4 = st.columns(4)
                i1.metric("所属行业", info.get("行业", "未知"))
                i2.metric("总市值", f"{info.get('总市值', 0)/100000000:.2f}亿" if info.get('总市值') else "N/A")
                i3.metric("流通市值", f"{info.get('流通市值', 0)/100000000:.2f}亿" if info.get('流通市值') else "N/A")
                i4.metric("市盈率(动)", f"{info.get('市盈率(动)', 'N/A')}")
                
                # --- 2. 资金面深度 ---
                st.markdown("#### 2. 💸 资金面深度 (量化/主力)")
                if not flow_history.empty:
                    # 简单计算近期主力净流入天数
                    recent_days = 20
                    recent_flow = flow_history.tail(recent_days)
                    positive_days = len(recent_flow[recent_flow['main_net_inflow'] > 0])
                    
                    st.write(f"近 {recent_days} 个交易日中，主力净流入 **{positive_days}** 天。")
                    
                    # 画图
                    fig = go.Figure()
                    colors = ['red' if v > 0 else 'green' for v in flow_history['main_net_inflow']]
                    fig.add_trace(go.Bar(x=flow_history['date'], y=flow_history['main_net_inflow'], marker_color=colors, name='主力净流入'))
                    fig.update_layout(height=300, title="近30日主力资金净流入趋势", margin=dict(l=0,r=0,t=30,b=0))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("暂无资金流向历史数据")

                # --- 3. 股东持股 ---
                st.markdown("#### 3. 👥 股东持股情况")
                if not holders.empty:
                    st.dataframe(holders, use_container_width=True)
                else:
                    clean_code = deep_analysis_fetcher.get_clean_code(stock_code)
                    url = f"http://data.eastmoney.com/gdfx/{clean_code}.html"
                    st.warning(f"暂无最新股东数据 (可能受限于网络)。 [👉 点击查看东财深度数据]({url})")

                # --- 4. 消息面 ---
                st.markdown("#### 4. 📰 市场消息与热度")
                if news:
                    for n in news[:5]:
                        st.markdown(f"- **[{n['time']}]** [{n['title']}]({n['url']}) _({n['source']})_")
                else:
                    st.warning("暂无相关新闻")

            except Exception as e:
                st.error(f"深度分析生成失败: {e}")
                st.exception(e)

def render_strategy_diagnosis(stock_code):
    """渲染策略诊断面板"""
    try:
        # 1. 获取历史数据 (至少200天以计算指标)
        # 在生产环境中，这里可以进一步优化缓存
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=300)).strftime("%Y%m%d")
        
        df = data_fetcher.fetch_stock_daily_kline(stock_code, start_date=start_date, end_date=end_date)
        
        if df.empty or len(df) < 30:
            st.warning("历史数据不足，无法进行策略诊断")
            return

        # 2. 运行策略引擎
        strategy = CompositeStrategy()
        result_df = strategy.apply(df)
        
        # 取最新一天的结果
        latest = result_df.iloc[-1]
        
        # 3. 布局展示
        st.subheader("🤖 AI 策略诊断")
        
        # 第一行：综合评分仪表盘 + 核心建议
        col_score, col_signal = st.columns([1, 2])
        
        with col_score:
            fig = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = latest['score'],
                title = {'text': "综合评分"},
                gauge = {
                    'axis': {'range': [0, 100]},
                    'bar': {'color': "darkblue"},
                    'steps': [
                        {'range': [0, 20], 'color': "#ffdddd"},  # 弱势区
                        {'range': [20, 80], 'color': "white"},   # 震荡区
                        {'range': [80, 100], 'color': "#ddffdd"} # 强势区
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': latest['score']
                    }
                }
            ))
            fig.update_layout(height=250, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
        with col_signal:
            st.markdown("### 核心信号")
            
            # 根据分数和信号生成解读
            signal_color = "gray"
            signal_text = "观望"
            if latest['score'] >= 80:
                signal_color = "green"
                signal_text = "强力买入"
            elif latest['score'] <= 20:
                signal_color = "red"
                signal_text = "强力卖出"
            elif latest['score'] >= 60:
                signal_color = "lightgreen"
                signal_text = "偏多震荡"
            elif latest['score'] <= 40:
                signal_color = "pink"
                signal_text = "偏空震荡"
                
            st.markdown(f"""
            <div style='padding: 20px; background-color: #f0f2f6; border-radius: 10px; border-left: 5px solid {signal_color}'>
                <h2 style='color: {signal_color}; margin: 0'>{signal_text}</h2>
                <p style='margin-top: 10px; font-size: 16px'>
                    {latest.get('signal_desc', 'Evaluating market trends...')}
                </p>
            </div>
            """, unsafe_allow_html=True)
            
        st.divider()
        
        # 第二行：具体指标卡片
        m1, m2, m3 = st.columns(3)
        
        # MACD 状态
        macd_val = latest.get('MACD_12_26_9', 0)
        macd_sig = latest.get('MACDs_12_26_9', 0)
        macd_hist = latest.get('MACDh_12_26_9', 0)
        macd_status = "金叉" if macd_hist > 0 else "死叉"
        m1.metric("MACD 趋势", macd_status, f"{macd_hist:.3f}", delta_color="normal")
        
        # RSI 状态
        rsi_val = latest.get('RSI_14', 50)
        rsi_status = "中性"
        if rsi_val > 70: rsi_status = "超买 (风险)"
        elif rsi_val < 30: rsi_status = "超卖 (机会)"
        m2.metric("RSI (14)", f"{rsi_val:.1f}", rsi_status, delta_color="off")
        
        # 布林带状态
        close_price = latest['close']
        bb_upper = latest.get('BBU_20_2.0', 0)
        bb_lower = latest.get('BBL_20_2.0', 0)
        bb_pos = "中轨附近"
        if close_price >= bb_upper: bb_pos = "突破上轨"
        elif close_price <= bb_lower: bb_pos = "触及下轨"
        m3.metric("布林带位置", bb_pos, f"上轨: {bb_upper:.2f}")

    except Exception as e:
        st.error(f"策略诊断执行失败: {e}")

def render_backtest_panel(stock_code):
    """渲染历史回测面板"""
    st.subheader("⌛ 历史回测验证")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        start_date = st.date_input("开始日期", value=datetime.now() - timedelta(days=365))
    with col2:
        end_date = st.date_input("结束日期", value=datetime.now())
    with col3:
        st.write("") # 占位
        if st.button("🚀 开始回测", type="primary"):
            with st.spinner("正在运行回测引擎..."):
                # 格式化日期
                s_str = start_date.strftime("%Y%m%d")
                e_str = end_date.strftime("%Y%m%d")
                
                stats = run_backtest(stock_code, s_str, e_str)
                
                if not stats:
                    st.error("回测失败，未获取到数据。")
                elif "error" in stats:
                    st.error(f"回测出错: {stats['error']}")
                else:
                    st.success("回测完成！")
                    
                    # 展示结果
                    r1, r2, r3 = st.columns(3)
                    ret_color = "normal" if stats['return_pct'] > 0 else "inverse"
                    r1.metric("策略收益率", f"{stats['return_pct']:.2f}%", delta_color=ret_color)
                    r2.metric("夏普比率", f"{stats['sharpe']:.2f}" if stats['sharpe'] else "N/A")
                    r3.metric("最大回撤", f"{stats['max_drawdown']:.2f}%", delta_color="inverse")
                    
                    st.info(f"初始资金: {stats['initial_cash']:.0f} | 最终资金: {stats['final_value']:.0f}")

def render_stock_detail_page():
    """个股详情页主入口"""
    # 从 URL 参数获取股票代码
    query_params = st.query_params
    stock_code = query_params.get("code", None)

    if not stock_code:
        st.info("👈 请从左侧或主页选择一只股票查看详情")
        return

    # 获取实时数据
    # 关键修复：如果Redis没数据，自动调用实时接口兜底
    realtime_data = get_stock_realtime_info(stock_code)
    
    if not realtime_data:
        # 再试一次，可能格式问题，尝试转换格式
        # 如果传入的是 300115.SZ，尝试转为 sz300115
        clean_code = stock_code.lower().replace('.', '').replace('sz', 'sz').replace('sh', 'sh') # 简单清理
        # 正规化 logic same as data_fetcher
        if not (clean_code.startswith('sh') or clean_code.startswith('sz')):
             if stock_code.startswith('6'): clean_code = f"sh{clean_code}"
             else: clean_code = f"sz{clean_code}"
             
        realtime_data = get_stock_realtime_info(clean_code)
        
        if not realtime_data:
            st.error(f"未找到股票 {stock_code} 的实时数据。请检查代码格式或网络连接。")
            return

    # --- 页面头部 ---
    # 移动端适配布局：7:3 比例，兼顾标题长度和按钮宽度
    col_title, col_fav = st.columns([0.7, 0.3])
    
    with col_title:
        # 使用 Markdown 渲染标题，font-size 稍微调小适应移动端
        st.markdown(f"### {realtime_data['name']} <span style='font-size:0.7em;color:gray'>({stock_code})</span>", unsafe_allow_html=True)
        
    with col_fav:
        is_watched = watchlist_manager.is_in_watchlist(stock_code)
        if is_watched:
            # use_container_width=True 让按钮填满列宽，视觉更整齐
            # type="primary" (红色)
            if st.button("★ 已存", key="btn_unfav", type="primary", use_container_width=True):
                watchlist_manager.remove_stock(stock_code)
                st.rerun()
        else:
            # type="secondary" (默认/灰色)
            if st.button("☆ 加入", key="btn_fav", use_container_width=True):
                watchlist_manager.add_stock(stock_code)
                st.rerun()
    
    # 核心指标栏 (移动端可能需要分成两行，每行2个)
    # 检查是否为移动端（无法直接检测，但可以优化布局）
    # 使用 st.columns 自动适配
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("当前价", realtime_data['price'], 
               f"{realtime_data['change_pct']}%", 
               delta_color="normal" if realtime_data['change_pct'] > 0 else "inverse")
    m2.metric("今开", realtime_data['open'])
    m3.metric("最高", realtime_data['high'])
    m4.metric("最低", realtime_data['low'])
    
    st.divider()

    # --- 主体内容 ---
    col_chart, col_book = st.columns([2, 1])
    
    with col_chart:
        st.subheader("📊 价格走势")
        
        # 使用 Tabs 切换分时图和日K线和深度分析
        tab1, tab2, tab3, tab4 = st.tabs(["🕒 分时图", "📅 日K线", "🔍 深度分析", "⌛ 历史回测"])
        
        with tab1:
            render_minute_chart(stock_code)
            
        with tab2:
            render_kline_chart(stock_code)
            
        with tab3:
            render_deep_analysis(stock_code)
            
        with tab4:
            render_backtest_panel(stock_code)
        
    with col_book:
        st.subheader("📑 深度盘口")
        render_order_book(realtime_data)

    # --- 底部策略区 ---
    st.divider()
    render_strategy_diagnosis(stock_code)
    st.divider()
    render_capital_flow(stock_code)

if __name__ == '__main__':
    st.set_page_config(layout="wide")
    render_stock_detail_page()
