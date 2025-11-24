import pandas as pd
import pandas_ta as ta
from .base_strategy import BaseStrategy
from src.logger import logger

class DmaStrategy(BaseStrategy):
    """
    双移动均线 (Dual Moving Average) 交叉策略。
    
    当短期移动均线上穿长期移动均线时，产生买入信号（金叉）。
    当短期移动均线下穿长期移动均线时，产生卖出信号（死叉）。
    """

    def __init__(self, short_window: int = 10, long_window: int = 30):
        """
        初始化DMA策略。

        :param short_window: 短期移动均线的时间窗口
        :param long_window: 长期移动均线的时间窗口
        """
        super().__init__(
            name=f"DMA Crossover ({short_window}/{long_window})",
            description="当短期均线上穿长期均线时买入，下穿时卖出。"
        )
        self.short_window = short_window
        self.long_window = long_window

    def apply(self, kline_data: pd.DataFrame) -> pd.DataFrame:
        """
        应用双均线策略。

        :param kline_data: 包含 'close' 列的K线数据 DataFrame
        :return: 带有均线值和信号的 DataFrame
        """
        if kline_data.empty or 'close' not in kline_data.columns:
            logger.warning("输入的K线数据为空或缺少'close'列，无法应用DMA策略。")
            return kline_data

        logger.debug(f"正在对 {len(kline_data)} 条数据应用 '{self.name}' 策略...")

        # 复制DataFrame以避免修改原始数据
        df = kline_data.copy()

        # 1. 使用 pandas-ta 计算短期和长期简单移动均线(SMA)
        df.ta.sma(length=self.short_window, append=True)
        df.ta.sma(length=self.long_window, append=True)

        # 字段名默认为 SMA_10, SMA_30 等
        short_ma_col = f'SMA_{self.short_window}'
        long_ma_col = f'SMA_{self.long_window}'
        
        # 2. 识别交叉点
        #    - 'signal' 列：1 表示金叉（买入），-1 表示死叉（卖出），0 表示无信号
        df['signal'] = 0
        
        # 金叉条件：短期均线从下方上穿长期均线
        golden_cross_condition = (df[short_ma_col].shift(1) < df[long_ma_col].shift(1)) & \
                                 (df[short_ma_col] > df[long_ma_col])
        df.loc[golden_cross_condition, 'signal'] = 1 # 买入信号

        # 死叉条件：短期均线从上方下穿长期均线
        death_cross_condition = (df[short_ma_col].shift(1) > df[long_ma_col].shift(1)) & \
                                (df[short_ma_col] < df[long_ma_col])
        df.loc[death_cross_condition, 'signal'] = -1 # 卖出信号
        
        logger.debug("DMA策略应用完成。")
        return df

if __name__ == '__main__':
    # --- 测试代码 ---
    # 创建一个模拟的K线数据，用于演示策略如何工作
    mock_data = {
        'time': pd.to_datetime([
            '2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05',
            '2023-01-06', '2023-01-07', '2023-01-08', '2023-01-09', '2023-01-10'
        ]),
        'close': [10.0, 10.2, 10.1, 9.8, 9.5, 9.8, 10.5, 11.0, 10.8, 11.2]
    }
    mock_kline = pd.DataFrame(mock_data)

    # 实例化策略 (使用较短的窗口以便在少量数据上看到效果)
    dma_strategy = DmaStrategy(short_window=3, long_window=6)
    
    print(f"--- 测试策略: {dma_strategy.name} ---")
    
    # 应用策略
    result_df = dma_strategy.apply(mock_kline)

    print("策略应用结果:")
    # 打印包含信号的结果行
    print(result_df[result_df['signal'] != 0])
    
    print("\n完整结果预览:")
    print(result_df.to_string()) 