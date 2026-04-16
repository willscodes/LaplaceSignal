#!/usr/bin/env python3
"""
main.py
LaplaceSignal 信号主循环 —— 每 15 分钟运行一轮评分。

运行方式：
    python main.py

环境变量：
    参考 .env.example，复制为 .env 并填入真实密钥。

流程（每个循环周期）：
    1. 从 OKX 拉取 K线 / 衍生品 / 订单簿数据
    2. 计算技术指标（Trend / RSI / MACD / Bollinger / Volume / ADX）
    3. 拉取情绪数据（Fear & Greed / Tavily 新闻）
    4. 判断市场状态（TRENDING / RANGING / TRANSITIONING）
    5. 多因子加权评分
    6. 决策（LONG / SHORT / NO_TRADE）
    7. 记录信号到 signals/history.json
    8. 权重进化（≥10 笔已结算后触发）
    9. 等待下一个周期
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from laplace.config import config
from laplace.factors import (
    calc_rsi, calc_macd, calc_bb, calc_atr, calc_adx, calc_trend,
)
from laplace.scoring import ScoringEngine, WeightManager
from laplace.utils   import okx_pub

# ================================================================
# 配置
# ================================================================
LOOP_INTERVAL_SEC = 15 * 60   # 15 分钟
INST_ID           = "BTC-USDT-SWAP"
SIGNALS_FILE      = config.SIGNALS_DIR / "history.json"


# ================================================================
# 数据拉取
# ================================================================

def get_klines(bar: str = "1H", limit: int = 150) -> list[dict]:
    """拉取 OKX K线并转换为标准格式。"""
    resp = okx_pub(
        f"/api/v5/market/candles?instId={INST_ID}&bar={bar}&limit={limit}"
    )
    rows = resp.get("data", [])
    candles = [
        {
            "ts":     int(d[0]),
            "open":   float(d[1]),
            "high":   float(d[2]),
            "low":    float(d[3]),
            "close":  float(d[4]),
            "volume": float(d[5]),
        }
        for d in rows
    ]
    return list(reversed(candles))  # 时间升序


def get_orderbook() -> dict | None:
    """拉取订单簿并计算买卖压力。"""
    try:
        d   = okx_pub(f"/api/v5/market/books?instId={INST_ID}&sz=20")["data"][0]
        bv  = sum(float(x[1]) for x in d["bids"])
        av  = sum(float(x[1]) for x in d["asks"])
        r   = bv / (av or 1e-9)
        return {
            "bid_vol":  round(bv, 2),
            "ask_vol":  round(av, 2),
            "ratio":    round(r, 3),
            "pressure": "buy_heavy" if r > 1.3 else "sell_heavy" if r < 0.77 else "balanced",
        }
    except Exception:
        return None


def get_funding() -> dict:
    """拉取当前资金费率。"""
    try:
        d = okx_pub(f"/api/v5/public/funding-rate?instId={INST_ID}")["data"][0]
        return {
            "current": float(d["fundingRate"]),
            "next":    float(d.get("nextFundingRate", d["fundingRate"])),
        }
    except Exception:
        return {"current": 0.0, "next": 0.0}


def get_taker_flow() -> dict | None:
    """拉取 Taker 买卖流量比（近 6H）。"""
    try:
        d = okx_pub("/api/v5/rubik/stat/taker-volume?ccy=BTC&instType=CONTRACTS&period=1H")["data"]
        if not d:
            return None
        ratios, buy_vols, sell_vols = [], [], []
        for row in d[:6]:
            buy, sell = float(row[1]), float(row[2])
            buy_vols.append(buy); sell_vols.append(sell)
            if sell > 0:
                ratios.append(buy / sell)
        if not ratios:
            return None
        latest  = ratios[0]
        avg_6h  = sum(ratios) / len(ratios)
        momentum = (latest - avg_6h) / (avg_6h or 1)
        return {
            "latest":      round(latest, 3),
            "avg_6h":      round(avg_6h, 3),
            "momentum":    round(momentum, 3),
            "buy_vol_6h":  round(sum(buy_vols)),
            "sell_vol_6h": round(sum(sell_vols)),
        }
    except Exception:
        return None


def get_liquidation_pressure() -> dict | None:
    """拉取近期爆仓方向压力。"""
    try:
        d = okx_pub(
            "/api/v5/public/liquidation-orders"
            "?instType=SWAP&instFamily=BTC-USDT&state=filled&limit=100"
        )["data"]
        if not d:
            return None
        long_liq = short_liq = 0.0
        for item in d:
            for det in item.get("details", []):
                sz   = float(det.get("sz", 0))
                px   = float(det.get("bkPx", 0))
                usdt = sz * px / 100
                if det.get("side") == "sell":
                    long_liq  += usdt
                else:
                    short_liq += usdt
        total = long_liq + short_liq
        if total < 1:
            return None
        return {
            "long_liq":         round(long_liq),
            "short_liq":        round(short_liq),
            "total":            round(total),
            "short_long_ratio": round(short_liq / (long_liq or 1), 2),
        }
    except Exception:
        return None


def get_oi_velocity() -> dict | None:
    """拉取 OI 增速。"""
    try:
        d = okx_pub(
            "/api/v5/rubik/stat/contracts/open-interest-volume?ccy=BTC&period=1H"
        )["data"]
        if len(d) < 4:
            return None
        ois   = [float(row[1]) for row in d[:6]]
        c1    = (ois[0] - ois[1]) / (ois[1] or 1) * 100
        c3    = (ois[0] - ois[3]) / (ois[3] or 1) * 100
        diffs = [ois[i] - ois[i + 1] for i in range(3)]
        consistent = all(v > 0 for v in diffs) or all(v < 0 for v in diffs)
        return {
            "chg_1h_pct":           round(c1, 3),
            "chg_3h_pct":           round(c3, 3),
            "latest_oi":            round(ois[0]),
            "direction_consistent": consistent,
        }
    except Exception:
        return None


def get_ls_ratio() -> dict | None:
    """拉取多空账户比。"""
    try:
        d = okx_pub(
            "/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy=BTC&period=1H"
        )["data"]
        if not d:
            return None
        current = float(d[0][1])
        refs    = [float(x[1]) for x in d[:6]]
        avg6h   = sum(refs) / len(refs)
        return {"current": round(current, 4), "trend": round(current - avg6h, 4)}
    except Exception:
        return None


# ================================================================
# 分析工具
# ================================================================

def analyze(klines: list[dict], tf: str) -> dict:
    """对 K 线执行全量技术指标计算。"""
    closes    = [k["close"] for k in klines]
    vol_avg   = sum(k["volume"] for k in klines[-20:]) / 20 or 1
    return {
        "tf":        tf,
        "price":     closes[-1],
        "rsi":       calc_rsi(closes),
        "macd":      calc_macd(closes),
        "bb":        calc_bb(closes),
        "atr":       calc_atr(klines),
        "trend":     calc_trend(closes),
        "adx":       calc_adx(klines),
        "vol_ratio": klines[-1]["volume"] / vol_avg,
    }


# ================================================================
# 信号持久化
# ================================================================

def load_signals() -> list[dict]:
    if SIGNALS_FILE.exists():
        try:
            return json.loads(SIGNALS_FILE.read_text())
        except Exception:
            pass
    return []


def save_signal(record: dict) -> None:
    """追加一条信号到历史文件。"""
    config.SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    history = load_signals()
    history.append(record)
    SIGNALS_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False)
    )


# ================================================================
# 主循环
# ================================================================

def run_once(engine: ScoringEngine) -> None:
    """执行一轮信号计算。"""
    now = datetime.now(timezone.utc)
    print("=" * 65)
    print(f"  LaplaceSignal — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 65)

    # ── 1. 拉取 K 线 ──────────────────────────────────────────────
    print("\n[1/5] 拉取市场数据...")
    k1h = get_klines("1H", 150)
    k4h = get_klines("4H", 100)
    k1d = get_klines("1Dutc", 60)
    if not k1h:
        print("  ERROR: K线获取失败，跳过本轮")
        return

    price = k1h[-1]["close"]
    m1h   = analyze(k1h, "1H")
    m4h   = analyze(k4h, "4H")
    m1d   = analyze(k1d, "1D")
    ob    = get_orderbook()
    print(f"  BTC: ${price:,.1f}  |  ADX 1H={m1h['adx']:.1f}  4H={m4h['adx']:.1f}")

    # ── 2. 市场状态分类 ────────────────────────────────────────────
    market_state = ScoringEngine.classify_market(m1h["adx"], m4h["adx"])
    print(f"\n[2/5] 市场状态: {market_state}")

    # ── 3. 衍生品 / 情绪数据 ──────────────────────────────────────
    print("\n[3/5] 拉取衍生品 & 情绪数据...")
    funding      = get_funding()
    taker_flow   = get_taker_flow()
    liq_pressure = get_liquidation_pressure()
    oi_velocity  = get_oi_velocity()
    ls_ratio     = get_ls_ratio()
    print(f"  FR={funding['current']*100:.4f}%  "
          f"TakerRatio={taker_flow['latest'] if taker_flow else 'N/A'}  "
          f"L/S={ls_ratio['current'] if ls_ratio else 'N/A'}")

    # ── 4. 评分 ────────────────────────────────────────────────────
    print("\n[4/5] 多因子评分...")
    data = {
        "m1h":         m1h,
        "m4h":         m4h,
        "m1d":         m1d,
        "orderbook":   ob,
        "funding":     funding,
        "taker_flow":  taker_flow,
        "liq_pressure": liq_pressure,
        "oi_velocity": oi_velocity,
        "ls_ratio":    ls_ratio,
    }
    result = engine.run(data, market_state=market_state)
    print(f"  总分: {result.total:+.2f}  →  决策: {result.decision}  ({result.reason})")

    # 打印各因子得分
    print("  因子得分：")
    for k, v in sorted(result.scores.items(), key=lambda x: abs(x[1]), reverse=True):
        bar = "█" * int(abs(v) / 2) if abs(v) > 0 else "·"
        sign = "+" if v >= 0 else ""
        print(f"    {k:<16} {sign}{v:6.2f}  {bar}")

    # ── 5. 记录信号 ────────────────────────────────────────────────
    print("\n[5/5] 记录信号...")
    signal_record = {
        "ts":           now.isoformat(),
        "price":        price,
        "market_state": market_state,
        "decision":     result.decision,
        "reason":       result.reason,
        "total_score":  result.total,
        "scores":       result.scores,
        "outcome":      "pending",
    }
    save_signal(signal_record)
    print(f"  已保存到 {SIGNALS_FILE}")


def main() -> None:
    """启动主循环，每 15 分钟执行一轮。"""
    print("LaplaceSignal 启动")
    print(f"  模式:   {config.RUN_MODE}")
    print(f"  间隔:   {LOOP_INTERVAL_SEC // 60} 分钟")
    print(f"  信号目录: {config.SIGNALS_DIR}\n")

    engine = ScoringEngine()

    while True:
        try:
            run_once(engine)
        except KeyboardInterrupt:
            print("\n用户中断，退出。")
            break
        except Exception as exc:
            print(f"\n[ERROR] 本轮异常: {exc}")

        print(f"\n等待 {LOOP_INTERVAL_SEC // 60} 分钟...\n")
        try:
            time.sleep(LOOP_INTERVAL_SEC)
        except KeyboardInterrupt:
            print("\n用户中断，退出。")
            break


if __name__ == "__main__":
    main()
