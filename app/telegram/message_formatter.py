from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from html import escape
from math import ceil
from typing import Any, Iterable
from zoneinfo import ZoneInfo


SEP = "━━━━━━━━━━━━━━━"
WIB = ZoneInfo("Asia/Jakarta")


def h(value: Any) -> str:
    return escape("" if value is None else str(value))


def split_long_message(text: str, max_length: int = 3800) -> list[str]:
    if len(text) <= max_length:
        return [text]
    chunks: list[str] = []
    current = ""
    for block in text.split("\n"):
        line = block + "\n"
        if len(current) + len(line) > max_length:
            if current:
                chunks.append(current.rstrip())
            current = line
        else:
            current += line
    if current:
        chunks.append(current.rstrip())
    return chunks


def paginate_items(items: Iterable[Any], page: int, per_page: int) -> tuple[list[Any], int, int]:
    rows = list(items)
    total_pages = max(1, ceil(len(rows) / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    return rows[start : start + per_page], page, total_pages


def compact_number(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    sign = "-" if number < 0 else ""
    number = abs(number)
    for suffix, size in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if number >= size:
            return f"{sign}{number / size:.2f}".rstrip("0").rstrip(".") + suffix
    return f"{sign}{number:,.0f}"


def percent(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def price(value: Any, symbol: str = "") -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if symbol.startswith(("BTC", "ETH")):
        return f"{number:,.2f}"
    if number < 0.01:
        return f"{number:.8f}"
    return f"{number:,.4f}".rstrip("0").rstrip(".")


def time_wib(value: Any = None) -> str:
    if value is None:
        dt = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return h(value)
    return dt.astimezone(WIB).strftime("%d %b %Y, %H:%M WIB")


def parse_json(value: Any, default: Any = None) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value if value is not None else default


def format_start_message(settings=None) -> str:
    provider = getattr(settings, "market_provider", "-") if settings else "-"
    auto = "ON" if getattr(settings, "auto_broadcast", False) else "OFF"
    orderflow = "ON" if getattr(settings, "enable_orderflow", False) else "OFF"
    return f"""<b>🤖 CryptoTrade Admin Bot</b>

Bot aktif dan siap digunakan.

{SEP}
<b>Mode:</b> Signal-only
<b>Market:</b> Crypto Perpetual
<b>Provider:</b> {h(provider)}
<b>Auto Broadcast:</b> {auto}
<b>Orderflow:</b> {orderflow}

Gunakan /help untuk melihat daftar command."""


def format_help_message() -> str:
    return f"""<b>📘 CryptoTrade Command Guide</b>

{SEP}
<b>Scanner</b>
<code>/scan_now</code> — Jalankan scan manual
<code>/last_scan</code> — Lihat hasil scan terakhir
<code>/status</code> — Status bot dan provider

<b>Market Data</b>
<code>/pairs</code> — Daftar pair yang dipantau
<code>/top_volume</code> — Pair dengan volume tertinggi
<code>/diagnose_market</code> — Cek koneksi market provider
<code>/diagnose_binance</code> — Cek endpoint Binance legacy
<code>/orderflow BTCUSDT</code> — Ringkasan orderflow symbol
<code>/orderflow_top</code> — Top aktivitas orderflow

<b>Signals</b>
<code>/signals</code> — Sinyal valid terakhir
<code>/waiting</code> — Setup WAIT/rejected
<code>/broadcast_on</code> — Aktifkan auto broadcast
<code>/broadcast_off</code> — Matikan auto broadcast

<b>Settings</b>
<code>/settings</code> — Lihat konfigurasi bot
<code>/set_confidence 70</code> — Ubah minimum confidence
<code>/set_rr 2.0</code> — Ubah minimum RR

{SEP}
<b>Catatan:</b>
Bot ini hanya signal-only. Tidak melakukan auto-trade."""


def format_status_message(status_data: dict[str, Any]) -> str:
    return f"""<b>📊 CryptoTrade Status</b>

{SEP}
<b>Bot:</b> 🟢 active
<b>Mode:</b> Signal-only
<b>Provider:</b> {h(status_data.get('market_provider'))}
<b>Fallback:</b> {h(status_data.get('fallback_provider'))}
<b>Orderflow:</b> {status_icon(status_data.get('enable_orderflow'))}
<b>Auto Broadcast:</b> {status_icon(status_data.get('auto_broadcast'))}

{SEP}
<b>Scanner</b>
<b>Max Pairs:</b> {h(status_data.get('max_pairs'))}
<b>Realtime Pairs:</b> {h(status_data.get('max_realtime_pairs'))}
<b>Depth Pairs:</b> {h(status_data.get('max_depth_pairs'))}
<b>Scan Interval:</b> {h(status_data.get('scan_interval_minutes'))} menit
<b>Last Scan:</b> {time_wib(status_data.get('last_scan_time')) if status_data.get('last_scan_time') else 'never'}

{SEP}
<b>Rules</b>
<b>Min Confidence:</b> {h(status_data.get('min_confidence'))}%
<b>Min RR:</b> 1:{h(status_data.get('min_risk_reward'))}
<b>Market:</b> USDT Perpetual

{SEP}
<b>Last Result</b>
<b>Scanned:</b> {h(status_data.get('total_scanned', 0))}
<b>Candidate:</b> {h(status_data.get('candidate_count', 0))}
<b>Valid Signal:</b> {h(status_data.get('valid_signal_count', 0))}
<b>Rejected:</b> {h(status_data.get('rejected_count', 0))}"""


def format_scan_started_message(settings) -> str:
    return f"""<b>🔎 Manual Scan Started</b>

Bot sedang scan market sekarang.

{SEP}
<b>Provider:</b> {h(settings.market_provider)}
<b>Max Pairs:</b> {h(settings.max_pairs)}
<b>Timeframes:</b> 15m, 1h, 4h, 1d
<b>Orderflow:</b> {status_icon(settings.enable_orderflow)}

Hasil akan dikirim setelah scan selesai."""


def format_scan_result_message(scan_result: dict[str, Any]) -> str:
    summary = scan_result.get("summary", {}) or {}
    valid = scan_result.get("valid_signals_rows", []) or []
    rows = "\n\n".join(format_signal_row(item) for item in valid) or "⚪ Tidak ada signal valid."
    return f"""<b>✅ Scan Completed</b>

{SEP}
<b>Summary</b>
<b>Provider:</b> {h(summary.get('provider', '-'))}
<b>Scanned:</b> {h(scan_result.get('total_pairs', 0))} pairs
<b>Candidate:</b> {h(scan_result.get('candidates', 0))}
<b>Valid Signals:</b> {h(scan_result.get('valid_signals', 0))}
<b>Rejected:</b> {h(scan_result.get('rejected', 0))}
<b>Duration:</b> {h(scan_result.get('duration', '-'))}s
<b>Time:</b> {time_wib()}

{SEP}
<b>Valid Signals</b>
{rows}

{SEP}
<b>Next Action:</b>
Review signal di atas, lalu approve/reject dari tombol admin."""


def format_no_setup_message(scan_result: dict[str, Any]) -> str:
    summary = scan_result.get("summary", {}) or {}
    reasons = Counter(summary.get("rejected_reasons", []) or [])
    rows = "\n".join(f"• {h(k.replace('_', ' ').title())}: <b>{v}</b>" for k, v in reasons.most_common()) or "• No rejected data"
    return f"""<b>⚪ No Valid Setup</b>

Tidak ada setup yang layak broadcast saat ini.

{SEP}
<b>Scan Summary</b>
<b>Provider:</b> {h(summary.get('provider', '-'))}
<b>Scanned:</b> {h(scan_result.get('total_pairs', 0))} pairs
<b>Candidate:</b> {h(scan_result.get('candidates', 0))}
<b>Valid Signals:</b> 0
<b>Rejected:</b> {h(scan_result.get('rejected', 0))}
<b>Duration:</b> {h(scan_result.get('duration', '-'))}s
<b>Time:</b> {time_wib()}

{SEP}
<b>Rejected Reasons</b>
{rows}

{SEP}
<b>Next Scan:</b> sesuai scheduler"""


def format_pairs_message(pairs: list[dict[str, Any]], page: int = 1, per_page: int = 20) -> str:
    items, page, total_pages = paginate_items(pairs, page, per_page)
    rows = "\n".join(f"{i + 1 + (page - 1) * per_page:02d}  {h(x.get('symbol','')):<12} {h(x.get('status','TRADING')):<10} #{h(x.get('rank', x.get('volume_rank','-')))}" for i, x in enumerate(items))
    return f"""<b>📌 Monitored Pairs</b>

{SEP}
<b>Provider:</b> {h((pairs[0] if pairs else {}).get('provider', '-'))}
<b>Market:</b> USDT Perpetual
<b>Total:</b> {len(pairs)} pairs
<b>Page:</b> {page}/{total_pages}

{SEP}
<pre>#   Symbol        Status     Rank
{rows}</pre>

{SEP}
<b>Tip:</b> Gunakan /top_volume untuk lihat ranking berdasarkan volume."""


def format_top_volume_message(pairs: list[dict[str, Any]], page: int = 1, per_page: int = 15) -> str:
    items, page, total_pages = paginate_items(pairs, page, per_page)
    rows = []
    for i, x in enumerate(items):
        idx = i + 1 + (page - 1) * per_page
        rows.append(f"{idx:02d}  {h(x.get('symbol','')):<12} {price(x.get('last_price'), x.get('symbol','')):>11} {percent(x.get('price_change_pct', 0)):>8} {compact_number(x.get('quote_volume')):>9}")
    return f"""<b>📊 Top Volume Pairs</b>

{SEP}
<b>Provider:</b> {h((pairs[0] if pairs else {}).get('provider', '-'))}
<b>Market:</b> USDT Perpetual
<b>Total:</b> {len(pairs)}
<b>Sort:</b> 24h Quote Volume
<b>Page:</b> {page}/{total_pages}

{SEP}
<pre>#   Pair          Price        24h%      Volume
{chr(10).join(rows)}</pre>

{SEP}
<b>Filter:</b> USDT perpetual, active/trading only."""


def format_signals_message(signals: list[Any], page: int = 1, per_page: int = 10) -> str:
    if not signals:
        return f"""<b>⚪ No Signals Yet</b>

Belum ada signal valid yang tersimpan.

{SEP}
Jalankan <code>/scan_now</code> untuk scan manual."""
    items, page, total_pages = paginate_items(signals, page, per_page)
    cards = "\n\n".join(format_signal_log_card(x) for x in items)
    return f"""<b>📈 Recent Valid Signals</b>

{SEP}
<b>Total:</b> {len(signals)}
<b>Page:</b> {page}/{total_pages}
<b>Filter:</b> Valid signal only

{SEP}
{cards}"""


def format_waiting_message(waiting_items: list[Any], page: int = 1, per_page: int = 15) -> str:
    items, page, total_pages = paginate_items(waiting_items, page, per_page)
    rows = []
    for i, item in enumerate(items):
        rows.append(f"{i + 1 + (page - 1) * per_page:02d}  {h(getattr(item, 'symbol', '')):<12} {h(getattr(item, 'reason', '')[:18]):<18} {'-':<6}")
    return f"""<b>🟡 Waiting / Rejected Setups</b>

{SEP}
<b>Total:</b> {len(waiting_items)}
<b>Page:</b> {page}/{total_pages}
<b>Mode:</b> WAIT + rejected candidate

{SEP}
<pre>#   Pair          Reason              TF
{chr(10).join(rows)}</pre>

{SEP}
<b>Note:</b> Pair WAIT tidak dikirim ke channel."""


def format_settings_message(settings: dict[str, Any]) -> str:
    return f"""<b>⚙️ CryptoTrade Settings</b>

{SEP}
<b>Market Provider</b>
<b>Primary:</b> {h(settings.get('market_provider'))}
<b>Fallback:</b> {h(settings.get('fallback_market_provider'))}
<b>Altcoin Provider:</b> {h(settings.get('altcoin_provider'))}

{SEP}
<b>Scanner</b>
<b>Max Pairs:</b> {h(settings.get('max_pairs'))}
<b>Scan Interval:</b> {h(settings.get('scan_interval_minutes'))} menit
<b>Timeframes:</b> 15m, 1h, 4h, 1d

{SEP}
<b>Signal Rules</b>
<b>Min Confidence:</b> {h(settings.get('min_confidence'))}%
<b>Min RR:</b> 1:{h(settings.get('min_risk_reward'))}
<b>Auto Broadcast:</b> {status_icon(settings.get('auto_broadcast'))}

{SEP}
<b>Orderflow</b>
<b>Enabled:</b> {status_icon(settings.get('enable_orderflow'))}
<b>Realtime Pairs:</b> {h(settings.get('max_realtime_pairs'))}
<b>Depth Pairs:</b> {h(settings.get('max_depth_pairs'))}
<b>Windows:</b> {h(settings.get('orderflow_windows'))}

{SEP}
<b>Commands</b>
<code>/set_confidence 70</code>
<code>/set_rr 2.0</code>
<code>/broadcast_on</code>
<code>/broadcast_off</code>"""


def format_set_confidence_message(old_value: Any, new_value: Any) -> str:
    return f"""<b>✅ Confidence Updated</b>

{SEP}
<b>Old:</b> {h(old_value)}%
<b>New:</b> {h(new_value)}%

Signal hanya bisa broadcast jika confidence minimal <b>{h(new_value)}%</b>."""


def format_set_rr_message(old_value: Any, new_value: Any) -> str:
    return f"""<b>✅ Risk-Reward Updated</b>

{SEP}
<b>Old:</b> 1:{h(old_value)}
<b>New:</b> 1:{h(new_value)}

Signal hanya bisa broadcast jika RR minimal <b>1:{h(new_value)}</b>."""


def format_broadcast_on_message(settings: dict[str, Any]) -> str:
    return f"""<b>🟢 Auto Broadcast Enabled</b>

Signal valid akan otomatis dikirim ke channel jika memenuhi rules.

{SEP}
<b>Min Confidence:</b> {h(settings.get('min_confidence'))}%
<b>Min RR:</b> 1:{h(settings.get('min_risk_reward'))}
<b>Channel:</b> {status_icon(settings.get('channel_enabled'))}

<b>Warning:</b>
Pastikan rules sudah sesuai sebelum membiarkan auto broadcast aktif."""


def format_broadcast_off_message(settings: dict[str, Any]) -> str:
    return f"""<b>🔴 Auto Broadcast Disabled</b>

Semua signal valid akan dikirim ke admin dulu untuk approval manual.

{SEP}
<b>Mode:</b> Manual Approval
<b>Action:</b> Admin harus klik Approve Broadcast."""


def format_last_scan_message(scan_log: Any) -> str:
    if not scan_log:
        return format_error_message("No Scan Yet", "Belum ada scan tersimpan.", "Jalankan /scan_now untuk scan manual.")
    summary = parse_json(scan_log.summary_json, {}) or {}
    reasons = Counter(summary.get("rejected_reasons", []) or {})
    rows = "\n".join(f"• {h(k.replace('_', ' ').title())}: <b>{v}</b>" for k, v in reasons.most_common(8)) or "⚪ Tidak ada rejected reason."
    return f"""<b>🕒 Last Scan Report</b>

{SEP}
<b>Time:</b> {time_wib(scan_log.timestamp)}
<b>Provider:</b> {h(summary.get('provider', '-'))}
<b>Duration:</b> -

{SEP}
<b>Result</b>
<b>Scanned:</b> {h(scan_log.total_pairs)}
<b>Candidate:</b> {h(scan_log.candidates_count)}
<b>Valid Signals:</b> {h(scan_log.valid_signals_count)}
<b>Rejected:</b> {h(scan_log.rejected_count)}

{SEP}
<b>Top Rejected Reasons</b>
{rows}

{SEP}
<b>Latest Valid Signals</b>
⚪ Tidak ada signal valid pada scan terakhir."""


def format_diagnose_binance_message(result: list[dict[str, Any]]) -> str:
    rows = []
    statuses = []
    for idx, row in enumerate(result, start=1):
        status = row.get("status_code", "error")
        statuses.append(status)
        rows.append(f"<b>{idx}. {h(row.get('name'))}</b>\nURL: <code>{h(row.get('endpoint'))}</code>\nStatus: <b>{h(status)}</b>\nContent-Type: <code>{h(row.get('content_type', ''))}</code>\nLocation: <code>{h(row.get('location') or '-')}</code>")
    footer = "✅ Binance market endpoint accessible." if all(s == 200 for s in statuses) else "⚠️ Redirect/rate-limit/network issue detected."
    return f"""<b>🧪 Binance Diagnostic</b>

{SEP}
<b>Status:</b> {h('OK' if all(s == 200 for s in statuses) else 'WARNING')}
<b>Time:</b> {time_wib()}

{SEP}
{chr(10).join(rows)}

{SEP}
{footer}"""


def format_diagnose_provider_message(result: list[dict[str, Any]]) -> str:
    rows = []
    ok = any(x.get("status") == "ok" for x in result)
    primary = result[0].get("provider") if result else "-"
    fallback = result[1].get("provider") if len(result) > 1 else "-"
    for row in result:
        rows.append(f"<b>{h(row.get('provider'))}</b>\nREST: {status_icon(row.get('status') == 'ok')}\nWebSocket: ⚪ not tested\nSymbols: {h(row.get('symbols'))}\nTicker: {h(row.get('tickers'))}\nKline: ⚪ not tested\nOrderbook: ⚪ not tested\nError: <code>{h(row.get('error', ''))}</code>")
    recommendation = "Provider siap digunakan." if ok else "Cek network/VPN/provider endpoint. Bot tetap hidup dan scan akan skip jika semua provider gagal."
    return f"""<b>🧪 Market Provider Diagnostic</b>

{SEP}
<b>Primary:</b> {h(primary)}
<b>Fallback:</b> {h(fallback)}
<b>Status:</b> {h('OK' if ok else 'WARNING')}

{SEP}
{chr(10).join(rows)}

{SEP}
<b>Recommendation:</b>
{h(recommendation)}"""


def format_signal_candidate_admin_message(signal: dict[str, Any]) -> str:
    risk = signal.get("risk", {}) or {}
    entry = signal.get("entry", {}) or {}
    bias = signal.get("bias", {}) or {}
    of = signal.get("orderflow_summary") or signal.get("orderflow", {}) or {}
    ai_of = signal.get("orderflow", {}) or {}
    scores = signal.get("scores", {}) or {}
    decision = signal.get("decision")
    return f"""<b>{side_emoji(decision)} {h(signal.get('symbol'))} — {h(decision)} Candidate</b>

{SEP}
<b>Decision:</b> {h(decision)}
<b>Confidence:</b> {h(signal.get('confidence'))}%
<b>Setup:</b> {h(signal.get('setup_type'))}
<b>RR:</b> 1:{h(risk.get('risk_reward'))}
<b>Provider:</b> {h(signal.get('provider', '-'))}

{SEP}
<b>Bias</b>
D1: {h(bias.get('D1'))}
H4: {h(bias.get('H4'))}
H1: {h(bias.get('H1'))}
M15: {h(bias.get('M15'))}

{SEP}
<b>Trade Plan</b>
<b>Entry:</b> <code>{h(entry.get('zone'))}</code>
<b>SL:</b> <code>{h(risk.get('stop_loss'))}</code>
<b>TP1:</b> <code>{h(risk.get('take_profit_1'))}</code>
<b>TP2:</b> <code>{h(risk.get('take_profit_2'))}</code>

{SEP}
<b>Score</b>
Technical: {h(scores.get('technical_score', 0))}/60
Orderflow: {h(scores.get('orderflow_score', ai_of.get('score', 0)))}/25
Risk: {h(scores.get('risk_score', 0))}/15
Final: {h(scores.get('final_confidence', signal.get('confidence', 0)))}/100

{SEP}
<b>Reason</b>
{h(signal.get('reason'))}

{SEP}
<b>Invalid If</b>
{h(signal.get('invalid_if'))}

{SEP}
<b>Orderflow</b>
Bias: {h(of.get('orderflow_bias', ai_of.get('bias', 'insufficient_data')))}
Delta: {h(of.get('volume_delta', 0))}
CVD: {h(of.get('cumulative_volume_delta', 0))}
Delta Ratio: {h(of.get('delta_ratio', 0))}
Imbalance: {h(of.get('orderbook_imbalance', 0))}
Spread: {h(of.get('spread', 0))}
Liquidation: {h(of.get('liquidation_spike_detected', False))}
OI Change: {h(of.get('open_interest_change', 0))}%
Absorption: {h(of.get('absorption_signal', ai_of.get('absorption_signal', 'none')))}"""


def format_signal_broadcast_channel_message(signal: dict[str, Any]) -> str:
    risk = signal.get("risk", {}) or {}
    entry = signal.get("entry", {}) or {}
    decision = signal.get("decision")
    of = signal.get("orderflow_summary") or signal.get("orderflow", {}) or {}
    of_line = of.get("flow_interpretation") or of.get("interpretation") or "Orderflow confirmation included."
    return f"""<b>{side_emoji(decision)} {h(signal.get('symbol'))} — {h(decision)} {h((entry.get('type') or 'limit').upper())}</b>

{SEP}
<b>Entry Zone</b>
<code>{h(entry.get('zone'))}</code>

<b>Stop Loss</b>
<code>{h(risk.get('stop_loss'))}</code>

<b>Take Profit</b>
TP1: <code>{h(risk.get('take_profit_1'))}</code>
TP2: <code>{h(risk.get('take_profit_2'))}</code>

{SEP}
<b>Setup</b>
{h(signal.get('setup_type'))}

<b>Confidence:</b> {h(signal.get('confidence'))}%
<b>RR:</b> 1:{h(risk.get('risk_reward'))}

<b>Orderflow:</b>
{h(str(of_line)[:180])}

{SEP}
<b>Invalid If</b>
{h(signal.get('invalid_if'))}

{SEP}
<b>Risk Reminder</b>
Gunakan risk management masing-masing. Signal ini bukan jaminan profit."""


def format_orderflow_summary_message(summary: dict[str, Any]) -> str:
    return f"""<b>📡 Orderflow Summary — {h(summary.get('symbol'))}</b>

{SEP}
<b>Window:</b> {h(summary.get('window'))}
<b>Price:</b> {price(summary.get('best_ask') or summary.get('best_bid'), summary.get('symbol', ''))}
<b>Spread:</b> {h(summary.get('spread'))}

{SEP}
<b>Trade Flow</b>
Buy Volume: <b>{compact_number(summary.get('buy_volume'))}</b>
Sell Volume: <b>{compact_number(summary.get('sell_volume'))}</b>
Delta: <b>{compact_number(summary.get('volume_delta'))}</b>
Delta Ratio: <b>{h(summary.get('delta_ratio'))}</b>
CVD: <b>{compact_number(summary.get('cumulative_volume_delta'))}</b>

{SEP}
<b>Activity</b>
Trades: {h(summary.get('trade_count'))}
Intensity: {h(summary.get('trade_intensity'))}
Avg Size: {h(summary.get('average_trade_size'))}
Large Trades: {h(summary.get('large_trade_count'))}

{SEP}
<b>Orderbook</b>
Best Bid: <code>{h(summary.get('best_bid'))}</code>
Best Ask: <code>{h(summary.get('best_ask'))}</code>
Imbalance: <b>{h(summary.get('orderbook_imbalance'))}</b>
Wall: {h(summary.get('liquidity_wall_side'))} at <code>{h(summary.get('liquidity_wall_price'))}</code>

{SEP}
<b>Liquidation</b>
Buy Liq: {compact_number(summary.get('liquidation_buy_notional'))}
Sell Liq: {compact_number(summary.get('liquidation_sell_notional'))}
Spike: {h(summary.get('liquidation_spike_detected'))}

{SEP}
<b>Open Interest</b>
OI: {compact_number(summary.get('open_interest'))}
OI Change: {percent(summary.get('open_interest_change'))}

{SEP}
<b>Interpretation</b>
{h(summary.get('flow_interpretation', summary.get('interpretation')))}"""


def format_orderflow_top_message(rows: list[Any]) -> str:
    if not rows:
        return format_error_message("No Orderflow Data", "Belum ada snapshot orderflow tersimpan.", "Jalankan /scan_now atau tunggu realtime stream mengumpulkan data.")
    seen = set()
    unique = []
    for row in rows:
        symbol = getattr(row, "symbol", "")
        if symbol not in seen:
            seen.add(symbol)
            unique.append(row)
        if len(unique) >= 15:
            break
    unique.sort(key=lambda r: abs(getattr(r, "volume_delta", 0)), reverse=True)
    table = []
    for idx, row in enumerate(unique, start=1):
        symbol = getattr(row, "symbol", "")
        table.append(f"{idx:02d}  {h(symbol):<15} {h(getattr(row, 'orderflow_bias', '')):<15} {compact_number(getattr(row, 'volume_delta', 0)):>10} {h(getattr(row, 'trade_intensity', '')):<10} {percent(getattr(row, 'open_interest_change', 0)):>8}")
    return f"""<b>📡 Top Orderflow Activity</b>

{SEP}
<pre>#   Pair            Bias             Delta       Intensity    OI%
{chr(10).join(table)}</pre>"""


def format_error_message(title: str, error: Any, suggestion: str | None = None) -> str:
    text = f"""<b>⚠️ {h(title)}</b>

{SEP}
<b>Error</b>
<code>{h(str(error)[:700])}</code>"""
    if suggestion:
        text += f"\n\n{SEP}\n<b>Suggestion</b>\n{h(suggestion)}"
    return text


def format_access_denied_message() -> str:
    return "<b>⛔ Access Denied</b>\n\nCommand ini hanya bisa digunakan oleh admin."


def status_icon(enabled: Any) -> str:
    return "🟢 ON" if enabled in {True, "true", "True", "ON", "on"} else "🔴 OFF"


def side_emoji(decision: Any) -> str:
    return "🟢" if decision == "BUY" else "🔴" if decision == "SELL" else "🟡"


def format_signal_row(item: dict[str, Any]) -> str:
    risk = item.get("risk", {}) or {}
    entry = item.get("entry", {}) or {}
    decision = item.get("decision")
    return f"{side_emoji(decision)} <b>{h(item.get('symbol'))}</b> — {h(decision)}\nConfidence: <b>{h(item.get('confidence'))}%</b> | RR: <b>1:{h(risk.get('risk_reward'))}</b>\nEntry: <code>{h(entry.get('zone'))}</code>\nSL: <code>{h(risk.get('stop_loss'))}</code>\nTP: <code>{h(risk.get('take_profit_1'))}</code> / <code>{h(risk.get('take_profit_2'))}</code>"


def format_signal_log_card(row: Any) -> str:
    decision = getattr(row, "decision", "WAIT")
    return f"""{side_emoji(decision)} <b>{h(getattr(row, 'symbol', ''))}</b> — <b>{h(decision)} LIMIT</b>
<b>Confidence:</b> {h(getattr(row, 'confidence', 0))}%
<b>RR:</b> 1:{h(getattr(row, 'risk_reward', 0))}
<b>Entry:</b> <code>{h(getattr(row, 'entry_zone', ''))}</code>
<b>SL:</b> <code>{h(getattr(row, 'stop_loss', ''))}</code>
<b>TP:</b> <code>{h(getattr(row, 'take_profit_1', ''))}</code> / <code>{h(getattr(row, 'take_profit_2', ''))}</code>
<b>Status:</b> {h(getattr(row, 'status', ''))}
<b>Time:</b> {time_wib(getattr(row, 'timestamp', None))}"""
