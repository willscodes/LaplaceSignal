"""
laplace/factors/technical.py
技术指标因子模块。

包含：
    - TrendFactor      ── EMA20/EMA50 趋势方向
    - RSIFactor        ── RSI 超买超卖
    - MACDFactor       ── MACD 金叉 / 死叉
    - BollingerFactor  ── 布林带 %B 位置
    - VolumeFactor     ── 成交量比率 + 订单簿压力

所有因子接受 data 字典，字段来自 OKX K线分析结果。
"""

import math
from typing import Any

from .base import BaseFactor


# ================================================================
# 内置技术指标计算函数（纯函数，无副作用）
# ================================================================

def calc_ema(closes: list[float], n: int) -> list[float]:
    """指数移动平均（EMA）。"""
    if len(closes) < n:
        return []
    k = 2 / (n + 1)
    result = [sum(closes[:n]) / n]
    for c in closes[n:]:
        result.append(c * k + result[-1] * (1 - k))
    return result


def calc_rsi(closes: list[float], n: int = 14) -> float:
    """相对强弱指数（RSI），返回 0~100。"""
    if len(closes) < n + 1:
        return 50.0
    avg_gain = avg_loss = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        if d > 0:
            avg_gain += d
        else:
            avg_loss -= d
    avg_gain /= n
    avg_loss /= n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (n - 1) + (d if d > 0 else 0)) / n
        avg_loss = (avg_loss * (n - 1) + (-d if d < 0 else 0)) / n
    return round(100 - 100 / (1 + avg_gain / (avg_loss or 1e-9)), 2)


def calc_macd(closes: list[float], fast: int = 12, slow: int = 26, sig: int = 9) -> dict | None:
    """MACD（DIF / DEA / 柱状图）。"""
    if len(closes) < slow + sig:
        return None
    e12 = calc_ema(closes, fast)
    e26 = calc_ema(closes, slow)
    offset = slow - fast
    macd_line = [e12[i + offset] - e26[i] for i in range(len(e26))]
    signal_line = calc_ema(macd_line, sig)
    lm, ls = macd_line[-1], signal_line[-1]
    pm, ps = macd_line[-2], signal_line[-2]
    hist = lm - ls
    if pm <= ps and lm > ls:
        cross = "golden_cross"
    elif pm >= ps and lm < ls:
        cross = "death_cross"
    elif lm > ls:
        cross = "bullish"
    else:
        cross = "bearish"
    return {"macd": round(lm, 2), "signal": round(ls, 2), "hist": round(hist, 4), "cross": cross}


def calc_bb(closes: list[float], n: int = 20) -> dict | None:
    """布林带（Bollinger Bands）。"""
    if len(closes) < n:
        return None
    sl = closes[-n:]
    mid = sum(sl) / n
    std = math.sqrt(sum((x - mid) ** 2 for x in sl) / n)
    upper = mid + 2 * std
    lower = mid - 2 * std
    last = closes[-1]
    pct_b = (last - lower) / (upper - lower) if upper != lower else 0.5
    bw = (upper - lower) / mid * 100
    return {
        "upper": round(upper, 2),
        "mid":   round(mid, 2),
        "lower": round(lower, 2),
        "pct_b": round(pct_b, 4),
        "bw":    round(bw, 2),
    }


def calc_atr(klines: list[dict], n: int = 14) -> float:
    """Average True Range（ATR）。"""
    if len(klines) < n + 1:
        return klines[-1]["high"] - klines[-1]["low"]
    trs = [
        max(
            klines[i]["high"] - klines[i]["low"],
            abs(klines[i]["high"] - klines[i - 1]["close"]),
            abs(klines[i]["low"]  - klines[i - 1]["close"]),
        )
        for i in range(1, len(klines))
    ]
    atr = sum(trs[:n]) / n
    for t in trs[n:]:
        atr = (atr * (n - 1) + t) / n
    return round(atr, 2)


def calc_adx(klines: list[dict], n: int = 14) -> float:
    """Average Directional Index（ADX），表示趋势强度 0~100。"""
    if len(klines) < n * 2:
        return 20.0
    plus_dms, minus_dms, trs = [], [], []
    for i in range(1, len(klines)):
        h  = klines[i]["high"];     l  = klines[i]["low"]
        ph = klines[i - 1]["high"]; pl = klines[i - 1]["low"]
        pc = klines[i - 1]["close"]
        up = h - ph; dn = pl - l
        plus_dms.append(up if up > dn and up > 0 else 0)
        minus_dms.append(dn if dn > up and dn > 0 else 0)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))

    def wilder(vals: list[float], period: int) -> list[float]:
        r = [sum(vals[:period])]
        for v in vals[period:]:
            r.append(r[-1] - r[-1] / period + v)
        return r

    atr14  = wilder(trs, n)
    pdm14  = wilder(plus_dms, n)
    mdm14  = wilder(minus_dms, n)
    dxs = []
    for i in range(len(atr14)):
        pdi = 100 * pdm14[i] / (atr14[i] or 1e-9)
        mdi = 100 * mdm14[i] / (atr14[i] or 1e-9)
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi or 1e-9))
    return round(sum(dxs[-n:]) / n, 2)


def calc_trend(closes: list[float]) -> dict:
    """EMA20/50 趋势判断。"""
    if len(closes) < 50:
        return {"trend": "unknown", "ema20": 0.0, "ema50": 0.0, "vs_ema20": 0.0}
    e20 = calc_ema(closes, 20)[-1]
    e50 = calc_ema(closes, 50)[-1]
    p   = closes[-1]
    if   p > e20 and e20 > e50: trend = "uptrend"
    elif p < e20 and e20 < e50: trend = "downtrend"
    elif p > e20 and e20 < e50: trend = "recovery"
    else:                        trend = "weakening"
    return {
        "trend":    trend,
        "ema20":    round(e20, 2),
        "ema50":    round(e50, 2),
        "vs_ema20": round((p - e20) / e20 * 100, 2),
    }


# ================================================================
# 因子类
# ================================================================

class TrendFactor(BaseFactor):
    """EMA20/50 趋势方向因子。

    data 键：
        m1h, m4h, m1d ── 各周期 analyze() 结果（含 trend 字段）
    """

    name   = "trend"
    weight = 25.0

    _TREND_MAP = {
        "uptrend":   1.0,
        "recovery":  0.5,
        "weakening": -0.3,
        "downtrend": -1.0,
        "unknown":    0.0,
    }

    def compute(self, data: dict[str, Any]) -> float:
        t1h = self._TREND_MAP.get(data["m1h"]["trend"]["trend"], 0.0)
        t4h = self._TREND_MAP.get(data["m4h"]["trend"]["trend"], 0.0)
        t1d = self._TREND_MAP.get(data["m1d"]["trend"]["trend"], 0.0)
        # 1H权重25%，4H权重45%，日线权重30%
        return t1h * 0.25 + t4h * 0.45 + t1d * 0.30


class RSIFactor(BaseFactor):
    """RSI 超买超卖因子（市场状态敏感）。

    data 键：
        m1h, m4h, m1d  ── 各周期分析结果（含 rsi 字段）
        market_state   ── "TRENDING" | "RANGING" | "TRANSITIONING"
    """

    name   = "rsi"
    weight = 14.0

    @staticmethod
    def _rsi_norm(rsi: float, state: str) -> float:
        if state == "RANGING":
            if rsi < 30: return  1.0
            if rsi < 40: return  0.5
            if rsi > 70: return -1.0
            if rsi > 60: return -0.5
            return 0.0
        else:  # TRENDING / TRANSITIONING
            if rsi > 70: return -0.3
            if rsi > 55: return  0.6
            if rsi > 50: return  0.2
            if rsi > 40: return -0.2
            return -0.7

    def compute(self, data: dict[str, Any]) -> float:
        state = data.get("market_state", "TRENDING")
        rn = (
            self._rsi_norm(data["m1h"]["rsi"], state) * 0.30 +
            self._rsi_norm(data["m4h"]["rsi"], state) * 0.45 +
            self._rsi_norm(data["m1d"]["rsi"], state) * 0.25
        )
        return rn


class MACDFactor(BaseFactor):
    """MACD 金叉 / 死叉因子。

    data 键：
        m1h, m4h, m1d ── 各周期分析结果（含 macd 字段）
    """

    name   = "macd"
    weight = 14.0

    _CROSS_MAP = {
        "golden_cross": 1.0,
        "bullish":      0.4,
        "bearish":     -0.4,
        "death_cross": -1.0,
    }

    def _macd_norm(self, m: dict | None) -> float:
        if m is None:
            return 0.0
        base = self._CROSS_MAP.get(m["cross"], 0.0)
        hist_boost = min(0.3, abs(m["hist"]) / (abs(m["macd"]) or 1e-9))
        hist_boost *= 1 if m["hist"] > 0 else -1
        return self.clamp(base + hist_boost)

    def compute(self, data: dict[str, Any]) -> float:
        return (
            self._macd_norm(data["m1h"]["macd"]) * 0.30 +
            self._macd_norm(data["m4h"]["macd"]) * 0.45 +
            self._macd_norm(data["m1d"]["macd"]) * 0.25
        )


class BollingerFactor(BaseFactor):
    """布林带 %B 位置因子（市场状态敏感）。

    data 键：
        m1h, m4h, m1d  ── 各周期分析结果（含 bb 字段）
        market_state   ── "TRENDING" | "RANGING" | "TRANSITIONING"
    """

    name   = "bollinger"
    weight = 10.0

    @staticmethod
    def _bb_norm(pct_b: float, state: str) -> float:
        if state == "RANGING":
            if pct_b > 0.95: return -1.0
            if pct_b > 0.80: return -0.5
            if pct_b < 0.05: return  1.0
            if pct_b < 0.20: return  0.5
            return 0.0
        else:
            if pct_b > 0.80: return  0.6
            if pct_b > 0.50: return  0.3
            if pct_b < 0.20: return -0.6
            return 0.0

    def compute(self, data: dict[str, Any]) -> float:
        state = data.get("market_state", "TRENDING")
        bb1h = data["m1h"].get("bb") or {}
        bb4h = data["m4h"].get("bb") or {}
        bb1d = data["m1d"].get("bb") or {}
        bn = (
            self._bb_norm(bb1h.get("pct_b", 0.5), state) * 0.35 +
            self._bb_norm(bb4h.get("pct_b", 0.5), state) * 0.40 +
            self._bb_norm(bb1d.get("pct_b", 0.5), state) * 0.25
        )
        return bn


class VolumeFactor(BaseFactor):
    """成交量比率 + 订单簿压力因子。

    data 键：
        m1h, m4h    ── 各周期分析结果（含 vol_ratio 字段）
        orderbook   ── get_orderbook() 返回值（可选）
        trend_dir   ── 趋势方向 +1 / -1（由 TrendFactor 计算）
    """

    name   = "volume"
    weight = 6.0

    def compute(self, data: dict[str, Any]) -> float:
        vr1 = data["m1h"].get("vol_ratio", 1.0)
        vr4 = data["m4h"].get("vol_ratio", 1.0)
        vol_conf = min(1.0, (vr1 * 0.5 + vr4 * 0.5 - 0.4) / 1.2)
        ob = data.get("orderbook")
        ob_n = 0.0
        if ob:
            if ob["pressure"] == "buy_heavy":
                ob_n =  0.4
            elif ob["pressure"] == "sell_heavy":
                ob_n = -0.4
        trend_dir = data.get("trend_dir", 1)
        vol_score = self.clamp(vol_conf * 0.7 + ob_n * 0.3)
        return vol_score * trend_dir
