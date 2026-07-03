# CryptoTrade

CryptoTrade is an AI-driven signal-only crypto market analysis bot. It extracts objective market features from public perpetual futures data, sends structured market context to DeepSeek for analysis, then routes validated signals to a Telegram admin bot for approval before broadcasting to a channel.

The bot does not hardcode a single trading method. DeepSeek chooses the most relevant analysis approach based on the available data: trend, momentum, volatility, price action, support/resistance, volume, derivatives data, orderflow, and risk-reward.

The project does not place trades. It does not use private exchange APIs, trading endpoints, account endpoints, balance endpoints, position endpoints, leverage endpoints, or withdrawal permissions.

## Features

- AI-driven market analysis via DeepSeek. No hardcoded single trading method.
- Multi-provider public market data architecture.
- Primary provider: Bybit.
- Fallback provider: OKX.
- Altcoin expansion provider: Gate.io, with MEXC support and KuCoin optional skeleton.
- USDT perpetual market focus.
- Automatic provider failover when the primary provider fails.
- Public WebSocket orderflow layer for realtime trade, ticker, kline, depth, and liquidation data where supported.
- Orderflow used as confirmation layer only, not standalone entry trigger.
- Multi-timeframe candles: `15m`, `1h`, `4h`, `1d`.
- Market feature extraction: EMA, RSI, ATR, swing points, market structure, price zones, volume spikes, risk-reward.
- DeepSeek strict JSON validation.
- Telegram admin approval flow with inline buttons.
- Telegram channel broadcast after approval.
- SQLite MVP database with SQLAlchemy models.
- FastAPI API and Swagger docs.
- APScheduler scheduled scans.

## Safety Rules

- Signal-only MVP.
- No auto-trading.
- No exchange API keys required for market data.
- No private API endpoints.
- No order creation/cancellation.
- No balance, account, position, leverage, margin, or withdrawal endpoints.
- No automatic VPN/proxy bypass logic.
- Redirects are not followed silently in market clients.
- If all providers fail, the bot stays alive and sends a diagnostic summary to the admin.

## Project Structure

```text
app/
  ai/                 DeepSeek client, prompt builder, response parser
  analysis/           Indicators, structure, SMC, setup detection, RR
  database/           SQLAlchemy models, session, repository
  market_data/        Multi-provider public market data clients
  orderflow/          Public WebSocket orderflow providers and aggregation
  signal/             Signal validation, formatting, broadcasting
  telegram/           Admin bot commands, callbacks, webhook/ngrok setup
  utils/              Logging and time helpers
run.py                FastAPI runner
requirements.txt      Python dependencies
.env.example          Environment template
```

## Requirements

- Python 3.11+
- Telegram bot token from BotFather
- DeepSeek API key
- Optional ngrok account/token for local Telegram webhook testing

## Installation

```bash
cd crypto-ai-signal-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and fill your secrets:

```env
DEEPSEEK_API_KEY=your_deepseek_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_ADMIN_CHAT_ID=your_admin_chat_id
TELEGRAM_CHANNEL_CHAT_ID=your_channel_chat_id
```

Do not commit `.env`.

## Market Provider Config

Default provider order:

```env
MARKET_PROVIDER=bybit
FALLBACK_MARKET_PROVIDER=okx
ALTCOIN_PROVIDER=gate
```

Provider endpoints:

```env
BYBIT_REST_BASE_URL=https://api.bybit.com
BYBIT_WS_LINEAR_URL=wss://stream.bybit.com/v5/public/linear
OKX_REST_BASE_URL=https://www.okx.com
OKX_WS_PUBLIC_URL=wss://ws.okx.com:8443/ws/v5/public
GATE_REST_BASE_URL=https://api.gateio.ws/api/v4
GATE_FUTURES_WS_URL=wss://fx-ws.gateio.ws/v4/ws/usdt
MEXC_REST_BASE_URL=https://contract.mexc.com
MEXC_SPOT_WS_URL=wss://wbs-api.mexc.com/ws
```

Scan universe size:

```env
MAX_PAIRS=150
```

This expands the scan universe for liquid crypto perpetuals, including altcoin, memecoin, DeFi, and other crypto sectors while filtering known stock-like and metals contracts from mixed providers.

Scanner tries providers in this order:

1. `MARKET_PROVIDER`
2. `FALLBACK_MARKET_PROVIDER`
3. `ALTCOIN_PROVIDER`

If all fail, the scan is skipped and the bot remains online.

## Orderflow Config

```env
ENABLE_ORDERFLOW=true
ENABLE_LIQUIDATION_STREAM=true
MAX_REALTIME_PAIRS=30
MAX_DEPTH_PAIRS=10
ORDERFLOW_WINDOWS=10s,1m,5m
```

Performance rules:

- Top pairs use realtime trades/ticker/kline only.
- Depth orderbook is only enabled for setup candidates.
- Raw tick data is not stored without bounds.
- Only orderflow summaries are stored.
- WebSocket tasks auto-reconnect where implemented.

Orderflow metrics include:

- `buy_volume`
- `sell_volume`
- `volume_delta`
- `cumulative_volume_delta`
- `delta_ratio`
- `trade_count`
- `trade_intensity`
- `average_trade_size`
- `large_trade_count`
- `best_bid`
- `best_ask`
- `spread`
- `bid_depth`
- `ask_depth`
- `orderbook_imbalance`
- `liquidity_wall_side`
- `liquidity_wall_price`
- `liquidity_pull_detected`
- `liquidation_buy_notional`
- `liquidation_sell_notional`
- `liquidation_spike_detected`

Orderflow is used as a confirmation layer in DeepSeek prompts, not as the primary entry reason.

## Orderflow Confirmation Layer

Orderflow is used after market setup detection. It is a confirmation layer, not a standalone entry trigger.

Core rules:

- Technical structure remains the primary signal source.
- BUY/SELL can only broadcast when technical setup is valid, RR is valid, final confidence meets threshold, and orderflow has no strong conflict.
- If orderflow conflicts with the technical setup, confidence is reduced or the setup becomes `WAIT`.
- If orderflow supports the setup, confidence can increase.
- If orderflow data is insufficient, the setup may still be sent to admin, but auto-broadcast is blocked.

Auto-broadcast is enabled on launch by default. Use `/broadcast_off` to pause channel broadcasting at runtime.

## Signal Logging And Outcome Tracking

CryptoTrade stores every BUY/SELL signal in `signal_logs` with a unique ID, original AI response, trade plan, market context, orderflow summary, derivatives summary, broadcast status, outcome status, and review status.

For every new signal, the bot also creates a `signal_outcomes` row with `pending` result. This is the foundation for a future learning loop, but it is not model fine-tuning and it does not give DeepSeek permanent memory.

Outcome tracking is signal-only. It does not open positions, place orders, cancel orders, or use private trading APIs. It only checks public market prices against TP/SL/expiry rules.

Tracked outcomes:

- `pending`
- `hit_tp1`
- `hit_tp2`
- `hit_sl`
- `break_even`
- `expired`
- `invalidated`
- `manually_closed`

Default expiry:

- M15/scalp: `SIGNAL_EXPIRY_M15_HOURS=6`
- H1/intraday/default: `SIGNAL_EXPIRY_H1_HOURS=24`
- H4/swing: `SIGNAL_EXPIRY_H4_HOURS=72`

Outcome tracking can be disabled with:

```env
ENABLE_OUTCOME_TRACKING=false
```

Telegram commands:

- `/signals` shows recent BUY/SELL signals.
- `/signal_recap` shows all BUY/SELL signals for the current WIB day.
- `/signal_detail ID` shows full signal context and status.
- `/signal_result ID RESULT` manually updates a signal outcome.
- `/pending_signals` shows signals still waiting for TP/SL/expiry.
- `/outcomes` shows recent closed outcome summary.

Allowed manual results: `hit_tp1`, `hit_tp2`, `hit_sl`, `break_even`, `expired`, `invalidated`, `manually_closed`.

## Signal Learning Loop

CryptoTrade includes a feedback loop for signal quality improvement. This is not DeepSeek fine-tuning and DeepSeek does not gain permanent memory. The bot stores signal history, tracks outcomes, asks DeepSeek to review completed signals, stores suggested lessons, and uses only admin-approved active lessons as context for future analysis.

Learning flow:

```text
Market Data
→ Feature Extractor
→ Orderflow Analyzer
→ Load Active Lessons
→ Adaptive Scoring Precheck
→ DeepSeek AI Market Analyst with learning_context
→ Signal Validator
→ Save Signal
→ Telegram Admin / Channel Broadcast
→ Outcome Tracker
→ Post-Trade Review
→ Suggested Lessons
→ Admin Approval
→ Active Lessons
```

Safety rules:

- Still signal-only.
- No auto-trading.
- No order creation/cancellation.
- No private exchange API.
- DeepSeek review output must be valid JSON.
- AI cannot activate rules directly.
- New lessons are created as `suggested`.
- Only `/approve_lesson ID` makes a lesson `active`.
- Rejected or disabled lessons are not injected into prompts.

Learning config:

```env
ENABLE_SIGNAL_LEARNING=true
ENABLE_AUTO_REVIEW=true
ENABLE_ADAPTIVE_SCORING=true
REQUIRE_ADMIN_APPROVAL_FOR_LESSONS=true
MAX_ACTIVE_LESSONS_IN_PROMPT=10
MIN_EVIDENCE_COUNT_FOR_AUTO_SUGGESTION=5
PERFORMANCE_LOOKBACK_DAYS=30
LEARNING_REVIEW_MODEL=deepseek-chat
LEARNING_PROMPT_VERSION=ai_signal_review_v1
```

Database tables:

- `signal_outcomes` tracks TP/SL/expiry, MFE, MAE, duration, and close reason.
- `signal_reviews` stores DeepSeek post-trade review JSON and failure classification.
- `strategy_lessons` stores suggested/active/rejected/disabled lessons with audit trail.
- `performance_snapshots` stores computed performance summaries.

Post-trade review classification:

- `good_signal`
- `valid_loss`
- `avoidable_loss`
- `bad_signal`
- `inconclusive`

Lesson types:

- `avoid_condition`
- `confidence_penalty`
- `confidence_boost`
- `filter_rule`
- `risk_adjustment`
- `prompt_context`
- `warning_note`

Adaptive scoring:

- Uses active lessons only.
- Confidence penalty is capped at `-25`.
- Confidence boost is capped at `+10`.
- Boost is blocked when RR is poor, orderflow conflicts, or data is insufficient.
- `avoid_condition` and `filter_rule` active lessons can block a candidate before broadcast.

Learning commands:

- `/performance`, `/performance 7d`, `/performance 30d`, `/performance all`
- `/lessons`
- `/lesson_detail ID`
- `/approve_lesson ID`
- `/reject_lesson ID`
- `/disable_lesson ID`
- `/review_signal ID`
- `/signal_result ID RESULT`
- `/learning_status`

Daily recap:

- The bot sends an automatic signal recap every day at `21:00 WIB`.
- Recap includes all BUY/SELL signals for that day without filtering: valid, rejected, broadcasted, failed, pending, TP, SL, and expired.
- Long recap messages are split automatically for Telegram delivery.

Aggressive trade interpretation:

- Aggressive buy volume means buyer taker pressure, not guaranteed new long positions.
- Aggressive sell volume means seller taker pressure, not guaranteed new short positions.
- Buy pressure with open interest rising may suggest new long risk.
- Buy pressure with open interest falling may suggest short covering.
- Sell pressure with open interest rising may suggest new short risk.
- Sell pressure with open interest falling may suggest long closing.

Orderflow scoring:

- Technical score: `0-60`
- Orderflow score: `-25` to `+25`
- Risk score: `0-15`
- Final confidence: `technical_score + orderflow_score + risk_score`, clamped to `0-100`

Telegram commands:

```text
/orderflow BTCUSDT
/orderflow_top
```

`/orderflow SYMBOL` shows the latest 1m orderflow summary for a symbol. `/orderflow_top` lists recent orderflow activity ranked from stored snapshots.

The project remains signal-only and does not perform auto-trading.

## Running Locally

```bash
python run.py
```

Open Swagger docs:

```text
http://localhost:8000/docs
```

Health check:

```bash
curl http://localhost:8000/health
```

Run scan and wait for result:

```bash
curl -X POST http://localhost:8000/scan/run
```

Queue background scan:

```bash
curl -X POST http://localhost:8000/scan
```

Check scan state:

```bash
curl http://localhost:8000/scan/state
```

## Telegram Setup

For local development, enable ngrok:

```env
AUTO_NGROK=true
NGROK_AUTHTOKEN=your_ngrok_token
APP_PORT=8000
```

Then run:

```bash
python run.py
```

Startup should log:

```text
Ngrok tunnel started https://...
Telegram webhook set to https://.../telegram/webhook
```

If deploying to a public server, use:

```env
AUTO_NGROK=false
PUBLIC_BASE_URL=https://your-domain.com
```

## Telegram Commands

Admin-only commands:

- `/start`
- `/status`
- `/scan_now`
- `/pairs`
- `/top_volume`
- `/signals`
- `/waiting`
- `/settings`
- `/set_confidence <value>`
- `/set_rr <value>`
- `/broadcast_on`
- `/broadcast_off`
- `/last_scan`
- `/diagnose_market`
- `/help`

The bot also sends an inline keyboard menu for the main commands.

## Telegram Message Formatting

- Semua command Telegram memakai `parse_mode="HTML"`.
- Dynamic text di-escape sebelum dikirim.
- Message panjang otomatis di-split dengan batas aman 3800 karakter.
- List panjang otomatis memakai pagination.
- Formatter terpusat di `app/telegram/message_formatter.py`.
- `/pairs` menampilkan 20 item per halaman.
- `/top_volume` menampilkan 15 item per halaman.
- `/signals` menampilkan 10 item per halaman.
- `/waiting` menampilkan 15 item per halaman.
- Inline keyboard tersedia untuk Prev, Next, Refresh, menu command, dan action signal.

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

## Database

Default:

```env
DATABASE_URL=sqlite:///crypto_signal_bot.db
```

Tables:

- `scan_logs`
- `signal_logs`
- `rejected_setups`
- `settings`
- `orderflow_snapshots`

`signal_logs` stores `orderflow_summary_json`, `binance_endpoint_status`, and `market_data_error` for audit/debugging.

## Market Diagnostics

Telegram command:

```text
/diagnose_market
```

This checks configured providers from `MARKET_PROVIDER`, `FALLBACK_MARKET_PROVIDER`, and `ALTCOIN_PROVIDER`, then reports symbol/ticker availability and provider errors.

## Development Notes

- The codebase is modular and provider-oriented.
- Bybit and OKX REST providers are implemented first.
- Gate.io and MEXC are included for altcoin expansion.
- KuCoin is an optional provider skeleton.
- No production migration system is included yet; SQLite schema creation is automatic for MVP.

## Roadmap

- Improve OKX/Gate/MEXC WebSocket parsing.
- Add PostgreSQL migration support.
- Add Docker deployment.
- Add signal performance tracking for TP/SL.
- Add backtesting.
- Add dashboard.

Auto-trading is intentionally not implemented.
