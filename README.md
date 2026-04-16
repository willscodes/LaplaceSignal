# LaplaceSignal

> **"Give me the present state of the universe, and I shall predict the future."**
> — Pierre-Simon Laplace, 1814

A self-evolving, multi-dimensional BTC/crypto signal engine. The name carries a dual meaning:

- **Laplace's Demon** — the thought experiment that a sufficiently informed intellect could determine the entire future from the present state. LaplaceSignal aspires to that completeness: ingesting every quantifiable edge (price, derivatives flow, options sentiment, on-chain data, macro news) to collapse uncertainty into a single actionable score.
- **Laplace Transform** — the mathematical operation that converts a time-domain signal into its frequency-domain representation, revealing hidden structure. The engine similarly transforms noisy, multi-timescale market data into a clean, normalized signal.

---

## Architecture

```
LaplaceSignal/
├── laplace/
│   ├── config.py                  # .env-backed configuration singleton
│   ├── factors/
│   │   ├── base.py                # BaseFactor ABC  (compute → [-1, +1])
│   │   ├── technical.py           # Level-1 price factors
│   │   │   ├── TrendFactor        # EMA-20/50 trend classification
│   │   │   ├── RSIFactor          # RSI-14 with regime-aware scoring
│   │   │   ├── MACDFactor         # MACD crossover + histogram boost
│   │   │   ├── BollingerFactor    # %B positioning (trend vs. range mode)
│   │   │   └── VolumeFactor       # Volume ratio + order book pressure
│   │   ├── derivatives.py         # Level-1/2 derivatives factors
│   │   │   ├── FundingRateFactor      # Spot funding rate bias
│   │   │   ├── FundingRateEMAFactor   # EMA-8/24 funding trend (Level-2)
│   │   │   ├── OIVelocityFactor       # Open interest velocity (1H/3H)
│   │   │   ├── TakerFlowFactor        # Taker buy/sell ratio (6H)
│   │   │   ├── LiquidationFactor      # Liquidation direction pressure
│   │   │   ├── LongShortRatioFactor   # L/S account ratio (contrarian)
│   │   │   └── PCRFactor              # Deribit Put/Call Ratio (Level-2)
│   │   ├── sentiment.py           # Level-3 sentiment factors
│   │   │   ├── FearGreedFactor    # Alternative.me Fear & Greed Index
│   │   │   └── NewsSentimentFactor# Tavily-powered news NLP scoring
│   │   └── onchain.py             # Level-3 on-chain placeholder
│   ├── scoring/
│   │   ├── engine.py              # Multi-timeframe scoring orchestrator
│   │   └── weights.py             # WeightManager + evolve_weights()
│   ├── utils/
│   │   └── okx_client.py          # OKX REST + authenticated client
│   └── execution/
│       └── okx.py                 # Order placement (paper / live modes)
├── main.py                        # Entry point — run signal cycle
├── signals/                       # Runtime output (weights.json, history.json)
├── .env.example                   # Environment variable template
├── requirements.txt
└── README.md
```

---

## Factor System

LaplaceSignal organizes its 12 factor dimensions into three layers:

### Level 1 — Price & Derivatives (real-time OKX data)

| Factor | Key | Default Weight | Description |
|--------|-----|---------------|-------------|
| Trend | `trend` | 25.0 | EMA-20/50 cross across 1H / 4H / 1D timeframes |
| RSI | `rsi` | 14.0 | RSI-14; regime-aware (trending vs. ranging scoring) |
| MACD | `macd` | 14.0 | Crossover classification + histogram momentum boost |
| Bollinger | `bollinger` | 10.0 | %B band position; breakout vs. mean-reversion mode |
| Volume | `volume` | 6.0 | Volume ratio (vs. 20-bar avg) + order book pressure |
| Taker Flow | `taker_flow` | 8.0 | Active buy/sell ratio with 6H momentum |
| OI Velocity | `oi_velocity` | 2.0 | Open interest 1H/3H change % with direction consistency |
| Liquidation | `liquidation` | 3.0 | Short/Long liquidation ratio (≥ $50K threshold) |
| Funding Rate | `funding` | 5.0 | Spot funding rate bias (positive = bearish) |

### Level 2 — Derivatives Intelligence (EMA & options)

| Factor | Key | Default Weight | Description |
|--------|-----|---------------|-------------|
| Funding EMA | `funding_ema` | 5.0 | EMA-8 vs EMA-24 over last 24 funding periods (OKX history) |
| PCR | `pcr` | 4.0 | Deribit BTC Put/Call Ratio — contrarian options sentiment |

### Level 3 — Macro & Sentiment

| Factor | Key | Default Weight | Description |
|--------|-----|---------------|-------------|
| Fear & Greed | `fear_greed` | 5.0 | Alternative.me index (current vs. 7-day trend) |
| News | `news` | 10.0 | Tavily NLP: bull/bear keyword ratio across recent headlines |
| On-Chain | `onchain` | 8.0 | Composite: Fear/Greed + funding rate + L/S ratio blend |

> **Total default weight sum = 109** (intentional — WeightManager normalizes to 100 after each evolution cycle).

---

## Market Regime Detection

Before scoring, the engine classifies the current market state using ADX (1H + 4H):

| State | ADX Threshold | Strategy |
|-------|--------------|----------|
| `TRENDING` | > 25 | Trend-following; standard signal thresholds |
| `RANGING` | < 20 | Mean reversion; strict RSI gates required |
| `TRANSITIONING` | 20–25 | Conservative; 1.5× threshold multiplier |

---

## Weight Self-Evolution

Weights adapt automatically after every 10 settled signals:

```
for each factor dimension k:
    accuracy = correct_predictions[k] / total_predictions[k]

    if accuracy > 60%:  weight[k] *= 1.08   (cap: 40.0)
    if accuracy < 40%:  weight[k] *= 0.92   (floor: 2.0)

normalize all weights → sum = 100
save to signals/weights.json
```

A "correct prediction" means the factor's signed contribution agreed with the actual trade outcome (win LONG with positive score, win SHORT with negative score, etc.). This closed-loop mechanism lets the engine discover which factors are genuinely predictive in current market conditions and down-weight noise.

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/willscodes/LaplaceSignal.git
cd LaplaceSignal
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
# OKX API (required for live data + execution)
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_API_PASSPHRASE=your_passphrase

# Tavily (required for news sentiment)
TAVILY_KEY=your_tavily_key

# Telegram notifications (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# "paper" = signal-only mode; "live" = real order execution
RUN_MODE=paper
```

### 3. Run

```bash
# Single signal cycle
python main.py

# Scheduled (every 4 hours via cron)
0 */4 * * * cd /path/to/LaplaceSignal && python main.py
```

### 4. Output

Signal history and evolved weights are stored in `signals/`:

```
signals/
├── history.json   # Timestamped signal records with scores, outcome
└── weights.json   # Current evolved factor weights
```

---

## Factor API

All factors share the same interface:

```python
from laplace.factors import FundingRateEMAFactor, PCRFactor

factor = FundingRateEMAFactor()

data = {
    "funding_ema": {
        "ema8":    0.00012,
        "ema24":   0.00015,
        "current": 0.00010,
        "signal":  "bearish",
    }
}

score = factor.score(data)          # float in [-1.0, +1.0]
weighted = factor.weighted_score(data)  # score × factor.weight
```

Each `compute()` method returns a raw float; `score()` auto-clamps to `[-1, +1]`.

---

## Requirements

- Python ≥ 3.11
- `requests`, `python-dotenv`, `tavily-python`, `pandas`, `numpy`
- OKX API credentials (public endpoints work without auth for read-only data)
- Tavily API key for news sentiment

---

## License

MIT © 2024 LaplaceSignal Contributors

---

*"Probability is nothing but common sense reduced to calculation."*
— Pierre-Simon Laplace
