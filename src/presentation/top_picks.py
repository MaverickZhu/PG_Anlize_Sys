import streamlit as st
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.data_acquisition import data_fetcher
from src.strategy_engine.composite_strategy import CompositeStrategy
from src.logger import logger

def get_strategy_score(stock_code, stock_name):
    """
    获取单只股票的策略评分。
    辅助函数，用于线程池并发调用。
    """
    try:
        # 获取 K 线数据 (最近 100 天即可满足指标计算)
        df = data_fetcher.fetch_stock_daily_kline(stock_code)
        if df.empty or len(df) < 30:
            return None
            
        strategy = CompositeStrategy()
        result_df = strategy.apply(df)
        
        if result_df.empty:
            return None
            
        latest = result_df.iloc[-1]
        
        return {
            'code': stock_code,
            'name': stock_name,
            'score': latest.get('score', 0),
            'signal': latest.get('signal', 0),
            'price': latest.get('close', 0),
            'desc': latest.get('signal_desc', '')
        }
    except Exception as e:
        logger.error(f"Error scoring {stock_code}: {e}")
        return None

def on_view_detail(code):
    """
    点击查看详情的回调函数。
    直接设置跳转所需的状态。
    """
    st.session_state['selected_stock'] = code
    st.session_state['navigation_radio'] = "个股详情" # 强制切换侧边栏状态

def render_top_picks_page():
    st.title("🏆 AI 优选前十榜 (Top 10 Picks)")
    st.markdown("""
    系统实时扫描全市场 5000+ 只股票，经过两轮筛选为您推荐：
    1.  **初筛**: 涨幅 0%~5%，换手率 > 2%，量比 > 1.5 (量能显著放大)。
    2.  **精选**: 深度运行 AI 策略 (MACD + RSI + Bollinger)，按综合评分排序。
    """)

    if st.button("🚀 开始扫描 (预计耗时 30秒)", type="primary"):
        with st.status("正在进行全市场扫描...", expanded=True) as status:
            
            # --- 第一步: 全市场快照 ---
            st.write("1. 获取全市场实时行情...")
            spot_df = data_fetcher.fetch_all_stock_spot_realtime()
            
            if spot_df.empty:
                st.error("获取全市场行情失败，请稍后再试。")
                return

            # --- 第二步: 初筛过滤 ---
            st.write("2. 执行第一轮过滤 (0% < 涨幅 < 5%, 活跃股, 量比 > 1.5)...")
            # 过滤条件:
            # 1. 涨幅 > 0 且 < 5
            # 2. 换手率 > 2% (保证活跃度)
            # 3. 量比 > 1.5 (新增: 相比过去5天平均量能显著放大)
            # 4. 排除 ST 股 (名称带 ST)
            
            # 转换数值列
            spot_df['pct_change'] = pd.to_numeric(spot_df['pct_change'], errors='coerce')
            spot_df['turnover_rate'] = pd.to_numeric(spot_df['turnover_rate'], errors='coerce')
            spot_df['volume_ratio'] = pd.to_numeric(spot_df['volume_ratio'], errors='coerce')
            
            filtered_df = spot_df[
                (spot_df['pct_change'] > 0) & 
                (spot_df['pct_change'] < 5) & 
                (spot_df['turnover_rate'] > 2) &
                (spot_df['volume_ratio'] > 1.5) &
                (~spot_df['name'].str.contains('ST'))
            ].copy()
            
            # 按量比排序，取前 30 只作为精选池 (优先关注量能爆发的个股)
            candidates = filtered_df.sort_values('volume_ratio', ascending=False).head(30)
            
            st.write(f"初筛完成，选出 {len(candidates)} 只潜力股，准备进行 AI 评分...")
            
            # --- 第三步: 并发策略计算 ---
            st.write("3. 并发拉取 K 线并运行 AI 策略模型...")
            
            scored_stocks = []
            progress_bar = st.progress(0)
            
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {
                    executor.submit(get_strategy_score, row['code'], row['name']): row 
                    for _, row in candidates.iterrows()
                }
                
                completed_count = 0
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        # 补充实时数据中的涨幅信息 (K线里的数据可能是昨天的)
                        match_row = candidates[candidates['code'] == result['code']].iloc[0]
                        result['pct_change'] = match_row['pct_change']
                        result['volume_ratio'] = match_row['volume_ratio']
                        scored_stocks.append(result)
                    
                    completed_count += 1
                    progress_bar.progress(completed_count / len(candidates))
            
            status.update(label="扫描完成!", state="complete", expanded=False)

        # --- 第四步: 展示结果 ---
        if not scored_stocks:
            st.warning("未能选出符合条件的股票。")
            return

        # 按分数倒序
        final_df = pd.DataFrame(scored_stocks)
        # 去重，防止同一只股票出现多次
        final_df.drop_duplicates(subset=['code'], inplace=True)
        final_df = final_df.sort_values('score', ascending=False).head(10).reset_index(drop=True)
        
        st.success(f"成功挖掘出 {len(final_df)} 只高分潜力股！")
        
        for i, row in final_df.iterrows():
            score = row['score']
            color = "red" if score >= 80 else "orange" if score >= 60 else "grey"
            
            with st.expander(f"#{i+1} {row['name']} ({row['code']}) - 评分: {score:.1f}", expanded=(i==0)):
                col1, col2, col3 = st.columns([1, 2, 1])
                
                with col1:
                    st.metric("当前涨幅", f"{row['pct_change']}%")
                    st.metric("AI 评分", f"{score:.0f}", delta="强力买入" if score >= 80 else "买入")
                
                with col2:
                    st.markdown(f"**策略分析**: {row['desc']}")
                    st.info(f"量比: {row.get('volume_ratio', 'N/A')} | 满足: 0%<涨幅<5%, 换手>2%, 量比>1.5")
                    
                with col3:
                    st.code(row['code'])
                    # 关键修复：使用 on_click 回调来处理跳转，避免 rerun 时状态丢失
                    # 再次修复：确保 key 唯一，防止数据源有重复时报错
                    st.button(
                        f"查看详情 {row['code']}", 
                        key=f"btn_{row['code']}_{i}",
                        on_click=on_view_detail,
                        args=(row['code'], )
                    )
