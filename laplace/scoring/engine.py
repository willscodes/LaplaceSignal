"""
laplace/scoring/engine.py
评分引擎 —— 归一化 + 加权求和，输出综合信号评分。

流程：
    1. 对每个已注册的 BaseFactor 调用 score()，得到 [-1, +1]
    2. 乘以对应权重
    3. 加权求和得到 total_score（理论范围 [-100, +100]）
    4. 依据 total_score 和市场状态做最终决策

决策阈值说明：
    - TRENDING:       |score| > threshold
    - RANGING:        |score| > threshold × 1.35，同时 RSI 确认
    - TRANSITIONING:  |score| > threshold × 1.50
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from laplace.factors.base import BaseFactor
from .weights import WeightManager, DEFAULT_WEIGHTS


# ================================================================
# 评分结果数据类
# ================================================================

@dataclass
class ScoreResult:
    """单次评分的完整结果。"""

    total:        float                    # 综合得分 [-100, +100]
    scores:       dict[str, float]         # 各因子得分（已乘权重）
    raw_scores:   dict[str, float]         # 各因子原始归一化值 [-1, +1]
    market_state: str  = "TRENDING"        # 市场状态
    decision:     str  = "NO_TRADE"        # LONG / SHORT / NO_TRADE
    reason:       str  = ""                # 决策原因说明
    confidence:   float = 0.0             # 置信度（总分绝对值，供参考）
    weights_used: dict[str, float] = field(default_factory=dict)


# ================================================================
# 评分引擎
# ================================================================

class ScoringEngine:
    """多因子加权评分引擎。

    用法：
        engine = ScoringEngine()
        result = engine.run(data, market_state="TRENDING")
        print(result.decision, result.total)
    """

    def __init__(
        self,
        factors: list[BaseFactor] | None = None,
        weight_manager: WeightManager | None = None,
        decision_threshold: float = 15.0,
    ) -> None:
        """
        Args:
            factors:            因子列表；为 None 时使用内置默认因子集。
            weight_manager:     权重管理器；为 None 时自动创建。
            decision_threshold: 触发交易信号的最低 |total_score|。
        """
        self.weight_manager   = weight_manager or WeightManager()
        self.decision_threshold = decision_threshold

        if factors is None:
            self.factors = self._default_factors()
        else:
            self.factors = factors

    # ── 默认因子集 ─────────────────────────────────────────────────

    @staticmethod
    def _default_factors() -> list[BaseFactor]:
        """返回内置的全量因子列表。"""
        from laplace.factors import (
            TrendFactor, RSIFactor, MACDFactor, BollingerFactor, VolumeFactor,
            FundingRateFactor, OIVelocityFactor, TakerFlowFactor,
            LiquidationFactor, FearGreedFactor, NewsSentimentFactor,
            OnchainPlaceholderFactor,
        )
        return [
            TrendFactor(),
            RSIFactor(),
            MACDFactor(),
            BollingerFactor(),
            VolumeFactor(),
            FundingRateFactor(),
            OIVelocityFactor(),
            TakerFlowFactor(),
            LiquidationFactor(),
            FearGreedFactor(),
            NewsSentimentFactor(),
            OnchainPlaceholderFactor(),
        ]

    # ── 核心计算 ───────────────────────────────────────────────────

    def run(
        self,
        data: dict[str, Any],
        market_state: str = "TRENDING",
    ) -> ScoreResult:
        """执行一轮完整评分。

        Args:
            data:         包含所有市场数据的字典，传递给各因子的 compute()。
            market_state: "TRENDING" | "RANGING" | "TRANSITIONING"

        Returns:
            ScoreResult 实例。
        """
        weights     = self.weight_manager.weights
        data["market_state"] = market_state  # 注入市场状态

        scores:     dict[str, float] = {}
        raw_scores: dict[str, float] = {}

        for factor in self.factors:
            # 从 weight_manager 获取最新权重（覆盖因子默认值）
            w = weights.get(factor.name, factor.weight)
            raw = factor.score(data)         # [-1, +1]
            raw_scores[factor.name] = raw
            scores[factor.name] = round(raw * w, 3)

        total = round(sum(scores.values()), 3)

        # 注入 trend_dir 供 VolumeFactor / OIVelocityFactor 使用
        # （在计算完 TrendFactor 之后追加）
        trend_raw = raw_scores.get("trend", 0.0)
        data["trend_dir"] = 1 if trend_raw >= 0 else -1

        decision, reason = self._decide(
            total, market_state,
            rsi_1h=data.get("m1h", {}).get("rsi", 50),
            rsi_4h=data.get("m4h", {}).get("rsi", 50),
            vol_ratio=data.get("m1h", {}).get("vol_ratio", 1.0),
        )

        return ScoreResult(
            total=total,
            scores=scores,
            raw_scores=raw_scores,
            market_state=market_state,
            decision=decision,
            reason=reason,
            confidence=abs(total),
            weights_used=weights,
        )

    # ── 决策逻辑 ───────────────────────────────────────────────────

    def _decide(
        self,
        total: float,
        market_state: str,
        rsi_1h: float = 50.0,
        rsi_4h: float = 50.0,
        vol_ratio: float = 1.0,
        vol_filter: float = 0.40,
    ) -> tuple[str, str]:
        """根据评分和市场状态输出交易决策。

        Returns:
            (decision, reason) —— decision ∈ {"LONG", "SHORT", "NO_TRADE"}
        """
        thr = self.decision_threshold

        if vol_ratio < vol_filter:
            return "NO_TRADE", f"成交量不足 ({vol_ratio:.2f}x < {vol_filter})"

        if market_state == "TRENDING":
            if total >  thr: return "LONG",     "trend+score"
            if total < -thr: return "SHORT",    "trend+score"
            return "NO_TRADE", f"评分不足 ({total:+.1f})"

        elif market_state == "RANGING":
            strict = thr * 1.35
            if total >  strict and rsi_1h < 38 and rsi_4h < 42:
                return "LONG",  "ranging_oversold"
            if total < -strict and rsi_1h > 62 and rsi_4h > 58:
                return "SHORT", "ranging_overbought"
            return "NO_TRADE", f"震荡市条件不满足 (score={total:+.1f})"

        else:  # TRANSITIONING
            strict = thr * 1.50
            if total >  strict: return "LONG",  "transitioning_high_conf"
            if total < -strict: return "SHORT", "transitioning_high_conf"
            return "NO_TRADE", f"过渡市保守 (score={total:+.1f})"

    # ── 市场状态分类 ───────────────────────────────────────────────

    @staticmethod
    def classify_market(
        adx_1h: float,
        adx_4h: float,
        trend_threshold: float = 25.0,
        range_threshold: float = 20.0,
    ) -> str:
        """根据 ADX 判断市场状态。"""
        adx_avg = adx_1h * 0.4 + adx_4h * 0.6
        if   adx_avg > trend_threshold: return "TRENDING"
        elif adx_avg < range_threshold: return "RANGING"
        else:                            return "TRANSITIONING"
