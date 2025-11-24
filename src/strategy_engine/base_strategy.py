from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    """
    策略基类 (Abstract Base Class)。
    
    这是一个抽象类，定义了所有具体策略类都必须遵循的接口。
    它确保了每个策略都有一个统一的入口点 (`apply` 方法)，
    并且都能够接收一个标准的 pandas DataFrame 作为输入。

    所有新的策略都应该继承自这个类，并实现 `apply` 方法。
    """

    def __init__(self, name: str, description: str):
        """
        初始化策略基类。

        :param name: 策略的名称, e.g., "Dual Moving Average Crossover"
        :param description: 策略的简要描述
        """
        self.name = name
        self.description = description

    @abstractmethod
    def apply(self, kline_data: pd.DataFrame) -> pd.DataFrame:
        """
        应用策略到给定的K线数据上。
        
        这是一个抽象方法，所有子类都必须实现它。
        该方法接收K线数据，执行策略逻辑（例如，计算指标、判断信号），
        并返回一个带有策略分析结果的 DataFrame。

        :param kline_data: 包含 'open', 'high', 'low', 'close', 'volume' 的 DataFrame
        :return: 一个新的 DataFrame，其中包含了原始数据以及策略计算出的额外列
                 （例如，移动均线值、信号标记等）。
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}')>"

if __name__ == '__main__':
    # 这个部分只是为了演示如何继承 BaseStrategy，它本身无法运行
    
    class MyDummyStrategy(BaseStrategy):
        def __init__(self):
            super().__init__(
                name="Dummy Strategy",
                description="A simple placeholder strategy."
            )

        def apply(self, kline_data: pd.DataFrame) -> pd.DataFrame:
            print(f"正在应用 '{self.name}' 策略...")
            # 在这里实现具体的策略逻辑
            # 例如：kline_data['signal'] = 1
            kline_data['dummy_signal'] = 0 # 示例：添加一个信号列
            print("策略应用完成。")
            return kline_data

    # 创建一个虚拟的 DataFrame 来测试
    mock_data = {
        'time': pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03']),
        'close': [10, 11, 12]
    }
    mock_df = pd.DataFrame(mock_data)

    # 实例化并应用策略
    dummy_strategy = MyDummyStrategy()
    print(dummy_strategy)
    result_df = dummy_strategy.apply(mock_df)
    
    print("\n策略应用结果:")
    print(result_df) 