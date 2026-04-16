"""
laplace/__init__.py
LaplaceSignal 顶层包。

版本：0.1.0
"""

__version__ = "0.1.0"
__author__  = "LaplaceSignal Team"

# 便捷导入
from laplace.config import config
from laplace.scoring import ScoringEngine, ScoreResult, WeightManager

__all__ = [
    "config",
    "ScoringEngine",
    "ScoreResult",
    "WeightManager",
    "__version__",
]
