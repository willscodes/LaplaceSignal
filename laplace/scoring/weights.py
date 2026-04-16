"""
laplace/scoring/weights.py
权重管理模块 —— 加载 / 保存 / 进化因子权重。

权重进化逻辑（≥10 笔已结算信号后触发）：
    - 若某因子方向预测准确率 > 60%  → 权重 × 1.08（上限 40）
    - 若某因子方向预测准确率 < 40%  → 权重 × 0.92（下限 2）
    - 调整后所有权重归一化到总和 = 100
"""

import json
import os
from pathlib import Path
from typing import Any

from laplace.config import config


# ================================================================
# 默认权重（10 维度，总和 = 100）
# ================================================================
DEFAULT_WEIGHTS: dict[str, float] = {
    "trend":       25.0,
    "rsi":         14.0,
    "macd":        14.0,
    "bollinger":   10.0,
    "news":        10.0,
    "onchain":      8.0,
    "taker_flow":   8.0,
    "volume":       6.0,
    "funding":      5.0,
    "fear_greed":   5.0,
    "liquidation":  3.0,
    "oi_velocity":  2.0,
}

# 权重文件路径
_WEIGHTS_FILE: Path = config.SIGNALS_DIR / "weights.json"


# ================================================================
# 加载 / 保存
# ================================================================

def load_weights() -> dict[str, float]:
    """从文件加载权重；若文件不存在则返回默认权重。

    - 自动补全文件中缺少的新维度（使用默认值）。
    - 文件损坏时静默回退到默认值。
    """
    w = DEFAULT_WEIGHTS.copy()
    if _WEIGHTS_FILE.exists():
        try:
            stored: dict = json.loads(_WEIGHTS_FILE.read_text())
            w.update(stored)
            # 补全文件中缺失的新因子
            for k, v in DEFAULT_WEIGHTS.items():
                if k not in w:
                    w[k] = v
        except Exception as e:
            print(f"[WeightManager] 权重文件读取失败，使用默认值: {e}")
    return w


def save_weights(w: dict[str, float]) -> None:
    """将权重保存到 signals/weights.json。"""
    _WEIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _WEIGHTS_FILE.write_text(json.dumps(w, indent=2, ensure_ascii=False))


# ================================================================
# 权重进化
# ================================================================

def evolve_weights(
    weights: dict[str, float],
    signals: list[dict[str, Any]],
    *,
    min_settled: int = 10,
    up_acc: float = 0.60,
    dn_acc: float = 0.40,
    up_factor: float = 1.08,
    dn_factor: float = 0.92,
    max_weight: float = 40.0,
    min_weight: float = 2.0,
) -> dict[str, float]:
    """基于历史信号结果进化因子权重。

    Args:
        weights:     当前权重字典。
        signals:     信号历史列表（每条含 outcome / decision / scores）。
        min_settled: 触发进化所需的最少已结算笔数。
        up_acc:      准确率超过此值 → 权重上调。
        dn_acc:      准确率低于此值 → 权重下调。
        up_factor:   上调乘数。
        dn_factor:   下调乘数。
        max_weight:  单因子权重上限。
        min_weight:  单因子权重下限。

    Returns:
        新的权重字典（已归一化，总和 = 100）。
    """
    settled = [s for s in signals if s.get("outcome") in ("win", "loss")]
    if len(settled) < min_settled:
        print(f"  [进化] 已结算 {len(settled)}/{min_settled} 笔，暂不调整")
        return weights

    correct:  dict[str, int] = {k: 0 for k in weights}
    total_k:  dict[str, int] = {k: 0 for k in weights}

    for s in settled:
        won     = s["outcome"] == "win"
        is_long = s["decision"] == "LONG"
        for k, v in s.get("scores", {}).items():
            if k not in weights:
                continue
            total_k[k] += 1
            # 因子方向与结果一致 → 预测正确
            if (
                (v > 0 and is_long  and won) or
                (v < 0 and not is_long and won) or
                (v > 0 and not is_long and not won) or
                (v < 0 and is_long  and not won)
            ):
                correct[k] += 1

    new_w   = dict(weights)
    changed = []
    for k in weights:
        n = total_k.get(k, 0)
        if not n:
            continue
        acc = correct[k] / n
        if acc > up_acc:
            new_w[k] = min(max_weight, weights[k] * up_factor)
            changed.append(
                f"  ↑ {k}: {weights[k]:.1f} → {new_w[k]:.1f}  (acc={acc:.0%})"
            )
        elif acc < dn_acc:
            new_w[k] = max(min_weight, weights[k] * dn_factor)
            changed.append(
                f"  ↓ {k}: {weights[k]:.1f} → {new_w[k]:.1f}  (acc={acc:.0%})"
            )

    # 归一化到总和 100
    total = sum(new_w.values())
    new_w = {k: round(v / total * 100, 2) for k, v in new_w.items()}

    if changed:
        print("[权重进化]")
        for line in changed:
            print(line)
    else:
        print("  [进化] 权重无需调整")

    return new_w


# ================================================================
# 便捷类封装
# ================================================================

class WeightManager:
    """权重管理器，封装加载 / 保存 / 进化操作。

    用法：
        wm = WeightManager()
        w  = wm.weights          # 获取当前权重
        wm.evolve(signals)       # 基于信号历史进化并自动保存
    """

    def __init__(self) -> None:
        self._weights = load_weights()

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

    def save(self) -> None:
        save_weights(self._weights)

    def evolve(self, signals: list[dict[str, Any]]) -> dict[str, float]:
        """进化权重并保存到文件。"""
        self._weights = evolve_weights(self._weights, signals)
        self.save()
        return self.weights

    def reset(self) -> None:
        """重置为默认权重。"""
        self._weights = DEFAULT_WEIGHTS.copy()
        self.save()

    def __repr__(self) -> str:
        return f"WeightManager(factors={list(self._weights.keys())})"
