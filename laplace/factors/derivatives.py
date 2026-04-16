"""
laplace/factors/derivatives.py
衍生品因子模块 —— OKX Level-1 实时数据。

包含：
    - FundingRateFactor    ── 资金费率 EMA 偏离
    - OIVelocityFactor     ── OI 增速（1H / 3H）
    - TakerFlowFactor      ── Taker 买卖流量比
    - LiquidationFactor    ── 爆仓方向压力
    - LongShortRatioFactor ── 多空账户比（PCR 替代）
"""

from typing import Any

from .base import BaseFactor


class FundingRateFactor(BaseFactor):
    """资金费率因子。

    正资金费率 → 多头支付空头 → 看空（价格可能均值回归向下）
    负资金费率 → 空头支付多头 → 看多

    data 键：
        funding ── {"current": float, "next": float}
    """

    name   = "funding"
    weight = 5.0

    # 0.03% 视为"极端"费率，归一化基准
    _NORM_BASE = 0.0003

    def compute(self, data: dict[str, Any]) -> float:
        funding = data.get("funding") or {}
        rate = funding.get("current", 0.0)
        # 资金费率高 → 多头过热 → 信号偏空（取负号）
        norm = -(rate / self._NORM_BASE)
        return self.clamp(norm)


class OIVelocityFactor(BaseFactor):
    """OI 增速因子。

    OI 快速上涨 + 价格上涨 → 趋势增强（看多）
    OI 快速下跌             → 平仓 / 反转预警

    data 键：
        oi_velocity ── {"chg_1h_pct": float, "chg_3h_pct": float,
                         "latest_oi": int, "direction_consistent": bool}
        trend_dir   ── 趋势方向 +1 / -1
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
        # 方向一致性加成：信号可信度更高
        if consistent:
            vel_n = self.clamp(vel_n * 1.3)
        trend_dir = data.get("trend_dir", 1)
        return vel_n * trend_dir


class TakerFlowFactor(BaseFactor):
    """Taker 买卖流量比因子。

    买方主动成交 > 卖方主动成交 → 看多

    data 键：
        taker_flow ── {"latest": float, "avg_6h": float,
                        "momentum": float, "buy_vol_6h": float, "sell_vol_6h": float}
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

        # 流量比分级
        if   r > 1.3: base_n =  1.0
        elif r > 1.1: base_n =  0.5
        elif r > 0.9: base_n =  0.0
        elif r > 0.7: base_n = -0.5
        else:         base_n = -1.0

        # 动量加成（最多 ±0.3）
        mom_boost = self.clamp(m * 1.5, -0.3, 0.3)
        if m >  0.15: mom_boost = min( 0.3, mom_boost + 0.2)
        if m < -0.15: mom_boost = max(-0.3, mom_boost - 0.2)

        return self.clamp(base_n + mom_boost)


class LiquidationFactor(BaseFactor):
    """爆仓方向压力因子。

    空头大量被爆 → 看多（空方清洗完毕）
    多头大量被爆 → 看空

    data 键：
        liq_pressure ── {"long_liq": float, "short_liq": float,
                          "total": float, "short_long_ratio": float}
    """

    name   = "liquidation"
    weight = 3.0

    # 最小清算规模门槛（USD），低于此值信号不可靠
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


class LongShortRatioFactor(BaseFactor):
    """多空账户比因子（Long/Short Ratio，类 PCR）。

    多头账户占比高 → 市场过热 → 轻微看空（逆向指标）
    空头账户占比高 → 悲观情绪 → 轻微看多

    data 键：
        ls_ratio ── {"current": float, "trend": float}
    """

    name   = "ls_ratio"
    weight = 0.0  # 默认 0，通过 WeightManager 覆盖

    def compute(self, data: dict[str, Any]) -> float:
        ls = data.get("ls_ratio")
        if not ls:
            return 0.0
        ls_val   = ls["current"] if isinstance(ls, dict) else float(ls)
        ls_trend = ls.get("trend", 0.0) if isinstance(ls, dict) else 0.0
        # current 接近 1.0 为中性；>1 = 多头偏多；<1 = 空头偏多
        ls_n       = self.clamp((ls_val - 1.0) * 2)
        trend_boost = self.clamp(ls_trend * 5, -0.2, 0.2)
        return self.clamp(ls_n + trend_boost)
