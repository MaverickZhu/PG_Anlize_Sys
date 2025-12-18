from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Literal

import numpy as np
import pandas as pd
import pandas_ta as ta


Direction = Literal["higher_better", "lower_better"]
PreferenceKey = Literal["trend", "volume_reversal", "liquidity_quality", "attention_spillover"]


@dataclass(frozen=True)
class FactorSpec:
    name: str
    weight: float
    direction: Direction
    compute: Callable[[pd.DataFrame, dict], float]


@dataclass(frozen=True)
class HorizonConfig:
    key: Literal["short", "mid", "long"]
    title: str
    holding_period: str
    min_history_days: int
    factors: tuple[FactorSpec, ...]


def _safe_last(series: pd.Series) -> float:
    if series is None or len(series) == 0:
        return np.nan
    try:
        return float(series.iloc[-1])
    except Exception:
        return np.nan


def _ret_n(df: pd.DataFrame, n: int) -> float:
    if df is None or df.empty or "close" not in df.columns or len(df) <= n:
        return np.nan
    c = df["close"]
    prev = c.iloc[-(n + 1)]
    last = c.iloc[-1]
    if prev == 0:
        return np.nan
    return float(last / prev - 1.0)


def _vol_ratio_n(df: pd.DataFrame, n: int = 5) -> float:
    if df is None or df.empty or "volume" not in df.columns or len(df) < n + 1:
        return np.nan
    v = df["volume"].astype(float)
    base = float(v.iloc[-(n + 1) : -1].mean())
    if base <= 0:
        return np.nan
    return float(v.iloc[-1] / base)


def _rsi14(df: pd.DataFrame) -> float:
    if df is None or df.empty or "close" not in df.columns or len(df) < 20:
        return np.nan
    s = df["close"].astype(float)
    rsi = ta.rsi(s, length=14)
    return _safe_last(rsi)


def _rsi_band_score(df: pd.DataFrame, low: float, high: float) -> float:
    """
    在目标区间内得分高，越偏离越低（0-1）。
    """
    r = _rsi14(df)
    if np.isnan(r):
        return np.nan
    if low <= r <= high:
        return 1.0
    # 简单的线性衰减
    if r < low:
        return float(max(0.0, 1.0 - (low - r) / 30.0))
    return float(max(0.0, 1.0 - (r - high) / 30.0))


def _macd_hist_slope(df: pd.DataFrame) -> float:
    if df is None or df.empty or "close" not in df.columns or len(df) < 40:
        return np.nan
    s = df["close"].astype(float)
    macd = ta.macd(s, fast=12, slow=26, signal=9)
    if macd is None or macd.empty:
        return np.nan
    hist_col = [c for c in macd.columns if c.startswith("MACDh_")]
    if not hist_col:
        return np.nan
    h = macd[hist_col[0]]
    if len(h) < 2:
        return np.nan
    return float(h.iloc[-1] - h.iloc[-2])


def _ma_gap(df: pd.DataFrame, n: int) -> float:
    if df is None or df.empty or "close" not in df.columns or len(df) < n + 5:
        return np.nan
    c = df["close"].astype(float)
    ma = c.rolling(n).mean()
    last_ma = _safe_last(ma)
    last = float(c.iloc[-1])
    if last_ma == 0 or np.isnan(last_ma):
        return np.nan
    return float(last / last_ma - 1.0)


def _ma_stack(df: pd.DataFrame, fast: int, slow: int) -> float:
    """
    close > MA_fast > MA_slow 时为 1，否则 0
    """
    if df is None or df.empty or "close" not in df.columns or len(df) < slow + 5:
        return np.nan
    c = df["close"].astype(float)
    ma_fast = c.rolling(fast).mean()
    ma_slow = c.rolling(slow).mean()
    last = float(c.iloc[-1])
    f = _safe_last(ma_fast)
    s = _safe_last(ma_slow)
    if np.isnan(f) or np.isnan(s):
        return np.nan
    return float(1.0 if (last > f and f > s) else 0.0)


def _volatility(df: pd.DataFrame, n: int) -> float:
    if df is None or df.empty or "close" not in df.columns or len(df) < n + 5:
        return np.nan
    r = df["close"].astype(float).pct_change()
    return float(r.iloc[-n:].std())


def _max_drawdown(df: pd.DataFrame, n: int) -> float:
    if df is None or df.empty or "close" not in df.columns or len(df) < n + 5:
        return np.nan
    c = df["close"].astype(float).iloc[-n:]
    peak = c.cummax()
    dd = (c / peak) - 1.0
    return float(dd.min())  # 负数，越接近 0 越好


def _patv_lite(df: pd.DataFrame, window: int = 20, persist: int = 10) -> float:
    """
    PATV(简化)：衡量“持续异常交易量”强度。
    - 用 volume / MA(volume, window) 作为异常量强度
    - 用最近 persist 天的异常比例作为“持续性”
    数值越大代表越“持续异常”，按研报逻辑更偏向未来下跌风险 -> 通常作为 lower_better 使用。
    """
    if df is None or df.empty or "volume" not in df.columns or len(df) < window + persist + 2:
        return np.nan
    v = df["volume"].astype(float)
    ma = v.rolling(window).mean()
    vr = v / ma
    vr = vr.replace([np.inf, -np.inf], np.nan)
    last_vr = float(vr.iloc[-1]) if pd.notna(vr.iloc[-1]) else np.nan
    recent = vr.iloc[-persist:]
    if recent.isna().all():
        return np.nan
    # 异常阈值：1.5 倍（可在 UI 侧做参数化，先保持 KISS）
    persist_ratio = float((recent > 1.5).mean())
    return float((np.nan_to_num(last_vr, nan=1.0)) * (0.5 + persist_ratio))


def _illiq_proxy(df: pd.DataFrame, window: int = 20) -> float:
    """
    Amihud ILLIQ 的简化代理：
      ILLIQ_proxy = mean( |ret| / volume )
    注：理想情况应使用“成交额”而非成交量；当前腾讯日K未提供 turnover，这里先用 volume 近似。
    数值越大越“非流动”（冲击成本更高）-> 通常 lower_better。
    """
    if df is None or df.empty or "close" not in df.columns or "volume" not in df.columns or len(df) < window + 2:
        return np.nan
    c = df["close"].astype(float)
    v = df["volume"].astype(float).replace(0, np.nan)
    r = c.pct_change().abs()
    x = (r / v).iloc[-window:]
    return float(x.mean())


def _build_horizons() -> tuple[HorizonConfig, ...]:
    short_factors = (
        FactorSpec("近3日动量", 0.28, "higher_better", lambda df, rt: _ret_n(df, 3)),
        FactorSpec("MACD动能走强", 0.18, "higher_better", lambda df, rt: _macd_hist_slope(df)),
        FactorSpec("量能放大(5日)", 0.18, "higher_better", lambda df, rt: _vol_ratio_n(df, 5)),
        FactorSpec("RSI舒适区(45-70)", 0.18, "higher_better", lambda df, rt: _rsi_band_score(df, 45, 70)),
        FactorSpec("近20日回撤更小", 0.18, "higher_better", lambda df, rt: 1.0 + _max_drawdown(df, 20)),
    )

    mid_factors = (
        FactorSpec("近20日动量", 0.26, "higher_better", lambda df, rt: _ret_n(df, 20)),
        FactorSpec("均线多头(20>60)", 0.22, "higher_better", lambda df, rt: _ma_stack(df, 20, 60)),
        FactorSpec("价格强于MA20", 0.18, "higher_better", lambda df, rt: _ma_gap(df, 20)),
        FactorSpec("波动更低(20日)", 0.18, "lower_better", lambda df, rt: _volatility(df, 20)),
        FactorSpec("RSI舒适区(40-70)", 0.16, "higher_better", lambda df, rt: _rsi_band_score(df, 40, 70)),
    )

    long_factors = (
        FactorSpec("近120日动量", 0.30, "higher_better", lambda df, rt: _ret_n(df, 120)),
        FactorSpec("均线多头(60>120)", 0.22, "higher_better", lambda df, rt: _ma_stack(df, 60, 120)),
        FactorSpec("近120日回撤更小", 0.20, "higher_better", lambda df, rt: 1.0 + _max_drawdown(df, 120)),
        FactorSpec("波动更低(60日)", 0.18, "lower_better", lambda df, rt: _volatility(df, 60)),
        FactorSpec("价格强于MA120", 0.10, "higher_better", lambda df, rt: _ma_gap(df, 120)),
    )

    return (
        HorizonConfig("short", "短线选股", "2–5 个交易日", 60, short_factors),
        HorizonConfig("mid", "中线选股", "2–8 周", 160, mid_factors),
        HorizonConfig("long", "长线选股", "9 周以上", 260, long_factors),
    )


HORIZONS = {h.key: h for h in _build_horizons()}


PREFERENCES: dict[PreferenceKey, dict] = {
    "trend": {
        "title": "趋势动量（默认）",
        "desc": "偏向动量/趋势结构/回撤控制（适合顺势）",
    },
    "volume_reversal": {
        "title": "量能反转（PATV）",
        "desc": "引入持续异常量(PATV简化)做风险约束，避免“放量但脆弱”的标的",
    },
    "liquidity_quality": {
        "title": "流动性稳健（ILLIQ）",
        "desc": "引入非流动性(ILLIQ代理)与波动约束，偏向更稳的可交易标的",
    },
    "attention_spillover": {
        "title": "注意力溢出（邻居热度）",
        "desc": "引入“邻居热度”作为注意力溢出代理（需要快照预计算 neighbor_attention）",
    },
}


def build_horizon_config(
    horizon: Literal["short", "mid", "long"],
    preferences: Iterable[PreferenceKey] | None = None,
) -> HorizonConfig:
    """
    根据用户偏好动态组装因子集合（在不破坏原有默认因子的基础上增量添加）。
    """
    base = HORIZONS[horizon]
    prefs = set(preferences or [])

    extra: list[FactorSpec] = []

    if "volume_reversal" in prefs:
        extra.append(FactorSpec("持续异常量PATV(简化)", 0.12, "lower_better", lambda df, ctx: _patv_lite(df)))

    if "liquidity_quality" in prefs:
        extra.append(FactorSpec("非流动性ILLIQ(代理)", 0.10, "lower_better", lambda df, ctx: _illiq_proxy(df)))

    if "attention_spillover" in prefs:
        # 需要 ctx 里包含 neighbor_attention（0-1），缺失则记 NaN
        extra.append(
            FactorSpec(
                "注意力溢出(邻居热度)",
                0.10,
                "higher_better",
                lambda df, ctx: float(ctx.get("neighbor_attention")) if ctx.get("neighbor_attention") is not None else np.nan,
            )
        )

    if not extra:
        return base

    # 直接追加；weight 会在 score_candidates 内部做归一化
    return HorizonConfig(
        key=base.key,
        title=base.title,
        holding_period=base.holding_period,
        min_history_days=base.min_history_days,
        factors=tuple(base.factors) + tuple(extra),
    )


def score_candidates(
    horizon: Literal["short", "mid", "long"],
    klines: dict[str, pd.DataFrame],
    realtime_rows: dict[str, dict],
    preferences: Iterable[PreferenceKey] | None = None,
    top_n: int = 5,
    min_score: float = 65.0,
    min_prob: float = 0.55,
) -> list[dict]:
    """
    输入候选股票的 K 线与实时数据，输出该期限的推荐列表。
    """
    cfg = build_horizon_config(horizon, preferences)

    rows: list[dict] = []
    for code, df in klines.items():
        if df is None or df.empty or len(df) < cfg.min_history_days:
            continue
        ctx = realtime_rows.get(code, {})  # ctx: realtime + 预计算字段
        row = {"code": code, "name": ctx.get("name", code)}
        for f in cfg.factors:
            row[f.name] = f.compute(df, ctx)
        rows.append(row)

    if not rows:
        return []

    factor_df = pd.DataFrame(rows).set_index("code")

    # 标准化到 [0,1]：rank percentile；对 lower_better 取反
    factor_scores = {}
    for f in cfg.factors:
        s = pd.to_numeric(factor_df[f.name], errors="coerce")
        s = s.replace([np.inf, -np.inf], np.nan)
        pct = s.rank(pct=True, na_option="bottom")
        if f.direction == "lower_better":
            pct = 1.0 - pct
        factor_scores[f.name] = pct

    score_df = pd.DataFrame(factor_scores)
    weight_sum = float(sum(f.weight for f in cfg.factors)) or 1.0
    weights = {f.name: float(f.weight) / weight_sum for f in cfg.factors}

    score = 0.0
    for name, w in weights.items():
        score = score + score_df[name] * w

    score_df["score"] = (score * 100.0).round(1)
    # 推荐概率：用 sigmoid 拉开高分段差异（非收益概率，仅作“推荐置信度”）
    score_df["prob"] = (1.0 / (1.0 + np.exp(-(score_df["score"] - 60.0) / 8.0))).round(3)

    # 生成解释：取贡献最大的 3 个因子
    def build_reason(code: str) -> str:
        contrib = {}
        for name, w in weights.items():
            v = score_df.loc[code, name]
            if pd.isna(v):
                continue
            contrib[name] = float(v) * w
        top = sorted(contrib.items(), key=lambda x: x[1], reverse=True)[:3]
        return "；".join([f"{k}（Top）" for k, _ in top]) if top else ""

    # 合并基础字段
    out = []
    for code in score_df.sort_values(["score", "prob"], ascending=False).index.tolist():
        rt = realtime_rows.get(code, {})
        out.append(
            {
                "code": code,
                "name": rt.get("name", code),
                "price": rt.get("price", np.nan),
                "pct_change": rt.get("pct_change", np.nan),
                "turnover_rate": rt.get("turnover_rate", np.nan),
                "volume_ratio": rt.get("volume_ratio", np.nan),
                "neighbor_attention": rt.get("neighbor_attention", np.nan),
                "score": float(score_df.loc[code, "score"]),
                "prob": float(score_df.loc[code, "prob"]),
                "reason": build_reason(code),
            }
        )

    # 过滤后取 top_n；如果过滤导致少于2只，则退化为取 top_n（但仍最多5）
    filtered = [x for x in out if x["score"] >= min_score and x["prob"] >= min_prob]
    final = filtered[:top_n]
    if len(final) < 2:
        final = out[: max(2, min(top_n, 5))]
    return final[: min(top_n, 5)]


