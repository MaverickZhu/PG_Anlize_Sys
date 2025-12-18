# PG_Anlize_Sys: 智能股票量化分析系统

**PG_Anlize_Sys** 是一个全流程自动化的股票量化分析平台。它不仅提供实时的市场监控看板，还能自动对自选股进行深入的策略分析（MACD+RSI+布林带），并将捕捉到的交易机会通过邮件推送到您的手中。

---

## 🚀 核心功能

*   **⚡ 实时量化看板**：秒级更新全市场行情，基于多因子模型实时筛选强势股。
*   **🏆 AI 优选前十 (Top Picks)**：(New) 系统根据量化算法实时扫描全市场 5000+ 只股票，动态选出当前最具爆发潜力的 10 只个股，助您先人一步发现机会。
*   **🧠 多因子选股 (短线/中线/长线)**：(New) 基于“候选池快筛 + 多因子评分”的方式，按 **短线(2–5日)、中线(2–8周)、长线(9周+)** 三个周期分别推荐 **2–5** 只高分股票，并支持“偏好战法”一键增强（量能反转/PATV、流动性稳健/ILLIQ、注意力溢出/邻居热度等）。
*   **📊 个股深度分析 (Deep Analysis)**：(New)
    *   **全维透视**：一键生成包含**行业基本面、实时资金流向、最新股东持股、市场新闻公告**的深度报告。
    *   **数据灾备**：采用三级数据源（Akshare/Baostock/HTTP直连）智能切换技术，确保数据 100% 可用。
    *   **实时资金**：精确的主力/散户净流入分析（基于 Level-2 级数据）。
    *   **AI 策略诊断**：结合 MACD 趋势、RSI 动量和布林带波动的综合评分。
*   **🤖 自动化策略扫描**：
    *   每日收盘后自动扫描自选股池。
    *   自动识别买入/卖出信号并持久化存储。
    *   **邮件消息推送**：发现机会，即刻通知。
*   **📜 历史信号复盘**：完整的历史交易信号记录，助力策略验证与优化。

---

## 🛠️ 快速开始 (Quick Start)

### 1. 环境准备

确保您的系统已安装：
*   Python 3.9+
*   Docker & Docker Compose (用于数据库服务)

### 2. 安装部署

**步骤 1: 克隆项目**
```bash
git clone <repository_url>
cd PG_Anlize_Sys
```

**步骤 2: 启动基础服务 (PostgreSQL + Redis)**
项目内置了 Docker 配置，可一键启动所需数据库，数据将持久化保存在本地 `docker_data` 目录。
```bash
docker-compose up -d
```

**步骤 3: 安装 Python 依赖**
```bash
python -m venv venv
# Windows
.\venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

**步骤 4: 初始化数据库**
首次运行前，需初始化数据库表结构。
```bash
python scripts/init_db_tables.py
```

### 3. 配置系统 (.env)

在项目根目录创建 `.env` 文件，配置数据库及邮件通知服务：

```ini
# --- 基础配置 ---
LOG_LEVEL=INFO

# --- 数据库配置 (默认适配 docker-compose) ---
DB_HOST=localhost
DB_PORT=15432
DB_USER=postgres
DB_PASSWORD=password
DB_NAME=pg_anlize_sys

# --- Redis 配置 ---
REDIS_HOST=localhost
REDIS_PORT=16380

# --- 邮件通知配置 (可选，用于接收策略信号) ---
MAIL_SERVER=smtp.163.com
MAIL_PORT=465
MAIL_USE_SSL=True
MAIL_USERNAME=your_email@163.com
MAIL_PASSWORD=your_auth_code  # 邮箱授权码
MAIL_SENDER=your_email@163.com
MAIL_RECEIVER=your_email@163.com
```

---

## 🖥️ 启动系统

本系统由三个核心组件组成，建议分别在不同的终端窗口启动：

### 1. 启动实时数据采集器 (后台运行)
负责源源不断地从新浪/腾讯接口获取实时行情并推送到 Redis。
```bash
python -m src.data_acquisition.realtime_fetcher
```

### 2. 启动任务调度器 (自动化核心)
负责每日更新股票列表、同步历史数据、执行策略扫描和发送邮件。
```bash
python -m src.scheduling.scheduler
```

### 3. 启动 Web 可视化看板
启动 Streamlit 前端界面。
```bash
python -m streamlit run src/presentation/app.py --server.port 9000
```
访问浏览器：`http://localhost:9000` (如果端口 8501 被占用，可指定其他端口)

---

## 📖 使用指南

1.  **全市场监控**：首页展示全市场实时行情。使用左侧边栏的“AI 优选前十榜”查看系统推荐的潜力股。
2.  **多因子选股**：
    *   点击左侧导航栏的 **“多因子选股”**。
    *   可选择 **偏好战法（可多选）**：量能反转（PATV 简化）、流动性稳健（ILLIQ 代理）、注意力溢出（邻居热度）。
    *   点击 **“开始多因子扫描”** 后，系统会分别给出短线/中线/长线的推荐列表（每组 2–5 只，若无合适则少于 5 只）。
    *   结果字段包含：**得分、推荐置信度(prob)、量比、换手、原因(贡献最大的因子)**。注意：prob 为推荐置信度映射，并非收益承诺。
2.  **个股详情**：
    *   点击列表中的股票代码，或在侧边栏输入代码（如 `sh600519`）。
    *   点击 **“🔍 深度分析”** 标签页，再点击 **“🚀 生成/刷新深度分析报告”** 按钮，即可获取该股的行业、股东、公告等核心情报。
    *   查看 **“AI 策略诊断”**：仪表盘显示综合得分（>80 强力买入，<20 强力卖出）。
3.  **管理自选股**：
    *   在个股详情页点击 **“☆ 加入”**，该股将永久保存到您的云端自选列表。
    *   调度器会每天自动关注这些股票的走势。
4.  **查看信号**：
    *   点击左侧导航栏的 **“历史信号”**。
    *   这里记录了系统自动捕捉到的所有历史买卖点。

---

## 📂 项目结构

```
PG_Anlize_Sys/
├── docker-compose.yml      # 数据库服务编排
├── scripts/                # 初始化与维护脚本
│   ├── init_db_tables.py   # 数据库表初始化
│   └── update_stock_list_db.py # 股票列表更新
├── src/
│   ├── data_acquisition/   # 数据采集核心
│   │   ├── data_fetcher.py # 基础行情接口
│   │   └── deep_analysis_fetcher.py # (New) 深度分析多源接口
│   ├── data_storage/       # 数据库模型与 CRUD
│   ├── strategy_engine/    # 策略核心 (MACD/RSI/Bollinger)
│   │   └── multifactor_stock_picker.py # (New) 多因子选股引擎（短/中/长 + 偏好战法）
│   ├── signals/            # 信号生成逻辑
│   ├── scheduling/         # 任务调度 (APScheduler)
│   ├── notification/       # 消息推送 (Email)
│   └── presentation/       # Streamlit 前端界面
│       ├── app.py          # 主入口
│       ├── stock_detail.py # 个股详情页
│       └── top_picks.py    # (New) AI优选页面
│       └── multifactor_picks.py # (New) 多因子选股页面
└── logs/                   # 系统运行日志
```
