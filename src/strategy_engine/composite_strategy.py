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
        macd_col = 'MACD_12_26_9'
        macd_signal_col = 'MACDs_12_26_9'
        macd_hist_col = 'MACDh_12_26_9'

        # RSI (14)
        df.ta.rsi(length=14, append=True)
        rsi_col = 'RSI_14'

        # Bollinger Bands (20, 2)
        # 返回列名: BBL_20_2.0 (Lower), BBM_20_2.0 (Mid), BBU_20_2.0 (Upper)
        df.ta.bbands(length=20, std=2, append=True)
        bb_lower_col = 'BBL_20_2.0'
        bb_upper_col = 'BBU_20_2.0'

        # --- 2. 综合评分逻辑 ---
        
        # 初始化分数为 50 (中性)
        df['score'] = 50
        df['signal'] = 0
        df['signal_desc'] = ''

        # 遍历计算每行 (注意：在生产环境中应尽量使用向量化操作以提升性能)
        # 这里为了逻辑清晰，暂时使用简单的逻辑，实际部署建议优化
        
        # MACD 逻辑
        # 金叉: MACD线 上穿 信号线
        macd_golden_cross = (df[macd_col] > df[macd_signal_col]) & (df[macd_col].shift(1) <= df[macd_signal_col].shift(1))
        df.loc[macd_golden_cross, 'score'] += 20
        
        # 死叉: MACD线 下穿 信号线
        macd_death_cross = (df[macd_col] < df[macd_signal_col]) & (df[macd_col].shift(1) >= df[macd_signal_col].shift(1))
        df.loc[macd_death_cross, 'score'] -= 20

        # RSI 逻辑
        # 超卖 (<30): 可能反弹，加分
        df.loc[df[rsi_col] < 30, 'score'] += 15
        # 超买 (>70): 可能回调，减分
        df.loc[df[rsi_col] > 70, 'score'] -= 15

        # 布林带逻辑
        # 价格触及下轨: 可能支撑反弹
        df.loc[df['close'] <= df[bb_lower_col], 'score'] += 10
        # 价格突破上轨: 虽然是强势，但也面临回调风险，视具体策略而定
        # 这里我们采取保守策略：突破上轨视为超买风险
        df.loc[df['close'] >= df[bb_upper_col], 'score'] -= 10


        # --- 3. 生成最终信号 ---
        
        # 强力买入: 分数 >= 80
        buy_condition = df['score'] >= 80
        df.loc[buy_condition, 'signal'] = 1
        df.loc[buy_condition, 'signal_desc'] = 'Strong Buy (High Score)'

        # 强力卖出: 分数 <= 20
        sell_condition = df['score'] <= 20
        df.loc[sell_condition, 'signal'] = -1
        df.loc[sell_condition, 'signal_desc'] = 'Strong Sell (Low Score)'

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

