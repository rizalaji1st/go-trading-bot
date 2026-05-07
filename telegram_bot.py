import asyncio
import time
from datetime import datetime, timezone
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from loguru import logger

from config import config
from ai import analyze_stock, chat_with_ai, daily_market_summary
from db import get_session, Position, TradeLog, DailySummary
from risk import risk_manager

WATCHLIST = [
    "BBCA", "BBRI", "TLKM", "ASII", "UNVR",
    "BMRI", "BBNI", "ICBP", "HMSP", "INDF",
    "ADRO", "ANTM", "PGAS", "GOTO", "BRIS",
]

OWNER_ID = int(config.TELEGRAM_CHAT_ID) if config.TELEGRAM_CHAT_ID else 0

# ─── Rate limiter ────────────────────────────────────────────────────

RATE_WINDOW = 3600
RATE_MAX = 5
_usage = defaultdict(list)
_total_usage = 0


def _rate_check(user_id: int) -> tuple[bool, int]:
    now = time.time()
    _usage[user_id] = [t for t in _usage[user_id] if now - t < RATE_WINDOW]
    used = len(_usage[user_id])
    if used >= RATE_MAX:
        return False, 0
    _usage[user_id].append(now)
    global _total_usage
    _total_usage += 1
    remaining = RATE_MAX - used - 1
    return True, remaining


def _usage_pct() -> float:
    return _total_usage / 3450 * 100


def _rate_limit(cmd: str = "cmd"):
    def deco(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            uid = update.effective_user.id
            allowed, rem = _rate_check(uid)
            if not allowed:
                await update.message.reply_text(
                    f"⏳ Limit {RATE_MAX} req/jam. Coba lagi nanti.\n"
                    f"⏳ <i>Rate limit: {RATE_MAX} requests per hour</i>",
                    parse_mode=ParseMode.HTML,
                )
                return
            return await func(update, context)
        return wrapper
    return deco


def _log_cmd(update: Update, cmd: str, details: str = ""):
    uid = update.effective_user.id
    uname = update.effective_user.username or str(uid)
    logger.info(f"[{uname}@{uid}] /{cmd} {details}")


# ─── Caching ─────────────────────────────────────────────────────────

_cache = {}
CACHE_TTL = 3600


def _cache_get(key: str):
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return val
    return None


def _cache_set(key: str, val):
    _cache[key] = (time.time(), val)


# ─── Helpers ─────────────────────────────────────────────────────────

def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _rp(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"Rp{value/1_000_000_000:+.2f}B"
    elif abs(value) >= 1_000_000:
        return f"Rp{value/1_000_000:.2f}M"
    return f"Rp{value:,.0f}"


def _signal_icon(signal: str) -> str:
    return {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(signal, "⚪")


def _bar(value: float, max_val: float = 1.0, width: int = 10) -> str:
    pct = min(abs(value) / max(max_val, 0.01), 1.0)
    filled = int(pct * width)
    return "█" * filled + "░" * (width - filled)


def _is_owner(update: Update) -> bool:
    return update.effective_user.id == OWNER_ID


# ─── /start ──────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_cmd(update, "start")
    limits = f"Maks {RATE_MAX} req/jam/user • Cache {CACHE_TTL//60}m"
    msg = (
        "🤖 <b>Trading Bot</b>\n"
        f"<i>{limits}</i>\n\n"
        "┌─────────────────────────┐\n"
        "│  /status      Posisi & PnL     │\n"
        "│  /analyze   Analisis saham  │\n"
        "│  /list            Watchlist          │\n"
        "│  /risk            Risk manager    │\n"
        "│  /ai               Tanya AI           │\n"
        "│  /admin        Admin panel       │\n"
        "└─────────────────────────┘"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# ─── /status ─────────────────────────────────────────────────────────

@_rate_limit("status")
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_cmd(update, "status")
    session = get_session()
    try:
        positions = session.query(Position).all()
        risk = risk_manager.get_risk_summary()

        if positions:
            lines = ["<b>📊 Posisi Aktif</b>\n"]
            for p in positions:
                price = p.current_price or p.avg_price
                pnl = p.quantity * (price - p.avg_price)
                pnl_pct = (price - p.avg_price) / p.avg_price
                icon = "🔺" if pnl > 0 else "🔻" if pnl < 0 else "➖"
                lines.append(
                    f"{icon} <code>{_escape_html(p.symbol)}</code> "
                    f"{p.quantity} lot @ {_rp(p.avg_price)}\n"
                    f"     PnL: {_rp(pnl)} ({pnl_pct:+.1%})"
                )
            msg_positions = "\n\n".join(lines)
        else:
            msg_positions = "<b>📊 Posisi</b>\nTidak ada posisi aktif."

        total_return = risk["total_return"]
        ret_icon = "🔺" if total_return > 0 else "🔻" if total_return < 0 else "➖"

        msg_risk = (
            f"\n\n<b>💰 Modal</b>\n"
            f"    {_rp(risk['current_capital'])} {ret_icon} {total_return:+.2%}\n"
            f"\n<b>📅 Hari Ini</b>\n"
            f"    PnL: {_rp(risk['daily_pnl'])} ({risk['daily_pnl_percent']:+.2%})\n"
            f"    DD:  {risk['max_drawdown']:.1%}  {_bar(risk['max_drawdown'], 1.0, 6)}"
        )

        await update.message.reply_text(
            msg_positions + msg_risk, parse_mode=ParseMode.HTML
        )
    finally:
        session.close()


# ─── /analyze ────────────────────────────────────────────────────────

def _format_analysis(result: dict, symbol: str) -> str:
    signal = result.get("signal", "HOLD")
    conf = result.get("confidence", 0)
    target = result.get("price_target")
    stop = result.get("stop_loss")
    rr = result.get("risk_reward_ratio", 0)
    reason = result.get("reason", "N/A")

    return (
        f"{_signal_icon(signal)} <b>{_escape_html(symbol)} — {signal}</b>\n"
        f"<pre>Confidence : {conf:.0%}</pre>\n"
        f"<pre>Target     : {_rp(target) if target else 'N/A'}</pre>\n"
        f"<pre>Stop Loss  : {_rp(stop) if stop else 'N/A'}</pre>\n"
        f"<pre>R/R Ratio  : {rr if rr else 'N/A'}</pre>\n"
        f"\n{_escape_html(reason[:300])}"
    )


@_rate_limit("analyze")
async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚡ /analyze BBCA")
        return

    symbol = context.args[0].upper()
    _log_cmd(update, "analyze", symbol)

    cached = _cache_get(f"analyze:{symbol}")
    if cached:
        out = _format_analysis(cached, symbol)
        out += f"\n\n<i>↻ Dari cache ({CACHE_TTL//60}m TTL)</i>"
        await update.message.reply_text(out, parse_mode=ParseMode.HTML)
        return

    msg_wait = await update.message.reply_text(f"🔍 {symbol}...")
    result = await analyze_stock(symbol)
    _cache_set(f"analyze:{symbol}", result)

    out = _format_analysis(result, symbol)
    await msg_wait.edit_text(out, parse_mode=ParseMode.HTML)


# ─── /list ───────────────────────────────────────────────────────────

@_rate_limit("list")
async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_cmd(update, "list")
    msg = await update.message.reply_text("🔍 Menganalisis...")

    cached = _cache_get("list:top5")
    if cached:
        out = cached + f"\n\n<i>↻ Cache ({CACHE_TTL//60}m TTL)</i>"
        await msg.edit_text(out, parse_mode=ParseMode.HTML)
        return

    results = []
    for s in WATCHLIST[:5]:
        cr = _cache_get(f"analyze:{s}")
        if cr:
            results.append(cr)
        else:
            r = await analyze_stock(s)
            _cache_set(f"analyze:{s}", r)
            results.append(r)

    lines = ["<b>📋 Sinyal Hari Ini</b>\n"]
    for r in results:
        sym = r.get("symbol", "?")
        sig = r.get("signal", "HOLD")
        conf = r.get("confidence", 0)
        reason = (r.get("reason", "") or "")[:60]
        lines.append(
            f"{_signal_icon(sig)} <code>{_escape_html(sym)}</code> "
            f"<b>{sig}</b> {conf:.0%}"
        )
        if reason:
            lines.append(f"     {_escape_html(reason)}")

    out = "\n".join(lines)
    out += f"\n\n<i>5 dari {len(WATCHLIST)} saham</i>"
    _cache_set("list:top5", out)

    await msg.edit_text(out, parse_mode=ParseMode.HTML)


# ─── /risk ───────────────────────────────────────────────────────────

@_rate_limit("risk")
async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_cmd(update, "risk")
    s = risk_manager.get_risk_summary()
    ret = s["total_return"]
    icon = "🟢" if ret > 0 else "🔴" if ret < 0 else "⚪"

    msg = (
        "<b>⚠️ Risk Manager</b>\n"
        f"<pre>Modal      {_rp(s['current_capital'])}</pre>\n"
        f"<pre>Return     {icon} {ret:+.2%}</pre>\n"
        f"<pre>PnL Hari Ini {_rp(s['daily_pnl'])} ({s['daily_pnl_percent']:+.2%})</pre>\n"
        f"<pre>Max DD     {s['max_drawdown']:.1%}</pre>\n"
        f"<pre>Batas Posisi  {s['max_position_size']:.0%} / trade</pre>\n"
        f"<pre>Batas Loss Harian {s['max_daily_loss']:.0%}</pre>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# ─── /ai ─────────────────────────────────────────────────────────────

@_rate_limit("ai")
async def chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚡ /ai Apakah BBCA layak beli hari ini?")
        return

    question = " ".join(context.args)
    _log_cmd(update, "ai", question[:50])

    cached = _cache_get(f"ai:{question}")
    if cached:
        await update.message.reply_text(
            cached + f"\n\n<i>↻ Cache ({CACHE_TTL//60}m TTL)</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    msg_wait = await update.message.reply_text("...")
    response = await chat_with_ai(question)
    safe = _escape_html(response[:3800])
    _cache_set(f"ai:{question}", safe)

    await msg_wait.edit_text(safe, parse_mode=ParseMode.HTML)


# ─── /admin ──────────────────────────────────────────────────────────

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_cmd(update, "admin")
    if not _is_owner(update):
        await update.message.reply_text("⛔ Admin only.", parse_mode=ParseMode.HTML)
        return

    if not context.args:
        await update.message.reply_text(
            "<b>🔐 Admin Panel</b>\n"
            "/admin stats   — Usage + cache stats\n"
            "/admin cache   — Clear all cache\n"
            "/admin users   — Active users",
            parse_mode=ParseMode.HTML,
        )
        return

    sub = context.args[0].lower()

    if sub == "stats":
        now = time.time()
        active_users = sum(1 for v in _usage.values() if v)
        total_req = sum(len([t for t in v if now - t < RATE_WINDOW]) for v in _usage.values())
        cache_count = len(_cache)
        usage_pct = _usage_pct()

        alert = ""
        if usage_pct > 80:
            alert = "\n⚠️ <b>WARNING: Usage >80%!</b>"

        await update.message.reply_text(
            "<b>📊 Bot Stats</b>\n"
            f"<pre>Total req     {_total_usage}</pre>\n"
            f"<pre>Active users  {active_users}</pre>\n"
            f"<pre>Req this hour {total_req}</pre>\n"
            f"<pre>Cache entries {cache_count}</pre>\n"
            f"<pre>Quota usage   {usage_pct:.1f}%</pre>"
            + alert,
            parse_mode=ParseMode.HTML,
        )

    elif sub == "cache":
        _cache.clear()
        await update.message.reply_text("✅ Cache cleared.", parse_mode=ParseMode.HTML)

    elif sub == "users":
        now = time.time()
        users = []
        for uid, times in _usage.items():
            recent = len([t for t in times if now - t < RATE_WINDOW])
            if recent > 0:
                users.append(f"<code>{uid}</code>: {recent} req")

        if users:
            out = "<b>👥 Active Users (this hour)</b>\n" + "\n".join(users[:20])
            if len(users) > 20:
                out += f"\n<i>...and {len(users)-20} more</i>"
        else:
            out = "<b>👥 Active Users</b>\nNo activity this hour."

        await update.message.reply_text(out, parse_mode=ParseMode.HTML)

    else:
        await update.message.reply_text("⚡ /admin stats | cache | users", parse_mode=ParseMode.HTML)


# ─── /help ───────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


# ─── main ────────────────────────────────────────────────────────────

def run_telegram_bot():
    if not config.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram bot disabled.")
        return

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("watchlist", list_cmd))
    app.add_handler(CommandHandler("risk", risk_cmd))
    app.add_handler(CommandHandler("ai", chat_cmd))
    app.add_handler(CommandHandler("chat", chat_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))

    logger.info("Telegram bot started — public mode, rate limit: {}/h/user, cache: {}m", RATE_MAX, CACHE_TTL // 60)
    app.run_polling()


if __name__ == "__main__":
    import sys

    logger.remove()
    logger.add(sys.stdout, level="INFO")
    run_telegram_bot()
