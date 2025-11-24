from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List
import pandas as pd

@dataclass
class Signal:
    """
    标准化的交易信号数据类。
    
    使用 dataclass 可以方便地创建一个包含类型提示的类，
    并自动获得 __init__, __repr__ 等方法。
    """
    time: datetime
    code: str
    signal_type: str  # 'BUY' or 'SELL'
    price: float
    strategy_name: str
    description: str

    def to_dict(self):
        """将信号对象转换为字典"""
        return asdict(self)

def generate_signals_from_dataframe(df: pd.DataFrame, stock_code: str, strategy_name: str) -> List[Signal]:
    """
    从应用了策略的 DataFrame 中提取信号，并生成标准化的 Signal 对象列表。

    :param df: 应用了策略并包含 'signal' 列的 DataFrame。
               'signal' 列：1 表示买入, -1 表示卖出。
    :param stock_code: 股票代码
    :param strategy_name: 生成此信号的策略名称
    :return: 一个包含 Signal 对象的列表
    """
    signals = []
    
    # 筛选出有信号的行 (signal != 0)
    signal_rows = df[df['signal'] != 0].copy()

    if signal_rows.empty:
        return []

    for index, row in signal_rows.iterrows():
        signal_type = 'BUY' if row['signal'] == 1 else 'SELL'
        description = f"{strategy_name}: {'Golden Cross' if signal_type == 'BUY' else 'Death Cross'}"
        
        signal = Signal(
            time=index,  # 假设 DataFrame 的索引是时间
            code=stock_code,
            signal_type=signal_type,
            price=row['close'],  # 使用当日收盘价作为信号触发价格
            strategy_name=strategy_name,
            description=description
        )
        signals.append(signal)

    return signals

if __name__ == '__main__':
    # --- 测试代码 ---
    from src.strategy_engine.dma_strategy import DmaStrategy

    # 1. 准备模拟数据
    mock_data = {
        'time': pd.to_datetime([
            '2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05',
            '2023-01-06', '2023-01-07', '2023-01-08', '2023-01-09', '2023-01-10'
        ]),
        'close': [10.0, 10.2, 10.1, 9.8, 9.5, 9.8, 10.5, 11.0, 10.8, 11.2]
    }
    mock_kline = pd.DataFrame(mock_data).set_index('time') # 将 time 设置为索引

    # 2. 应用策略
    dma_strategy = DmaStrategy(short_window=3, long_window=6)
    result_df = dma_strategy.apply(mock_kline)
    
    # 3. 从结果中生成信号
    stock_code_test = "000001.SZ"
    generated_signals = generate_signals_from_dataframe(result_df, stock_code_test, dma_strategy.name)

    # 4. 打印信号
    print(f"--- 从策略 '{dma_strategy.name}' 的结果中生成了 {len(generated_signals)} 个信号 ---")
    for sig in generated_signals:
        print(sig.to_dict())

    # 示例输出:
    # --- 从策略 'DMA Crossover (3/6)' 的结果中生成了 1 个信号 ---
    # {'time': Timestamp('2023-01-07 00:00:00'), 'code': '000001.SZ', 'signal_type': 'BUY', 'price': 10.5, 'strategy_name': 'DMA Crossover (3/6)', 'description': 'DMA Crossover (3/6): Golden Cross'} 