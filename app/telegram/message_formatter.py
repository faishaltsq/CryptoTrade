from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
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


def format_entry_zone(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Entry: <code></code>"
    normalized = raw.replace("–", "-").replace("—", "-")
    parts = [x.strip() for x in normalized.split("-") if x.strip()]
    if len(parts) == 2:
        return f"Entry 1: <code>{h(parts[0])}</code>\nEntry 2: <code>{h(parts[1])}</code>"
    return f"Entry: <code>{h(raw)}</code>"


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
    return f"""<b>📈 Recent Signals</b>

{SEP}
<b>Total:</b> {len(signals)}
<b>Page:</b> {page}/{total_pages}
<b>Filter:</b> BUY/SELL signals

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
    market = signal.get("market_summary", {}) or {}
    of = signal.get("orderflow_summary") or signal.get("orderflow", {}) or {}
    ai_of = signal.get("orderflow", {}) or {}
    scores = signal.get("scores", {}) or {}
    methods = signal.get("analysis_method_used", []) or []
    decision = signal.get("decision")
    setup_label = signal.get("setup_type", "no_trade").replace("_", " ").title()
    method_str = " | ".join(m.replace("_", " ").title() for m in methods) or "General Analysis"
    return f"""<b>{side_emoji(decision)} {h(signal.get('symbol'))} — {h(decision)} Candidate</b>

{SEP}
<b>Decision:</b> {h(decision)}
<b>Confidence:</b> {h(signal.get('confidence'))}%
<b>Market Regime:</b> {h(market.get('market_regime', 'unclear'))}
<b>Provider:</b> {h(signal.get('provider', '-'))}
<b>RR:</b> 1:{h(risk.get('risk_reward'))}

{SEP}
<b>Analysis Used:</b>
{method_str}

{SEP}
<b>Market Context:</b>
HTF Bias: {h(market.get('higher_timeframe_bias', 'neutral'))}
LTF Context: {h(market.get('lower_timeframe_context', 'neutral'))}
Main Reason:
{h(market.get('main_reason', signal.get('reason', '')))}

{SEP}
<b>Trade Plan</b>
{format_entry_zone(risk.get('entry_zone'))}
SL: <code>{h(risk.get('stop_loss'))}</code>
TP1: <code>{h(risk.get('take_profit_1'))}</code>
TP2: <code>{h(risk.get('take_profit_2'))}</code>

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
Confirmation: {h(ai_of.get('confirmation', False))}
Conflict: {h(ai_of.get('conflict', False))}
Interpretation:
{h(of.get('flow_interpretation', ai_of.get('interpretation', '')))}"""


def format_signal_broadcast_channel_message(signal: dict[str, Any]) -> str:
    risk = signal.get("risk", {}) or {}
    decision = signal.get("decision")
    of = signal.get("orderflow_summary") or signal.get("orderflow", {}) or {}
    of_line = of.get("flow_interpretation") or of.get("interpretation") or "Orderflow confirmation included."
    setup_label = signal.get("setup_type", "no_trade").replace("_", " ").title()
    market = signal.get("market_summary", {}) or {}
    context = market.get("main_reason", "") or of_line
    return f"""<b>{side_emoji(decision)} {h(signal.get('symbol'))} — {h(decision)} {h((risk.get('entry_type') or 'limit').upper())}</b>

{SEP}
<b>Entry Zone</b>
{format_entry_zone(risk.get('entry_zone'))}

<b>Stop Loss</b>
<code>{h(risk.get('stop_loss'))}</code>

<b>Take Profit</b>
TP1: <code>{h(risk.get('take_profit_1'))}</code>
TP2: <code>{h(risk.get('take_profit_2'))}</code>

{SEP}
<b>Confidence:</b> {h(signal.get('confidence'))}%
<b>RR:</b> 1:{h(risk.get('risk_reward'))}

<b>Market Context:</b>
{h(str(context)[:180])}

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
    return f"{side_emoji(decision)} <b>{h(item.get('symbol'))}</b> — {h(decision)}\nConfidence: <b>{h(item.get('confidence'))}%</b> | RR: <b>1:{h(risk.get('risk_reward'))}</b>\n{format_entry_zone(entry.get('zone'))}\nSL: <code>{h(risk.get('stop_loss'))}</code>\nTP: <code>{h(risk.get('take_profit_1'))}</code> / <code>{h(risk.get('take_profit_2'))}</code>"


def format_signal_log_card(row: Any) -> str:
    decision = getattr(row, "decision", "WAIT")
    outcome = signal_outcome(row)
    current_price = getattr(row, "current_price", 0)
    validity = signal_validity(row, outcome)
    price_line = f"\n<b>Price Now:</b> <code>{h(price(current_price, getattr(row, 'symbol', '')))}</code>" if current_price else ""
    return f"""{side_emoji(decision)} <b>{h(getattr(row, 'symbol', ''))}</b> — <b>{h(decision)} LIMIT</b>
<b>Confidence:</b> {h(getattr(row, 'confidence', 0))}%
<b>RR:</b> 1:{h(getattr(row, 'risk_reward', 0))}
{format_entry_zone(getattr(row, 'entry_zone', ''))}
<b>SL:</b> <code>{h(getattr(row, 'stop_loss', ''))}</code>
<b>TP:</b> <code>{h(getattr(row, 'take_profit_1', ''))}</code> / <code>{h(getattr(row, 'take_profit_2', ''))}</code>{price_line}
<b>Status:</b> {h(outcome)}
<b>Est. Valid:</b> {h(validity)}
<b>Time:</b> {time_wib(getattr(row, 'timestamp', None))}"""


def format_signal_detail_message(row: Any, outcome: Any | None = None) -> str:
    methods = parse_json(getattr(row, "analysis_method_json", "[]"), []) or []
    orderflow = parse_json(getattr(row, "orderflow_summary_json", "{}"), {}) or {}
    return f"""<b>📌 Signal Detail #{h(getattr(row, 'id', ''))}</b>

{SEP}
<b>Symbol:</b> {h(getattr(row, 'symbol', ''))}
<b>Decision:</b> {h(getattr(row, 'decision', ''))}
<b>Provider:</b> {h(getattr(row, 'provider', '') or '-')}
<b>Market:</b> {h(getattr(row, 'market_type', '') or 'USDT Perpetual')}
<b>Confidence:</b> {h(getattr(row, 'confidence', 0))}%
<b>RR:</b> 1:{h(getattr(row, 'risk_reward', 0))}

{SEP}
<b>Trade Plan</b>
{format_entry_zone(getattr(row, 'entry_zone', ''))}
SL: <code>{h(getattr(row, 'stop_loss', ''))}</code>
TP1: <code>{h(getattr(row, 'take_profit_1', ''))}</code>
TP2: <code>{h(getattr(row, 'take_profit_2', ''))}</code>

{SEP}
<b>Market Context</b>
Regime: {h(getattr(row, 'market_regime', '') or '-')}
Methods: {h(', '.join(str(x) for x in methods) or '-')}

{SEP}
<b>Orderflow</b>
Bias: {h(orderflow.get('orderflow_bias', orderflow.get('bias', '-')))}
Delta: {h(orderflow.get('volume_delta', '-'))}
CVD: {h(orderflow.get('cumulative_volume_delta', '-'))}
Spread: {h(orderflow.get('spread', '-'))}
Conflict: {h(orderflow.get('orderflow_conflict', orderflow.get('conflict', False)))}

{SEP}
<b>Reason</b>
{h(getattr(row, 'reason', ''))}

{SEP}
<b>Invalid If</b>
{h(getattr(row, 'invalid_if', ''))}

{SEP}
<b>Status</b>
Broadcast: {h(getattr(row, 'broadcast_status', ''))}
Outcome: {h(getattr(row, 'outcome_status', ''))}
Review: {h(getattr(row, 'review_status', ''))}
Close Reason: {h(getattr(outcome, 'close_reason', '') if outcome else '-')}"""


def format_pending_signals_message(rows: list[Any]) -> str:
    if not rows:
        return "<b>⏳ Pending Signals</b>\n\nTidak ada signal pending."
    cards = []
    for row in rows[:20]:
        cards.append(f"#{h(getattr(row, 'id', ''))} <b>{h(getattr(row, 'symbol', ''))}</b> {h(getattr(row, 'decision', ''))}\n{format_entry_zone(getattr(row, 'entry_zone', ''))}\nSL: <code>{h(getattr(row, 'stop_loss', ''))}</code>\nTP1: <code>{h(getattr(row, 'take_profit_1', ''))}</code>\nAge: {h(age_text(getattr(row, 'timestamp', None)))}")
    return f"""<b>⏳ Pending Signals</b>

{SEP}
<b>Total:</b> {len(rows)}

{SEP}
{chr(10).join(cards)}"""


def format_outcomes_message(rows: list[Any]) -> str:
    closed = [x for x in rows if getattr(x, "result", "pending") != "pending"]
    counts = Counter(getattr(x, "result", "") for x in closed)
    latest = "\n".join(f"#{h(getattr(x, 'signal_id', ''))} {h(getattr(x, 'symbol', ''))} {h(getattr(x, 'decision', ''))} — {h(getattr(x, 'result', ''))}" for x in closed[:10]) or "Belum ada closed outcome."
    return f"""<b>📊 Recent Outcomes</b>

{SEP}
<b>Total Closed:</b> {len(closed)}

TP1: {counts.get('hit_tp1', 0)}
TP2: {counts.get('hit_tp2', 0)}
SL: {counts.get('hit_sl', 0)}
Expired: {counts.get('expired', 0)}

{SEP}
<b>Latest</b>
{latest}"""


def format_signal_result_updated_message(row: Any, outcome: Any) -> str:
    return f"""<b>✅ Signal Result Updated</b>

{SEP}
Signal: <code>#{h(getattr(row, 'id', ''))}</code>
Pair: <b>{h(getattr(row, 'symbol', ''))}</b>
Outcome: <b>{h(getattr(outcome, 'result', ''))}</b>
Close Reason: {h(getattr(outcome, 'close_reason', '') or '-')}"""


def format_performance_message(stats: dict[str, Any]) -> str:
    best_symbols = "\n".join(f"{i}. {h(x.get('name'))} — {h(x.get('winrate'))}% WR ({h(x.get('sample'))})" for i, x in enumerate(stats.get("best_symbols", [])[:5], 1)) or "-"
    worst_symbols = "\n".join(f"{i}. {h(x.get('name'))} — {h(x.get('winrate'))}% WR ({h(x.get('sample'))})" for i, x in enumerate(stats.get("worst_symbols", [])[:5], 1)) or "-"
    best_conditions = "\n".join(f"* {h(x)}" for x in stats.get("best_conditions", [])[:5]) or "-"
    worst_conditions = "\n".join(f"* {h(x)}" for x in stats.get("worst_conditions", [])[:5]) or "-"
    return f"""<b>📊 CryptoTrade Performance</b>

{SEP}
<b>Period:</b> {h(stats.get('period'))}
<b>Total Signals:</b> {h(stats.get('total_signals'))}
<b>Winrate:</b> {h(stats.get('winrate'))}%
<b>TP1 Rate:</b> {h(stats.get('tp1_rate'))}%
<b>TP2 Rate:</b> {h(stats.get('tp2_rate'))}%
<b>SL Rate:</b> {h(stats.get('sl_rate'))}%
<b>Expired:</b> {h(stats.get('expired_rate'))}%

Average RR: 1:{h(stats.get('average_rr'))}
Avg MFE: {h(stats.get('average_mfe'))}
Avg MAE: {h(stats.get('average_mae'))}
Profit Factor Est: {h(stats.get('profit_factor_estimate'))}

{SEP}
<b>Best Symbols</b>
{best_symbols}

<b>Worst Symbols</b>
{worst_symbols}

<b>Best Conditions</b>
{best_conditions}

<b>Worst Conditions</b>
{worst_conditions}

{h(stats.get('sample_warning', ''))}"""


def format_lessons_message(lessons: list[Any]) -> str:
    active = [x for x in lessons if getattr(x, "status", "") == "active"]
    suggested = [x for x in lessons if getattr(x, "status", "") == "suggested"]
    rejected = [x for x in lessons if getattr(x, "status", "") == "rejected"]
    active_rows = "\n".join(f"{i}. {h(x.lesson_text)} ({h(x.confidence_adjustment)} confidence)" for i, x in enumerate(active[:10], 1)) or "-"
    suggested_rows = "\n".join(f"{i}. [ID {h(x.id)}] {h(x.lesson_text)}" for i, x in enumerate(suggested[:10], 1)) or "-"
    return f"""<b>🧠 Strategy Lessons</b>

{SEP}
Active Lessons: {len(active)}
Suggested Lessons: {len(suggested)}
Rejected Lessons: {len(rejected)}

{SEP}
<b>Active</b>
{active_rows}

<b>Suggested</b>
{suggested_rows}

Commands: <code>/lesson_detail ID</code>, <code>/approve_lesson ID</code>, <code>/reject_lesson ID</code>, <code>/disable_lesson ID</code>"""


def format_lesson_detail_message(lesson: Any, review: Any | None = None) -> str:
    return f"""<b>🧠 Lesson Detail</b>

{SEP}
ID: {h(getattr(lesson, 'id', ''))}
Status: {h(getattr(lesson, 'status', ''))}
Type: {h(getattr(lesson, 'lesson_type', ''))}
Adjustment: {h(getattr(lesson, 'confidence_adjustment', 0))}

{SEP}
<b>Lesson</b>
{h(getattr(lesson, 'lesson_text', ''))}

<b>Evidence</b>
Source Signal: #{h(getattr(lesson, 'source_signal_id', 0))}
Result Quality: {h(getattr(review, 'result_quality', '-') if review else '-')}
Reason: {h(getattr(review, 'main_failure_reason', '-') if review else '-')}

<b>Suggested Rule</b>
{h(getattr(lesson, 'filter_rule_json', '{}'))}"""


def format_learning_status_message(data: dict[str, Any]) -> str:
    return f"""<b>🧠 Learning Status</b>

{SEP}
Signal Learning: {status_icon(data.get('enable_signal_learning'))}
Auto Review: {status_icon(data.get('enable_auto_review'))}
Adaptive Scoring: {status_icon(data.get('enable_adaptive_scoring'))}
Admin Approval Required: {h('YES' if data.get('require_admin_approval_for_lessons') else 'NO')}

{SEP}
Pending Outcomes: {h(data.get('pending_outcomes'))}
Pending Reviews: {h(data.get('pending_reviews'))}
Active Lessons: {h(data.get('active_lessons'))}
Suggested Lessons: {h(data.get('suggested_lessons'))}

Lookback: {h(data.get('lookback_days'))} days
Max Lessons in Prompt: {h(data.get('max_lessons'))}"""


def format_signal_review_message(review: Any | None, error: str | None = None) -> str:
    if error:
        return format_error_message("Signal Review Failed", error, "Coba ulangi /review_signal ID nanti.")
    return f"""<b>🧠 Signal Review</b>

{SEP}
Signal: #{h(getattr(review, 'signal_id', ''))}
Quality: <b>{h(getattr(review, 'result_quality', ''))}</b>
Main Reason: {h(getattr(review, 'main_failure_reason', ''))}

{SEP}
<b>Future Lesson</b>
{h(getattr(review, 'future_lesson', ''))}"""


def format_lesson_approved_message(lesson: Any) -> str:
    return f"<b>✅ Lesson Approved</b>\n\nLesson <code>#{h(getattr(lesson, 'id', ''))}</code> sekarang active."


def format_lesson_rejected_message(lesson: Any) -> str:
    return f"<b>🟡 Lesson Rejected</b>\n\nLesson <code>#{h(getattr(lesson, 'id', ''))}</code> ditolak."


def format_lesson_disabled_message(lesson: Any) -> str:
    return f"<b>⏸ Lesson Disabled</b>\n\nLesson <code>#{h(getattr(lesson, 'id', ''))}</code> dinonaktifkan."


def age_text(value: Any) -> str:
    if not isinstance(value, datetime):
        return "-"
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    minutes = max(0, int((datetime.now(timezone.utc) - dt).total_seconds() // 60))
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m" if hours else f"{mins}m"


def signal_outcome(row: Any) -> str:
    current_price = parse_float(getattr(row, "current_price", 0))
    if current_price <= 0:
        return getattr(row, "status", "pending") or "pending"
    decision = str(getattr(row, "decision", "")).upper()
    stop_loss = parse_float(getattr(row, "stop_loss", 0))
    tp1 = parse_float(getattr(row, "take_profit_1", 0))
    tp2 = parse_float(getattr(row, "take_profit_2", 0))
    if decision == "BUY":
        if stop_loss and current_price <= stop_loss:
            return "LOSS (SL hit)"
        if tp2 and current_price >= tp2:
            return "WIN (TP2 hit)"
        if tp1 and current_price >= tp1:
            return "WIN (TP1 hit)"
    if decision == "SELL":
        if stop_loss and current_price >= stop_loss:
            return "LOSS (SL hit)"
        if tp2 and current_price <= tp2:
            return "WIN (TP2 hit)"
        if tp1 and current_price <= tp1:
            return "WIN (TP1 hit)"
    if signal_expired(row):
        return "EXPIRED"
    return getattr(row, "status", "pending") or "pending"


def signal_validity(row: Any, outcome: str) -> str:
    timestamp = getattr(row, "timestamp", None)
    if not isinstance(timestamp, datetime):
        return "-"
    valid_until = timestamp + timedelta(hours=4)
    suffix = ""
    if outcome == "EXPIRED" or datetime.now(timezone.utc) > valid_until.replace(tzinfo=valid_until.tzinfo or timezone.utc):
        suffix = " (expired)"
    return f"until {time_wib(valid_until)}{suffix}"


def signal_expired(row: Any) -> bool:
    timestamp = getattr(row, "timestamp", None)
    if not isinstance(timestamp, datetime):
        return False
    valid_until = timestamp + timedelta(hours=4)
    if not valid_until.tzinfo:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > valid_until


def parse_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
