"""
laplace/factors/sentiment.py
情绪因子模块。

包含：
    - FearGreedFactor    ── Alternative.me 恐慌与贪婪指数
    - NewsSentimentFactor ── Tavily 新闻搜索情绪分析
"""

import json
import urllib.request
from typing import Any

from .base import BaseFactor


class FearGreedFactor(BaseFactor):
    """恐慌与贪婪指数因子（Alternative.me）。

    0   = Extreme Fear  → 看多（逆向）
    100 = Extreme Greed → 看空（逆向）
    50  = Neutral       → 0

    data 键：
        fear_greed ── {"value": int, "label": str, "trend": int}
                      或 None（将自动拉取）
    """

    name   = "fear_greed"
    weight = 5.0

    _API_URL = "https://api.alternative.me/fng/?limit=7"

    @staticmethod
    def fetch() -> dict:
        """从 API 拉取最新恐慌与贪婪数据。"""
        try:
            req = urllib.request.Request(
                FearGreedFactor._API_URL,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            now  = int(data["data"][0]["value"])
            week = int(data["data"][6]["value"])
            return {
                "value": now,
                "label": data["data"][0]["value_classification"],
                "trend": now - week,
            }
        except Exception:
            return {"value": 50, "label": "Unknown", "trend": 0}

    def compute(self, data: dict[str, Any]) -> float:
        fg = data.get("fear_greed") or self.fetch()
        # (value - 50) / 50 → [-1, +1]
        # 高贪婪 → 看多，但同时也是反转信号
        # 此处采用顺势解读：高贪婪 = 看多，低恐慌 = 看空
        return self.clamp((fg["value"] - 50) / 50.0)


class NewsSentimentFactor(BaseFactor):
    """新闻情绪因子（Tavily 搜索 API）。

    根据关键词计数粗估新闻看多 / 看空倾向。

    data 键：
        news_sentiment ── {"score": int, "label": str, ...}
                          或 None（将自动拉取，需要 TAVILY_KEY）
        tavily_key     ── Tavily API Key（可选覆盖 config）
    """

    name   = "news"
    weight = 10.0

    _BULL_WORDS = [
        "surge", "rally", "bull", "gain", "rise", "buy", "growth",
        "breakout", "soar", "adoption", "inflow", "rebound", "recovery",
        "upside", "bullish", "strong", "hodl", "etf", "approval",
    ]
    _BEAR_WORDS = [
        "crash", "bear", "drop", "fall", "sell", "loss", "fear", "dump",
        "hack", "ban", "regulation", "outflow", "liquidat", "panic",
        "bearish", "weak", "correction", "warning", "decline",
    ]

    def fetch(self, api_key: str) -> dict:
        """从 Tavily API 拉取并分析新闻情绪。"""
        try:
            payload = json.dumps({
                "api_key":       api_key,
                "query":         "Bitcoin BTC market sentiment price today 2026",
                "search_depth":  "basic",
                "max_results":   8,
                "include_answer": True,
                "days":          2,
            }).encode()
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent":   "Mozilla/5.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                resp = json.loads(r.read())
            text = (
                resp.get("answer", "") + " " +
                " ".join(
                    x.get("title", "") + " " + x.get("content", "")[:150]
                    for x in resp.get("results", [])
                )
            ).lower()
            bc = sum(text.count(w) for w in self._BULL_WORDS)
            br = sum(text.count(w) for w in self._BEAR_WORDS)
            score = round(bc / (bc + br or 1) * 100)
            if   score >= 75: label = "Extreme Bullish"
            elif score >= 58: label = "Bullish"
            elif score >= 42: label = "Neutral"
            elif score >= 25: label = "Bearish"
            else:             label = "Extreme Bearish"
            return {
                "score":     score,
                "label":     label,
                "headlines": [x.get("title", "") for x in resp.get("results", [])[:3]],
                "bull":      bc,
                "bear":      br,
            }
        except Exception:
            return {"score": 50, "label": "Unknown", "headlines": [], "bull": 0, "bear": 0}

    def compute(self, data: dict[str, Any]) -> float:
        news = data.get("news_sentiment")
        if not news:
            from laplace.config import config
            api_key = data.get("tavily_key") or config.TAVILY_KEY
            if api_key:
                news = self.fetch(api_key)
            else:
                news = {"score": 50}
        # score: 0~100 → (-1, +1)
        return self.clamp((news["score"] - 50) / 50.0)
