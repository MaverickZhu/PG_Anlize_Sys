# PG_Anlize_Sys: 股票量化分析系统

## 1. 项目概述

**PG_Anlize_Sys** 是一个旨在根据预设策略实时筛选具有上涨趋势的优质股票的量化交易辅助软件。本系统通过模块化的架构，实现数据采集、策略分析、信号生成和结果展示的全流程自动化，为投资者提供决策支持。

## 2. 架构概览

系统采用分层架构，确保模块间的高内聚和低耦合，便于扩展和维护。

- **数据采集层 (Data Acquisition Layer)**
- **数据存储层 (Data Storage Layer)**
- **策略引擎 (Strategy Engine)**
- **信号与执行层 (Signal & Execution Layer)**
- **调度与监控层 (Scheduling & Monitoring Layer)**
- **展示与交互层 (Presentation Layer)**

## 3. 技术栈

- **后端**: Python 3.9+
- **数据获取**: Akshare, Tushare
- **数据处理**: Pandas, NumPy
- **策略与回测**: Pandas-TA, Backtrader
- **数据库**: PostgreSQL + TimescaleDB, Redis
- **任务调度**: APScheduler
- **前端展示**: Streamlit / Flask

## 4. 项目结构

```
PG_Anlize_Sys/
├── data/               # 存放临时或小型数据文件
├── docs/               # 存放项目文档 (如本文件)
│   └── project_plan.md # 项目开发计划
├── notebooks/          # Jupyter Notebooks，用于探索性分析和策略研究
├── src/                # 核心源代码
│   ├── data_acquisition/ # 数据采集模块
│   ├── data_storage/     # 数据存储模块
│   ├── presentation/     # 前端展示模块
│   ├── scheduling/       # 任务调度模块
│   ├── signals/          # 信号生成模块
│   └── strategy_engine/  # 策略引擎模块
├── tests/              # 测试代码
├── requirements.txt    # Python依赖包
└── README.md           # 项目入口文档
```

## 5. 快速开始

1.  **克隆项目**
    ```bash
    git clone <repository_url>
    cd PG_Anlize_Sys
    ```

2.  **创建并激活虚拟环境**
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```

3.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

4.  **运行**
    (根据后续开发的应用启动命令执行)
