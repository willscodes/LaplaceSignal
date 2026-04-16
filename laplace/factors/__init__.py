"""
laplace/factors/__init__.py
导出所有因子类及计算工具函数。
"""

from .base import BaseFactor

# 技术指标因子
from .technical import (
    TrendFactor,
    RSIFactor,
    MACDFactor,
    BollingerFactor,
    VolumeFactor,
    # 纯函数工具（供外部直接调用）
    calc_ema,
    calc_rsi,
    calc_macd,
    calc_bb,
    calc_atr,
    calc_adx,
    calc_trend,
)

# 衍生品因子
from .derivatives import (
    FundingRateFactor,
    OIVelocityFactor,
    TakerFlowFactor,
    LiquidationFactor,
    LongShortRatioFactor,
)

# 情绪因子
from .sentiment import (
    FearGreedFactor,
    NewsSentimentFactor,
)

# 链上因子（占位）
from .onchain import OnchainPlaceholderFactor

__all__ = [
    # 基类
    "BaseFactor",
    # 技术
    "TrendFactor",
    "RSIFactor",
    "MACDFactor",
    "BollingerFactor",
    "VolumeFactor",
    # 衍生品
    "FundingRateFactor",
    "OIVelocityFactor",
    "TakerFlowFactor",
    "LiquidationFactor",
    "LongShortRatioFactor",
    # 情绪
    "FearGreedFactor",
    "NewsSentimentFactor",
    # 链上
    "OnchainPlaceholderFactor",
    # 工具函数
    "calc_ema",
    "calc_rsi",
    "calc_macd",
    "calc_bb",
    "calc_atr",
    "calc_adx",
    "calc_trend",
]
