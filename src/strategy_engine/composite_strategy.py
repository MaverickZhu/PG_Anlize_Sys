import pandas as pd
import pandas_ta as ta
from .base_strategy import BaseStrategy
from src.logger import logger

class CompositeStrategy(BaseStrategy):
    """
    综合量化策略 (Multi-Factor Strategy)。
    
    结合趋势 (MACD)、动量 (RSI) 和波动率 (Bollinger Bands) 三个维度，
    对股票进行综合评分并生成买卖信号。
    
    评分逻辑 (示例):
    - 基础分: 50分
    - MACD金叉: +20分
    - RSI < 30 (超卖): +20分
    - 突破布林带下轨: +10分 (反弹预期)
    - 评分 > 80: 强力买入
    - 评分 < 20: 强力卖出
    """

    def __init__(self):
        super().__init__(
            name="Composite Multi-Factor",
            description="结合MACD、RSI和布林带的多因子综合策略"
        )

    def apply(self, kline_data: pd.DataFrame) -> pd.DataFrame:
        """
        应用综合策略。
        """
        if kline_data.empty or 'close' not in kline_data.columns:
            return kline_data

        df = kline_data.copy()

        # --- 1. 计算技术指标 ---
        
        # MACD (12, 26, 9)
        # 返回列名通常为: MACD_12_26_9, MACDh_12_26_9 (Histogram), MACDs_12_26_9 (Signal)
        macd = df.ta.macd(fast=12, slow=26, signal=9, append=True)
        
        # 动态查找列名
        macd_col = [c for c in df.columns if c.startswith('MACD_')][0]
        macd_signal_col = [c for c in df.columns if c.startswith('MACDs_')][0]
        macd_hist_col = [c for c in df.columns if c.startswith('MACDh_')][0]

        # RSI (14)
        df.ta.rsi(length=14, append=True)
        rsi_col = [c for c in df.columns if c.startswith('RSI_')][0]

        # Bollinger Bands (20, 2)
        # 返回列名: BBL_... (Lower), BBM_... (Mid), BBU_... (Upper)
        df.ta.bbands(length=20, std=2, append=True)
        # 动态查找列名 (应对 BBL_20_2.0 或 BBL_20_2.0_2.0 等不同版本)
        bb_lower_col = [c for c in df.columns if c.startswith('BBL_')][0]
        bb_upper_col = [c for c in df.columns if c.startswith('BBU_')][0]

        # --- 2. 综合评分逻辑 (更细粒度的状态评分) ---
        
        # 初始化分数为 50 (中性)
        df['score'] = 50
        # 初始化信号列为浮点数，以支持 0.5 这种弱信号
        df['signal'] = 0.0
        # 设置默认描述，防止前端渲染空标签
        df['signal_desc'] = 'Wait (Neutral Trend)'

        # A. MACD 逻辑
        # 1. 金叉/死叉 (强信号)
        macd_golden_cross = (df[macd_col] > df[macd_signal_col]) & (df[macd_col].shift(1) <= df[macd_signal_col].shift(1))
        df.loc[macd_golden_cross, 'score'] += 20
        
        macd_death_cross = (df[macd_col] < df[macd_signal_col]) & (df[macd_col].shift(1) >= df[macd_signal_col].shift(1))
        df.loc[macd_death_cross, 'score'] -= 20
        
        # 2. 趋势持续 (弱信号)
        # MACD > Signal (多头趋势)
        df.loc[df[macd_col] > df[macd_signal_col], 'score'] += 5
        # MACD < Signal (空头趋势)
        df.loc[df[macd_col] < df[macd_signal_col], 'score'] -= 5

        # B. RSI 逻辑
        # 1. 超卖 (<30): 可能反弹，加分
        df.loc[df[rsi_col] < 30, 'score'] += 15
        # 2. 超买 (>70): 可能回调，减分
        df.loc[df[rsi_col] > 70, 'score'] -= 15
        # 3. 强势区间 (50-70): 趋势向上
        mask_rsi_bull = (df[rsi_col] >= 50) & (df[rsi_col] <= 70)
        df.loc[mask_rsi_bull, 'score'] += 5
        # 4. 弱势区间 (30-50): 趋势向下
        mask_rsi_bear = (df[rsi_col] >= 30) & (df[rsi_col] < 50)
        df.loc[mask_rsi_bear, 'score'] -= 5

        # C. 布林带逻辑
        # 1. 价格触及下轨: 强支撑
        df.loc[df['close'] <= df[bb_lower_col], 'score'] += 10
        # 2. 价格突破上轨: 强阻力/超买
        df.loc[df['close'] >= df[bb_upper_col], 'score'] -= 10
        # 3. 中轨之上 (多头)
        mid_col = [c for c in df.columns if c.startswith('BBM_')][0]
        df.loc[df['close'] > df[mid_col], 'score'] += 5
        # 4. 中轨之下 (空头)
        df.loc[df['close'] < df[mid_col], 'score'] -= 5


        # --- 3. 生成最终信号 ---
        
        # 限制分数范围 0-100
        df['score'] = df['score'].clip(0, 100)
        
        # 强力买入: 分数 >= 80
        buy_condition = df['score'] >= 80
        df.loc[buy_condition, 'signal'] = 1
        df.loc[buy_condition, 'signal_desc'] = 'Strong Buy (Multiple Bullish Signals)'

        # 适度买入: 60 <= 分数 < 80
        mod_buy_condition = (df['score'] >= 60) & (df['score'] < 80)
        df.loc[mod_buy_condition, 'signal'] = 0.5 # 弱买信号
        df.loc[mod_buy_condition, 'signal_desc'] = 'Moderate Buy (Positive Trend)'

        # 适度卖出: 20 < 分数 <= 40
        mod_sell_condition = (df['score'] > 20) & (df['score'] <= 40)
        df.loc[mod_sell_condition, 'signal'] = -0.5 # 弱卖信号
        df.loc[mod_sell_condition, 'signal_desc'] = 'Moderate Sell (Negative Trend)'

        # 强力卖出: 分数 <= 20
        sell_condition = df['score'] <= 20
        df.loc[sell_condition, 'signal'] = -1
        df.loc[sell_condition, 'signal_desc'] = 'Strong Sell (Multiple Bearish Signals)'
        
        # 关键修复：因为前N行数据计算出的指标为NaN，这里会导致 score 计算异常或不准确。
        # 我们应该将前 30 行（大约是 MACD 和 布林带 需要的窗口）的 score 设为 NaN 或者 50 (不操作)
        # 为了安全，直接 dropna 或者保留但标记
        # 简单做法：如果任意关键指标为 NaN，则 Score 为 50，Desc 为 "Insufficient Data"
        cols_to_check = [macd_col, rsi_col, bb_upper_col]
        mask_nan = df[cols_to_check].isna().any(axis=1)
        df.loc[mask_nan, 'score'] = 50
        df.loc[mask_nan, 'signal'] = 0
        df.loc[mask_nan, 'signal_desc'] = 'Initializing Indicators...'

        return df

        return df

if __name__ == '__main__':
    # 测试代码
    import numpy as np
    
    # 生成更逼真的随机游走数据
    dates = pd.date_range(start='2023-01-01', periods=100)
    close_prices = 100 + np.cumsum(np.random.randn(100))
    
    mock_df = pd.DataFrame({
        'time': dates,
        'open': close_prices + np.random.randn(100) * 0.5,
        'high': close_prices + 1 + np.random.rand(100),
        'low': close_prices - 1 - np.random.rand(100),
        'close': close_prices,
        'volume': np.random.randint(1000, 10000, 100)
    })
    
    strategy = CompositeStrategy()
    result = strategy.apply(mock_df)
    
    print("--- 综合策略测试结果 ---")
    # 打印最后5行数据，查看指标和分数
    cols_to_show = ['time', 'close', 'MACD_12_26_9', 'RSI_14', 'score', 'signal', 'signal_desc']
    print(result[cols_to_show].tail())

