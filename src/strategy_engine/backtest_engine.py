import backtrader as bt
import pandas as pd
import datetime
from src.data_acquisition import data_fetcher
from src.logger import logger

# --- Backtrader 策略实现 ---
class BTCompositeStrategy(bt.Strategy):
    """
    适配 Backtrader 的综合策略。
    逻辑应与 CompositeStrategy 保持一致。
    """
    params = (
        ('macd_fast', 12),
        ('macd_slow', 26),
        ('macd_signal', 9),
        ('rsi_period', 14),
        ('bb_period', 20),
        ('bb_dev', 2),
    )

    def __init__(self):
        # 指标计算
        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.params.macd_fast,
            period_me2=self.params.macd_slow,
            period_signal=self.params.macd_signal
        )
        
        self.rsi = bt.indicators.RSI(
            self.data.close,
            period=self.params.rsi_period
        )
        
        self.bbands = bt.indicators.BollingerBands(
            self.data.close,
            period=self.params.bb_period,
            devfactor=self.params.bb_dev
        )
        
    def next(self):
        # 简单的评分逻辑复现
        score = 50
        
        # MACD
        if self.macd.macd[0] > self.macd.signal[0]:
            score += 20
        else:
            score -= 20
            
        # RSI
        if self.rsi[0] < 30:
            score += 15
        elif self.rsi[0] > 70:
            score -= 15
            
        # Bollinger
        if self.data.close[0] < self.bbands.lines.bot[0]:
            score += 10
        elif self.data.close[0] > self.bbands.lines.top[0]:
            score -= 10
            
        # 交易逻辑
        if not self.position:
            if score >= 80:
                self.buy() # 全仓买入 (默认size需要设置)
        else:
            if score <= 40: # 止盈/止损
                self.close()

class PandasDataPlus(bt.feeds.PandasData):
    """自定义数据加载器"""
    pass

def run_backtest(stock_code, start_date, end_date, initial_cash=100000):
    """
    运行回测
    :return: (final_value, performance_stats_dict, plot_fig)
    """
    try:
        # 1. 获取数据
        df = data_fetcher.fetch_stock_daily_kline(stock_code, start_date, end_date)
        if df.empty:
            return None, {"error": "No data"}, None
            
        # 必须确保时间索引正确
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
        
        # 2. 初始化 Cerebro
        cerebro = bt.Cerebro()
        cerebro.addstrategy(BTCompositeStrategy)
        
        # 3. 加载数据
        data = PandasDataPlus(dataname=df)
        cerebro.adddata(data)
        
        # 4. 设置资金
        cerebro.broker.setcash(initial_cash)
        # 设置佣金 (万3)
        cerebro.broker.setcommission(commission=0.0003)
        # 设置每笔交易股数 (简单起见，每次买1000股，或按比例)
        cerebro.addsizer(bt.sizers.FixedSize, stake=1000) 
        
        # 5. 添加分析器
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        
        # 6. 运行
        logger.info(f"Starting backtest for {stock_code}...")
        start_value = cerebro.broker.getvalue()
        results = cerebro.run()
        end_value = cerebro.broker.getvalue()
        
        strat = results[0]
        
        # 7. 提取结果
        stats = {
            "initial_cash": start_value,
            "final_value": end_value,
            "return_pct": (end_value - start_value) / start_value * 100,
            "sharpe": strat.analyzers.sharpe.get_analysis().get('sharperatio', None),
            "max_drawdown": strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
        }
        
        # Backtrader 自带的 plot 是 matplotlib，Streamlit 显示比较麻烦
        # 我们通常只返回统计数据，或者把 equity curve 提取出来自己画
        
        return stats
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return None, {"error": str(e)}

