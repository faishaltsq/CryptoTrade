# CryptoTrade

CryptoTrade is a signal-only crypto market analysis bot. It scans public perpetual futures market data, detects technical setup candidates, validates them with DeepSeek, sends candidates to a Telegram admin bot, and broadcasts approved signals to a Telegram channel.

The project does not place trades. It does not use private exchange APIs, trading endpoints, account endpoints, balance endpoints, position endpoints, leverage endpoints, or withdrawal permissions.

## Features

- Multi-provider public market data architecture.
- Primary provider: Bybit.
- Fallback provider: OKX.
- Altcoin expansion provider: Gate.io, with MEXC support and KuCoin optional skeleton.
- USDT perpetual market focus.
- Automatic provider failover when the primary provider fails.
- Public WebSocket orderflow layer for realtime trade, ticker, kline, depth, and liquidation data where supported.
- Multi-timeframe candles: `15m`, `1h`, `4h`, `1d`.
- Technical analysis: EMA 50/200, RSI 14, ATR 14, swing high/low, market structure, BOS/CHoCH, liquidity sweep, order block, FVG, volume spike, risk-reward.
- DeepSeek strict JSON validation.
- Telegram admin approval flow with inline buttons.
- Telegram channel broadcast after approval.
- SQLite MVP database with SQLAlchemy models.
- FastAPI API and Swagger docs.
- APScheduler scheduled scans.
- Binance diagnostic module retained for troubleshooting only; scanner does not depend on Binance by default.

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

## Binance Diagnostic

Binance is not required for the default scanner, but a diagnostic tool is available:

```bash
python -m app.market_data.binance_diagnostic
```

Legacy Telegram command:

```text
/diagnose_binance
```

Use `/diagnose_market` for general provider checks.

Diagnostic uses `follow_redirects=False` and reports endpoint, status code, `Location`, content type, and a 300-character body preview.

HTTP `301/302` means a redirect was detected. The bot does not follow redirects silently and does not use `https://www.binance.com` as a market data source.

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
