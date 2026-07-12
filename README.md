# CryptoTrade

AI-driven crypto futures signal bot. Extracts market features from public perpetual futures data, sends structured context to DeepSeek for analysis, routes validated signals to Telegram.

The bot does not place trades, execute orders, or use private exchange APIs. It is signal-only.

## Architecture

```
Market Data Providers (Gate, OKX, Bybit, MEXC, KuCoin)
         │
         ▼
   ┌─────────┐   ┌──────────────┐   ┌─────────────┐
   │ Scanner │   │ Spike Monitor│   │Zone Monitor  │
   │ (10 min)│   │  (30 sec)    │   │  (60 sec)    │
   └────┬────┘   └──────┬───────┘   └──────┬──────┘
        │               │                  │
        ▼               ▼                  ▼
   ┌─────────────────────────────────────────┐
   │         DeepSeek AI Analysis            │
   │    (System Prompt: 37 trading rules)     │
   └──────────────────┬──────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   ┌─────────┐  ┌──────────┐  ┌───────────┐
   │ Signal  │  │Watchlist │  │  Outcome  │
   │Broadcast│  │  Manager │  │  Tracker  │
   └────┬────┘  └────┬─────┘  └───────────┘
        │            │
        ▼            ▼
   ┌────────────────────┐
   │    Telegram Bot     │
   │  (Admin + Channel)  │
   └────────────────────┘
```

## Features

### Core Signal System
- **AI analysis** via DeepSeek with 37 trading rules (trend, momentum, volume, S/R, orderflow, derivatives, risk-reward, RSI thresholds, zone reaction, false breakout, BTC correlation, session timing, volume accumulation, orderbook context, continuous analyst mindset)
- **Multi-provider** market data (Gate, OKX, Bybit, MEXC, KuCoin) with automatic failover
- **Multi-timeframe**: M15, H1, H4, D1 candles
- **Kline cache** with TTL (15m/1h/4h/24h) reducing API calls 60-70%
- **Volume spike monitor** — polls every 30s, detects volume anomalies, triggers AI analysis
- **Zone proximity monitor** — polls every 60s, detects price entering demand/supply zones, triggers AI analysis
- **Signal validation**: confidence, risk-reward, orderflow conflict, entry/SL/TP completeness
- **Auto-broadcast** valid signals to Telegram channel, warning signals to admin only
- **Batch recap** per 5 signals as backup summary
- **Inline warning badges** on signal headers for quick assessment
- **Signal auto-pinning** to channel, daily unpin at 21:00 WIB

### Live Watchlist System
- **Continuous pair monitoring** across all 3 AI analysis sources
- **Market states**: WATCHING → ACCUMULATING → BREAKOUT_READY → TRENDING with transition rules
- **Probability tracking**: previous/current probability with delta and change reason
- **Opportunity ranking**: composite score (confidence, priority, RR, trigger distance, analysis count)
- **Single Telegram message**, edited in-place (editMessageText), day-separated
- **DB persistence**: `watchlist_items` table with history (analysis_count per pair)
- **Auto-cleanup**: expired, completed, and invalid items removed
- **Commands**: `/watchlist` (refresh), `/watchlist clear` (reset)

### Analysis & Detection
- **Indicators**: EMA, RSI, ATR, volume SMA, OBV, CVD (approximate), volume spike/trend/ratio
- **Market structure**: swing points, BOS/CHoCH, support/resistance, demand/supply zones
- **False breakout scoring** (0-10): volume, RSI, structure, round number, CVD divergence
- **Zone reaction scoring** (0-3): wick detection, engulfing, volume exhaustion at S/D zones
- **BTC correlation guard**: BTC status classification, confidence adjustment, dump alert
- **Session timing filter**: dead zone, Asian, London, NY overlap with confidence adjustments
- **Risk-reward**: structural SL/TP, TP2 probability estimation, ATR-based buffer
- **Volume accumulation**: OBV divergence, CVD divergence, volume compression detection
- **Orderbook context**: depth ratio, bid/ask walls, spread analysis
- **Whale activity tracking**: large trade buy/sell volume and notional

### Learning System
- **Outcome tracking**: TP/SL/expiry detection with candle backfill (OHLCV high/low between polls)
- **Post-trade review**: DeepSeek analyzes completed signals, generates lesson suggestions
- **Strategy lessons**: 7 types (confidence_boost, confidence_penalty, filter_rule, risk_adjustment, prompt_context, warning_note, avoid_condition)
- **Auto-approve** for quality lessons (confidence_boost, confidence_penalty, filter_rule, risk_adjustment)
- **Adaptive scoring**: active lessons adjust candidate confidence pre-broadcast
- **Performance analytics**: winrate, per-symbol, per-regime, per-direction stats
- **Daily signal recap** at 21:00 WIB with full outcome summary

### Telegram Commands

```
/start              Start + auto broadcast enable
/status             Live server state
/cache              Kline cache stats (hit rate, entries, TTL)
/scan_now           Manual market scan
/pairs              Pair list (20/page)
/top_volume         Highest volume pairs (15/page)
/signals            Recent signals (5/page)
/signal_detail ID   Full signal detail
/signal_result ID R Set outcome
/signal_recap       Today signal summary
/pending_signals    Pending outcome signals
/outcomes           Recent resolved outcomes
/performance        Winrate, per-symbol stats (7d/30d/all)
/waiting            Rejected/Warning candidate list
/settings           Config overview
/set_confidence N   Min confidence threshold
/set_rr N.N         Min risk-reward threshold
/set_interval N     Scan interval (minutes)
/broadcast_on       Enable auto channel broadcast
/broadcast_off      Manual approval mode
/last_scan          Last scan result
/diagnose_market    Provider connectivity test
/orderflow SYM      Orderflow summary
/orderflow_top      Top orderflow activity
/nudge ID approve   Manual signal approve
/nudge ID reject    Manual signal reject
/watchlist          Refresh live watchlist
/watchlist clear    Reset watchlist
/approve_all        Auto-approve best 10 lessons
/lessons            Strategy lessons list
/lesson_detail ID   Lesson detail
/approve_lesson ID  Approve lesson
/reject_lesson ID   Reject lesson
/disable_lesson ID  Disable lesson
/review_signal ID   Trigger signal review
/learning_status    Learning loop status
/help               Command list
```

## Project Structure

```
app/
  ai/                 DeepSeek client, prompt builder (37 rules), response parser
  analysis/           Indicators (EMA/RSI/ATR/OBV/CVD), market structure (S/R/zones/BOS),
                        setup detector, risk-reward, volume spike monitor, zone proximity monitor
  watchlist/          Live watchlist manager, models, state machine, Telegram message editing
  database/           SQLAlchemy models (SignalLog, OrderflowSnapshot, WatchlistItem, etc.),
                        session, repository
  learning/           Outcome tracker, post-trade reviewer, performance analyzer,
                        adaptive scoring, lesson manager
  market_data/        Multi-provider REST clients (Gate/OKX/Bybit/MEXC/KuCoin),
                        kline cache, symbol mapper, provider factory
  orderflow/          WebSocket providers (Gate/OKX/Bybit/MEXC), trade flow store,
                        orderflow analyzer, volume delta
  signal/             Signal validation, formatting, broadcasting
  telegram/           Admin bot (send/edit/pin/retry), commands, callbacks,
                        message formatter, webhook manager
  utils/              Logging setup
run.py                FastAPI runner
requirements.txt      Python dependencies
.env.example          Environment template
prompts/              Reference prompt files for AI analysis rules
```

## Environment Configuration

```env
# Core
DEEPSEEK_API_KEY=your_key
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_ADMIN_CHAT_ID=your_admin_id
TELEGRAM_CHANNEL_CHAT_ID=your_channel_id

# Providers
MARKET_PROVIDER=gate
FALLBACK_MARKET_PROVIDER=gate
ALTCOIN_PROVIDER=gate

# Scan
MAX_PAIRS=150
SCAN_INTERVAL_MINUTES=10
MAX_REALTIME_PAIRS=70
MAX_DEPTH_PAIRS=20

# Signal Filters
MIN_CONFIDENCE=50
MIN_RISK_REWARD=1.5
AUTO_BROADCAST=true

# Zone Monitor
ENABLE_ZONE_MONITOR=true
ZONE_MONITOR_INTERVAL_SECONDS=60
ZONE_MONITOR_PAIRS=30
ZONE_APPROACHING_PCT=2.5

# Learning
ENABLE_ORDERFLOW=true
ENABLE_OUTCOME_TRACKING=true
ENABLE_SIGNAL_LEARNING=true
ENABLE_AUTO_REVIEW=true
ENABLE_ADAPTIVE_SCORING=true
REQUIRE_ADMIN_APPROVAL_FOR_LESSONS=false
SIGNAL_MARKET_VALID_MINUTES=30
PERFORMANCE_LOOKBACK_DAYS=30
MAX_ACTIVE_LESSONS_IN_PROMPT=10

# Expiry
SIGNAL_EXPIRY_M15_HOURS=6
SIGNAL_EXPIRY_H1_HOURS=24
SIGNAL_EXPIRY_H4_HOURS=72
```

## Signal Flow

### Main Scanner (10 min)
1. Fetch top 150 pairs by 24h volume
2. Multi-timeframe kline fetch (M15/H1/H4/D1) with cache
3. Technical indicator computation (EMA, RSI, ATR, OBV, CVD)
4. Market structure analysis (trend, BOS/CHoCH, S/R levels)
5. Demand/supply zone detection
6. False breakout scoring
7. Risk-reward plan calculation (structural SL/TP)
8. Volume gate (5 tiers: spike → soft spike → top-10 → stable → minimal)
9. BTC correlation context computation
10. Session timing classification
11. Zone analysis (reaction score, within/near zone)
12. Adaptive scoring pre-check
13. DeepSeek AI analysis with full market context
14. TP2 probability calculation
15. Signal validation
16. Admin notification (BUY/SELL only) + channel broadcast (valid only)
17. Live watchlist update
18. Batch recap per 5 signals
19. Daily recap at 21:00 WIB

### Volume Spike Monitor (30 sec)
1. Poll tickers for top `MAX_REALTIME_PAIRS` by volume
2. Check M15 candle: volume > 2× 20-bar SMA
3. Cooldown 10 min per symbol
4. Duplicate check: skip if active signal exists
5. AI analysis (same DeepSeek pipeline)
6. Watchlist update + Telegram alert

### Zone Proximity Monitor (60 sec)
1. Poll tickers for top `ZONE_MONITOR_PAIRS` by volume
2. Lightweight: M15 (50 candles) + H1 (100 candles) only
3. Detect S/D zones + S/R levels from market structure
4. Proximity evaluation:
   - `price_within_demand/supply` → full AI analysis
   - `near_support/resistance` (0.5%) → full AI analysis
   - `approaching` (0.3-2.5%) → admin alert only
5. Cooldown 5 min per symbol
6. On trigger: full 4 TF fetch + detect_setup + DeepSeek + broadcast

## Live Watchlist System

### Architecture
```
Scanner / Spike Monitor / Zone Monitor
         │
         ▼
   update_from_scan()
         │
    ┌────┴────┐
    │ State Machine  │  ← WATCHING/ACCUMULATING/BREAKOUT_READY/TRENDING/CHOPPY/WEAK
    │ Priority Calc  │  ← 6-factor weighted score
    │ Prob Tracking  │  ← previous → current with delta + reason
    │ Opp Ranking    │  ← composite opportunity score
    └────┬────┘
         │
         ▼
   WatchlistItem DB
         │
         ▼
   refresh_all()
         │
    ┌────┴────┐
    │ editMessageText (update existing)  │
    │ OR sendMessage (create new)        │
    └────────────────────────────────────┘
```

### Priority Score Formula
| Factor | Weight |
|--------|--------|
| AI Confidence | 40% |
| Orderflow Score | 20% |
| Volume Ratio | 15% |
| Risk-Reward | 10% |
| Momentum (spike + CVD) | 10% |
| HTF Context | 5% |

### States & Transitions
| From | To (allowed) |
|------|-------------|
| WATCHING | ACCUMULATING, BREAKOUT_READY, BREAKDOWN_READY, PULLBACK_READY, TRENDING, CHOPPY, WEAK |
| ACCUMULATING | BREAKOUT_READY, TRENDING, WEAK |
| BREAKOUT_READY | TRENDING, CHOPPY, WEAK |
| PULLBACK_READY | TRENDING, BREAKOUT_READY, WATCHING, WEAK |
| TRENDING | CHOPPY, WEAK, PULLBACK_READY |
| CHOPPY | WATCHING, BREAKOUT_READY, BREAKDOWN_READY, WEAK |
| WEAK | WATCHING, INVALID |
| INVALID | (terminal) |

### Telegram Display
```
Live Watchlist  —  12:16 UTC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔥 READY
🟢 BTCUSDT [BREAKOUT_READY] op72 84% Δ+6% | P78 | 0.5%
  volume increasing, near key level
  D1 bullish trend, H4 support holding, buyers active

👀 WATCHING (12)
...

⚠ WEAK (3)
...

Total: 16
```

## Safety Rules

- Signal-only MVP. No auto-trading.
- No exchange API keys required for market data.
- No private API endpoints (balance, account, position, leverage, withdrawal).
- No automatic VPN/proxy bypass logic.
- Redirects not followed silently in market clients.
- If all providers fail, bot stays alive and sends diagnostic summary.

## Installation

```bash
cd crypto-ai-signal-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your keys

# Run
python run.py
```

## API Endpoints

- `GET /health`
- `POST /scan`
- `POST /scan/run`
- `GET /scan/state`
- `GET /status`
- `GET /last_scan`
- `GET /signals`
- `GET /rejected`
- `GET /orderflow/{symbol}`
- `POST /telegram/webhook`
