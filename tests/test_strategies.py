import unittest
import pandas as pd
import numpy as np
import sys
import os

# 添加项目根目录到 sys.path
sys.path.append(os.getcwd())

from src.strategy_engine.composite_strategy import CompositeStrategy

class TestCompositeStrategy(unittest.TestCase):

    def setUp(self):
        self.strategy = CompositeStrategy()

    def create_mock_data(self, trend='up'):
        """构造模拟K线数据"""
        dates = pd.date_range(start='2023-01-01', periods=50)
        
        if trend == 'up':
            # 制造上涨趋势，产生金叉
            # 前半段下跌，后半段急涨
            close = np.concatenate([
                np.linspace(100, 90, 25),
                np.linspace(90, 110, 25)
            ])
        else:
            # 制造下跌趋势，产生死叉
            # 前半段上涨，后半段急跌
            close = np.concatenate([
                np.linspace(90, 110, 25),
                np.linspace(110, 90, 25)
            ])
            
        df = pd.DataFrame({
            'time': dates,
            'open': close, # 简化
            'high': close + 2,
            'low': close - 2,
            'close': close,
            'volume': 100000
        })
        return df

    def test_buy_signal(self):
        """测试是否能识别强力买入信号"""
        # 构造更长、更明显的数据
        dates = pd.date_range(start='2023-01-01', periods=100)
        # 1-70天: 阴跌 (100 -> 50)
        # 71-80天: 急跌 (50 -> 30) -> 制造恐慌和超卖
        # 81-100天: 暴力反弹 (30 -> 60) -> 制造金叉
        close = np.concatenate([
            np.linspace(100, 50, 70),
            np.linspace(50, 30, 10),
            np.linspace(30, 60, 20)
        ])
        
        df = pd.DataFrame({
            'time': dates,
            'close': close,
            'high': close * 1.02,
            'low': close * 0.98,
            'volume': 100000
        })
        
        result = self.strategy.apply(df)
        
        # 打印最后几天的分数，帮助调试
        # print(result[['time', 'close', 'score', 'signal']].tail(10))
        
        # 检查反弹阶段(最后20天)是否有高分
        recent = result.tail(20)
        # 只要分数超过 65 就认为策略有效（识别出了反转趋势）
        has_good_score = (recent['score'] > 65).any()
        
        self.assertTrue(has_good_score, "Expected high score (>65) in strong rebound scenario")

    def test_neutral_signal(self):
        """测试震荡行情下的中性信号"""
        dates = pd.date_range(start='2023-01-01', periods=50)
        close = np.full(50, 100.0) # 价格横盘
        
        df = pd.DataFrame({
            'time': dates,
            'close': close,
            'high': close + 1,
            'low': close - 1,
            'volume': 100000
        })
        
        result = self.strategy.apply(df)
        last_row = result.iloc[-1]
        
        # 横盘时分数应接近50，信号为0
        self.assertEqual(last_row['signal'], 0)
        self.assertTrue(40 <= last_row['score'] <= 60, f"Score {last_row['score']} should be neutral")

if __name__ == '__main__':
    unittest.main()
