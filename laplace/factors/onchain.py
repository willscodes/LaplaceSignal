"""
laplace/factors/onchain.py
链上因子模块 —— 占位，待后续扩展。

规划因子（TODO）：
    - ExchangeNetFlowFactor    ── 交易所净流入/流出（Glassnode / CryptoQuant）
    - MinerReserveFactor       ── 矿工持仓变化
    - StablecoinSupplyFactor   ── 稳定币发行量（资金流入预期）
    - STHSOPRFactor            ── 短期持有者 SOPR（盈亏比）
    - NUPLFactor               ── 未实现盈亏比（NUPL）

现阶段对应 CTIS engine 中的 onchain 评分使用
FearGreedFactor + FundingRateFactor + LongShortRatioFactor 复合计算。
"""

from typing import Any

from .base import BaseFactor


class OnchainPlaceholderFactor(BaseFactor):
    """链上综合因子占位符。

    当前实现：永远返回 0.0（中性）。
    待接入 Glassnode / CryptoQuant 等链上数据源后实现。

    data 键：
        onchain ── 链上数据字典（暂未使用）
    """

    name   = "onchain"
    weight = 8.0

    def compute(self, data: dict[str, Any]) -> float:
        # TODO: 接入链上数据源并实现真实计算逻辑
        return 0.0
