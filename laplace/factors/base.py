"""
laplace/factors/base.py
BaseFactor 抽象基类 —— 所有因子模块必须继承此类。

约定：
    - compute() 返回 float，范围严格限定在 [-1.0, +1.0]
      +1.0 = 极度看多
      -1.0 = 极度看空
       0.0 = 中性/无信号
    - weight 表示该因子在评分引擎中的初始权重（0 ~ 100），
      合计应等于 100（由 WeightManager 负责归一化）。
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseFactor(ABC):
    """所有信号因子的抽象基类。

    子类示例：
        class RSIFactor(BaseFactor):
            name   = "rsi"
            weight = 14.0

            def compute(self, data: dict) -> float:
                rsi = data["rsi_1h"]
                if rsi > 70: return -0.8
                if rsi < 30: return  0.8
                return 0.0
    """

    # ── 子类必须定义这两个类属性 ──────────────────────────────────

    #: 因子唯一标识符（用于权重字典 key 和日志输出）
    name: str = ""

    #: 默认权重（0 ~ 100），所有因子权重之和应等于 100
    weight: float = 0.0

    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    def compute(self, data: dict[str, Any]) -> float:
        """根据输入数据计算因子得分。

        Args:
            data: 包含所需市场数据的字典（K线、衍生品、情绪等）。
                  具体字段由子类文档说明。

        Returns:
            float，严格在 [-1.0, +1.0] 之间。
        """
        ...

    # ── 工具方法 ──────────────────────────────────────────────────

    @staticmethod
    def clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
        """将数值截断到 [lo, hi] 区间，防止越界。"""
        return max(lo, min(hi, value))

    def score(self, data: dict[str, Any]) -> float:
        """调用 compute() 并自动 clamp，对外统一入口。"""
        raw = self.compute(data)
        return self.clamp(raw)

    def weighted_score(self, data: dict[str, Any]) -> float:
        """返回 score × weight（用于加权求和）。"""
        return self.score(data) * self.weight

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, weight={self.weight})"
