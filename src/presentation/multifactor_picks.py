import streamlit as st
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.data_acquisition import data_fetcher
from src.logger import logger
from src.strategy_engine.multifactor_stock_picker import score_candidates, build_horizon_config, PREFERENCES, PreferenceKey


@st.cache_data(ttl=3600, show_spinner=False)
def cached_kline(code: str) -> pd.DataFrame:
    return data_fetcher.fetch_stock_daily_kline(code)


def _build_candidate_pool(spot_df: pd.DataFrame, horizon: str, pool_size: int) -> pd.DataFrame:
    df = spot_df.copy()
    for col in ["pct_change", "turnover_rate", "volume_ratio", "price"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["code", "name", "price"])
    df = df[(df["price"] > 1)]
    df = df[~df["name"].astype(str).str.contains("ST")]

    if horizon == "short":
        df = df[
            (df["pct_change"] > 0)
            & (df["pct_change"] < 6)
            & (df["turnover_rate"] > 2)
            & (df["volume_ratio"] > 1.3)
        ]
        df = df.sort_values(["volume_ratio", "turnover_rate"], ascending=False)
    elif horizon == "mid":
        df = df[(df["turnover_rate"] > 1)]
        df = df.sort_values(["turnover_rate", "volume_ratio"], ascending=False)
    else:
        df = df[(df["turnover_rate"] > 0.5)]
        df = df.sort_values(["turnover_rate", "price"], ascending=False)

    return df.head(pool_size).reset_index(drop=True)


def _render_result_block(title: str, holding_period: str, picks: list[dict]):
    st.subheader(f"{title}（{holding_period}）")

    if not picks:
        st.warning("本次扫描未能给出有效推荐（候选池或历史数据不足）。")
        return

    show_df = pd.DataFrame(picks)
    show_df["prob"] = (show_df["prob"] * 100).round(1).astype(str) + "%"
    if "neighbor_attention" in show_df.columns:
        show_df["neighbor_attention"] = pd.to_numeric(show_df["neighbor_attention"], errors="coerce")
        show_df["neighbor_attention"] = (show_df["neighbor_attention"] * 100).round(0).astype("Int64").astype(str) + "%"

    st.dataframe(
        show_df[
            [
                "name",
                "code",
                "score",
                "prob",
                "pct_change",
                "turnover_rate",
                "volume_ratio",
                "neighbor_attention",
                "reason",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

def _calc_neighbor_attention(codes: list[str], spot_df: pd.DataFrame, k: int = 3) -> dict[str, float]:
    """
    简化版“注意力溢出”代理：
    - 按“同市场 + 代码数值”排序
    - 取相邻 k 个股票的“热度”（|涨幅| + 换手 + 量比）的均值
    - 最终对候选集合做 rank 到 [0,1]
    """
    if spot_df.empty or not codes:
        return {c: 0.0 for c in codes}

    df = spot_df[["code", "pct_change", "turnover_rate", "volume_ratio"]].copy()
    for col in ["pct_change", "turnover_rate", "volume_ratio"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    def parse_key(code: str):
        c = str(code).lower().replace(".", "")
        market = "sh" if c.startswith("sh") else "sz" if c.startswith("sz") else c[:2]
        num = "".join([ch for ch in c if ch.isdigit()])
        try:
            n = int(num)
        except Exception:
            n = -1
        return market, n

    df["market"] = df["code"].map(lambda x: parse_key(x)[0])
    df["num"] = df["code"].map(lambda x: parse_key(x)[1])
    df = df[df["num"] >= 0]

    # 热度：|涨幅| + 换手/5 + 量比/2（缩放只是为了数值平衡）
    df["heat"] = df["pct_change"].abs().fillna(0) + (df["turnover_rate"].fillna(0) / 5.0) + (
        df["volume_ratio"].fillna(0) / 2.0
    )

    df = df.sort_values(["market", "num"]).reset_index(drop=True)
    idx_map = {c: i for i, c in enumerate(df["code"].tolist())}

    raw_scores = {}
    for code in codes:
        i = idx_map.get(code)
        if i is None:
            raw_scores[code] = 0.0
            continue
        # 取左右邻居
        neighbors = []
        for d in range(1, k + 1):
            if i - d >= 0:
                neighbors.append(i - d)
            if i + d < len(df):
                neighbors.append(i + d)
        if not neighbors:
            raw_scores[code] = 0.0
            continue
        raw_scores[code] = float(df.loc[neighbors, "heat"].mean())

    s = pd.Series(raw_scores)
    # rank 到 [0,1]
    return {c: float(s.rank(pct=True).get(c, 0.0)) for c in codes}


def render_multifactor_picks_page():
    st.title("🧠 多因子选股（短线 / 中线 / 长线）")
    st.markdown(
        """
本页基于**全市场实时快照**做候选池，再并发拉取候选池的**历史日K**计算多因子得分。

- **短线（2–5个交易日）**：更偏向动量 + 量能 + 动能走强
- **中线（2–8周）**：更偏向趋势结构 + 动量 + 波动控制
- **长线（9周以上）**：更偏向中长期趋势 + 回撤控制 + 稳定性

> 注意：这里的“推荐概率”是**推荐置信度映射**（由得分函数映射而来），不是收益概率承诺。
        """
    )

    with st.expander("参数（可选）", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            short_pool = st.slider("短线候选池规模", 30, 200, 80, step=10)
            mid_pool = st.slider("中线候选池规模", 50, 300, 150, step=10)
            long_pool = st.slider("长线候选池规模", 80, 400, 220, step=10)
        with col2:
            workers = st.slider("并发线程数", 4, 20, 10, step=1)
        with col3:
            top_n = st.slider("每组输出数量（最多5）", 2, 5, 5, step=1)
            min_score = st.slider("最低得分门槛", 50, 85, 65, step=1)
            min_prob = st.slider("最低推荐置信度门槛", 0.45, 0.85, 0.55, step=0.01)

    st.subheader("🎛️ 偏好战法（可多选）")
    pref_options = [k for k in PREFERENCES.keys() if k != "trend"]
    selected_prefs: list[PreferenceKey] = st.multiselect(
        "选择你偏好的战法（不选=默认趋势动量）",
        options=pref_options,
        default=[],
        format_func=lambda k: PREFERENCES[k]["title"],
        help="勾选后会把对应因子加入短/中/长线打分，并在结果中展示更清晰的解释项。",
    )

    with st.expander("本次将使用的因子说明（按期限）", expanded=False):
        for horizon_key in ["short", "mid", "long"]:
            cfg = build_horizon_config(horizon_key, preferences=selected_prefs)
            st.markdown(f"**{cfg.title}（{cfg.holding_period}）**")
            for f in cfg.factors:
                st.write(f"- {f.name}（权重 {f.weight:.2f}，{'越高越好' if f.direction=='higher_better' else '越低越好'}）")

    if st.button("🚀 开始多因子扫描（预计 30-90 秒）", type="primary"):
        with st.status("正在扫描...", expanded=True) as status:
            st.write("1) 获取全市场实时快照...")
            spot_df = data_fetcher.fetch_all_stock_spot_realtime()
            if spot_df.empty:
                st.error("获取全市场行情失败，请稍后再试（或检查数据库股票列表是否已初始化）。")
                return

            st.write("2) 构造三种期限候选池（速度优先，只对候选池拉K线）...")
            pools = {
                "short": _build_candidate_pool(spot_df, "short", short_pool),
                "mid": _build_candidate_pool(spot_df, "mid", mid_pool),
                "long": _build_candidate_pool(spot_df, "long", long_pool),
            }

            # 合并去重，避免重复拉取 K 线
            all_codes = []
            for p in pools.values():
                all_codes.extend(p["code"].tolist())
            all_codes = list(dict.fromkeys(all_codes))

            st.write(f"3) 并发拉取候选池日K并计算因子（候选总数：{len(all_codes)}）...")
            progress = st.progress(0)
            klines: dict[str, pd.DataFrame] = {}
            realtime_rows: dict[str, dict] = {}

            # realtime_rows 需要包含 name/price/pct_change/turnover_rate/volume_ratio
            # 修复：先过滤再 set_index，避免 boolean mask 与索引不对齐导致 IndexingError
            spot_subset = spot_df.loc[
                spot_df["code"].isin(all_codes),
                ["code", "name", "price", "pct_change", "turnover_rate", "volume_ratio"],
            ].copy()
            # 防止 code 重复导致映射覆盖不稳定
            spot_subset = spot_subset.drop_duplicates(subset=["code"], keep="last")

            for _, r in spot_subset.iterrows():
                realtime_rows[str(r["code"])] = {
                    "name": r["name"],
                    "price": r["price"],
                    "pct_change": r["pct_change"],
                    "turnover_rate": r["turnover_rate"],
                    "volume_ratio": r["volume_ratio"],
                }

            # 注意力溢出：预计算邻居热度（只在用户勾选时计算，避免无谓开销）
            if "attention_spillover" in selected_prefs:
                st.write("3.1) 预计算“注意力溢出(邻居热度)”...")
                neighbor_scores = _calc_neighbor_attention(all_codes, spot_df, k=3)
                for c, s in neighbor_scores.items():
                    if c in realtime_rows:
                        realtime_rows[c]["neighbor_attention"] = s

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(cached_kline, code): code for code in all_codes}
                done = 0
                for f in as_completed(futures):
                    code = futures[f]
                    try:
                        df = f.result()
                        if df is not None and not df.empty:
                            klines[code] = df
                    except Exception as e:
                        logger.error(f"多因子选股：拉取K线失败 {code}: {e}")
                    done += 1
                    progress.progress(done / max(1, len(all_codes)))

            st.write("4) 分期限计算多因子得分并给出推荐...")
            results = {}
            for horizon_key in ["short", "mid", "long"]:
                pool_codes = set(pools[horizon_key]["code"].tolist())
                sub_klines = {c: klines[c] for c in pool_codes if c in klines}
                sub_rt = {c: realtime_rows.get(c, {}) for c in pool_codes}
                results[horizon_key] = score_candidates(
                    horizon=horizon_key,
                    klines=sub_klines,
                    realtime_rows=sub_rt,
                    preferences=selected_prefs,
                    top_n=top_n,
                    min_score=min_score,
                    min_prob=min_prob,
                )

            status.update(label="扫描完成", state="complete", expanded=False)

        st.divider()
        for horizon_key in ["short", "mid", "long"]:
            cfg = build_horizon_config(horizon_key, preferences=selected_prefs)
            _render_result_block(cfg.title, cfg.holding_period, results.get(horizon_key, []))


