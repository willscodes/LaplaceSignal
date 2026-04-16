"""
laplace/factors/derivatives.py
Derivatives factor module — OKX Level-1 & Deribit Level-2 real-time data.

Factors:
    - FundingRateFactor      ── Spot funding rate bias (basic)
    - FundingRateEMAFactor   ── Funding rate EMA-8 / EMA-24 trend signal (Level-2)
    - OIVelocityFactor       ── OI velocity (1H / 3H change %)
    - TakerFlowFactor        ── Taker buy/sell flow ratio (6H)
    - LiquidationFactor      ── Liquidation direction pressure
    - LongShortRatioFactor   ── Long/Short account ratio (contrarian)
    - PCRFactor              ── Deribit Put/Call Ratio (Level-2 options sentiment)
"""

from typing import Any

from .base import BaseFactor


# ================================================================
# Level-1 Funding Rate (basic spot signal)
# ================================================================

class FundingRateFactor(BaseFactor):
    """Spot funding rate factor.

    Positive funding → longs paying shorts → overbought (bearish signal)
    Negative funding → shorts paying longs → bearish overcrowding (bullish signal)

    Expected data keys:
        funding ── {"current": float, "next": float}
    """

    name   = "funding"
    weight = 5.0

    # 0.03% treated as "extreme" rate — normalization base
    _NORM_BASE = 0.0003

    def compute(self, data: dict[str, Any]) -> float:
        funding = data.get("funding") or {}
        rate = funding.get("current", 0.0)
        # High funding rate → longs overheated → bearish (negate)
        norm = -(rate / self._NORM_BASE)
        return self.clamp(norm)


# ================================================================
# Level-2 Funding Rate EMA (trend signal from history)
# ================================================================

class FundingRateEMAFactor(BaseFactor):
    """Funding rate EMA trend factor (Level-2).

    Computes EMA-8 and EMA-24 over the last 24 funding rate periods
    (OKX: /api/v5/public/funding-rate-history).

    Signal logic (mirrors CTIS get_funding_ema):
        ema8 < ema24 AND current < 0  → bearish  (-1.0)
        ema8 > ema24 AND current > 0  → bullish  (+1.0)
        otherwise                     → neutral  (0.0)

    Expected data keys:
        funding_ema ── {
            "ema8":    float,   # EMA of last 8 funding periods
            "ema24":   float,   # EMA of last 24 funding periods
            "current": float,   # most recent funding rate
            "signal":  str,     # "bullish" | "bearish" | "neutral"
        }
    """

    name   = "funding_ema"
    weight = 5.0

    def compute(self, data: dict[str, Any]) -> float:
        fe = data.get("funding_ema")
        if not fe:
            return 0.0

        e8   = fe.get("ema8", 0.0)
        e24  = fe.get("ema24", 0.0)
        sig  = fe.get("signal", "neutral")

        if e8 < e24 and sig == "bearish":
            return -1.0
        elif e8 > e24 and sig == "bullish":
            return 1.0
        else:
            return 0.0


# ================================================================
# Level-1 OI Velocity
# ================================================================

class OIVelocityFactor(BaseFactor):
    """OI velocity factor.

    Rising OI + rising price → trend reinforcement (bullish)
    Falling OI              → position unwinding / reversal warning

    Expected data keys:
        oi_velocity ── {
            "chg_1h_pct":           float,
            "chg_3h_pct":           float,
            "latest_oi":            int,
            "direction_consistent": bool,   # True if last 3 OI moves are same direction
        }
        trend_dir   ── +1 (uptrend) / -1 (downtrend)
    """

    name   = "oi_velocity"
    weight = 2.0

    def compute(self, data: dict[str, Any]) -> float:
        oi_velocity = data.get("oi_velocity")
        if not oi_velocity:
            return 0.0

        c1 = oi_velocity["chg_1h_pct"]
        c3 = oi_velocity["chg_3h_pct"]
        consistent = oi_velocity.get("direction_consistent", False)

        vel_raw = c1 * 0.6 + c3 * 0.4
        vel_n   = self.clamp(vel_raw / 2.0)

        # Direction consistency boost: more reliable when persistent
        if consistent:
            vel_n = self.clamp(vel_n * 1.3)

        trend_dir = data.get("trend_dir", 1)
        return vel_n * trend_dir


# ================================================================
# Level-1 Taker Flow
# ================================================================

class TakerFlowFactor(BaseFactor):
    """Taker buy/sell flow ratio factor.

    Active buy volume > active sell volume → bullish conviction

    Expected data keys:
        taker_flow ── {
            "latest":      float,   # buy/sell ratio of most recent period
            "avg_6h":      float,   # 6H rolling average ratio
            "momentum":    float,   # (latest - avg_6h) / avg_6h
            "buy_vol_6h":  float,
            "sell_vol_6h": float,
        }
    """

    name   = "taker_flow"
    weight = 8.0

    def compute(self, data: dict[str, Any]) -> float:
        tf = data.get("taker_flow")
        if not tf:
            return 0.0

        total_vol = tf.get("buy_vol_6h", 0) + tf.get("sell_vol_6h", 0)
        if total_vol <= 0:
            return 0.0

        r = tf["latest"]
        m = tf["momentum"]

        # Tier-based flow classification
        if   r > 1.3: base_n =  1.0
        elif r > 1.1: base_n =  0.5
        elif r > 0.9: base_n =  0.0
        elif r > 0.7: base_n = -0.5
        else:         base_n = -1.0

        # Momentum boost (capped at ±0.3; extra bonus if momentum > 0.15)
        mom_boost = self.clamp(m * 1.5, -0.3, 0.3)
        if m >  0.15: mom_boost = min( 0.3, mom_boost + 0.2)
        if m < -0.15: mom_boost = max(-0.3, mom_boost - 0.2)

        return self.clamp(base_n + mom_boost)


# ================================================================
# Level-1 Liquidation Pressure
# ================================================================

class LiquidationFactor(BaseFactor):
    """Liquidation direction pressure factor.

    Heavy short liquidations → shorts washed out → bullish
    Heavy long  liquidations → longs washed out  → bearish

    Expected data keys:
        liq_pressure ── {
            "long_liq":          float,   # USD value of long liquidations
            "short_liq":         float,   # USD value of short liquidations
            "total":             float,
            "short_long_ratio":  float,   # short_liq / long_liq
        }
    """

    name   = "liquidation"
    weight = 3.0

    # Minimum liquidation size threshold (USD); signal unreliable below this
    _MIN_TOTAL_USD = 50_000

    def compute(self, data: dict[str, Any]) -> float:
        lp = data.get("liq_pressure")
        if not lp:
            return 0.0
        if lp["total"] < self._MIN_TOTAL_USD:
            return 0.0

        r = lp["short_long_ratio"]
        if   r > 3.0:  return  1.0
        elif r > 1.5:  return  0.5
        elif r > 0.67: return  0.0
        elif r > 0.33: return -0.5
        else:          return -1.0


# ================================================================
# Level-1 Long/Short Ratio (contrarian)
# ================================================================

class LongShortRatioFactor(BaseFactor):
    """Long/Short account ratio factor (contrarian).

    High long account ratio → market euphoria → mild bearish signal
    High short account ratio → pessimism → mild bullish signal

    Expected data keys:
        ls_ratio ── {"current": float, "trend": float}
    """

    name   = "ls_ratio"
    weight = 0.0  # Default 0; overridden via WeightManager

    def compute(self, data: dict[str, Any]) -> float:
        ls = data.get("ls_ratio")
        if not ls:
            return 0.0
        ls_val   = ls["current"] if isinstance(ls, dict) else float(ls)
        ls_trend = ls.get("trend", 0.0) if isinstance(ls, dict) else 0.0
        # current ≈ 1.0 = neutral; >1 = more longs; <1 = more shorts
        ls_n        = self.clamp((ls_val - 1.0) * 2)
        trend_boost = self.clamp(ls_trend * 5, -0.2, 0.2)
        return self.clamp(ls_n + trend_boost)


# ================================================================
# Level-2 Put/Call Ratio (Deribit options sentiment)
# ================================================================

class PCRFactor(BaseFactor):
    """Deribit Put/Call Ratio factor (Level-2).

    Fetches BTC options book summary from Deribit API
    (https://www.deribit.com/api/v2/public/get_book_summary_by_currency).

    Signal logic (mirrors CTIS get_deribit_pcr):
        PCR > 1.3  → extreme fear  → contrarian bullish  (+0.8)
        PCR < 0.7  → extreme greed → contrarian bearish  (-0.8)
        0.7 ≤ PCR ≤ 1.3 → linear interpolation between -0.8 and +0.8

    Expected data keys:
        pcr ── {
            "pcr":      float,   # put_vol / call_vol
            "put_vol":  float,
            "call_vol": float,
            "signal":   str,     # "fear" | "greed" | "neutral"
        }
        OR
        pcr ── float   (raw PCR value)
    """

    name   = "pcr"
    weight = 4.0

    # Contrarian signal cap (max absolute score before weight scaling)
    _SIGNAL_CAP = 0.8

    def compute(self, data: dict[str, Any]) -> float:
        pcr_raw = data.get("pcr")
        if pcr_raw is None:
            return 0.0

        pcr_val = pcr_raw["pcr"] if isinstance(pcr_raw, dict) else float(pcr_raw)

        if pcr_val > 1.3:
            # Extreme fear → contrarian bullish
            return self._SIGNAL_CAP
        elif pcr_val < 0.7:
            # Extreme greed → contrarian bearish
            return -self._SIGNAL_CAP
        else:
            # Linear interpolation: 0.7 → -0.8, 1.0 → 0, 1.3 → +0.8
            score = (pcr_val - 1.0) / 0.3 * self._SIGNAL_CAP
            return self.clamp(round(score, 4), -self._SIGNAL_CAP, self._SIGNAL_CAP)
