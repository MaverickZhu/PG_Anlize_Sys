import pandas as pd
import pandas_ta as ta
import numpy as np

# 创建模拟数据
df = pd.DataFrame({
    'close': np.random.randn(100) + 100
})

# 运行布林带
bb = df.ta.bbands(length=20, std=2)
print("Columns returned by ta.bbands:", bb.columns.tolist())

# 运行带 append=True
df.ta.bbands(length=20, std=2, append=True)
print("Columns in df after append:", df.columns.tolist())

