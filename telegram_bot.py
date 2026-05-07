import asyncio
from datetime import datetime, timezone
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


# ─── /start ────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 <b>Trading Bot</b>\n\n"
        "┌─────────────────────┐\n"
        "│ <b>Perintah</b>                            │\n"
        "├─────────────────────┤\n"
        "│ /status   Cek posisi           │\n"
        "│ /analyze  Analisis saham       │\n"
        "│ /list        Lihat watchlist      │\n"
        "│ /risk        Cek risiko              │\n"
        "│ /ai           Tanya AI langsung  │\n"
        "│ /help        Bantuan                  │\n"
        "└─────────────────────┘"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# ─── /status ────────────────────────────────────────────────────────

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session()
    try:
        positions = session.query(Position).all()
        risk = risk_manager.get_risk_summary()

        if positions:
            lines = ["<b>📊 Posisi Aktif</b>\n"]
            for p in positions:
                price = p.current_price or p.avg_price
                value = p.quantity * price
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
            f"    DD:  {risk['max_drawdown']:.1%}  {_bar(risk['max_drawdown'], 1.0, 6)}\n"
        )

        await update.message.reply_text(msg_positions + msg_risk, parse_mode=ParseMode.HTML)
    finally:
        session.close()


# ─── /analyze ───────────────────────────────────────────────────────

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚡ /analyze BBCA")
        return

    symbol = context.args[0].upper()
    msg_wait = await update.message.reply_text(f"🔍 {symbol}...")

    result = await analyze_stock(symbol)
    signal = result.get("signal", "HOLD")
    conf = result.get("confidence", 0)
    target = result.get("price_target")
    stop = result.get("stop_loss")
    rr = result.get("risk_reward_ratio", 0)
    reason = result.get("reason", "N/A")

    out = (
        f"{_signal_icon(signal)} <b>{_escape_html(symbol)} — {signal}</b>\n"
        f"<pre>Confidence : {conf:.0%}</pre>\n"
        f"<pre>Target     : {_rp(target) if target else 'N/A'}</pre>\n"
        f"<pre>Stop Loss  : {_rp(stop) if stop else 'N/A'}</pre>\n"
        f"<pre>R/R Ratio  : {rr if rr else 'N/A'}</pre>\n"
        f"\n{_escape_html(reason[:300])}"
    )

    await msg_wait.edit_text(out, parse_mode=ParseMode.HTML)


# ─── /list ──────────────────────────────────────────────────────────

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Menganalisis...")

    results = []
    batch = WATCHLIST[:5]
    for s in batch:
        r = await analyze_stock(s)
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
    out += f"\n\n<i>5 dari {len(WATCHLIST)} saham. Ulangi untuk refresh.</i>"

    await msg.edit_text(out, parse_mode=ParseMode.HTML)


# ─── /risk ──────────────────────────────────────────────────────────

async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


# ─── /ai ────────────────────────────────────────────────────────────

async def chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚡ /ai Apakah BBCA layak beli hari ini?")
        return

    question = " ".join(context.args)
    msg_wait = await update.message.reply_text("...")

    response = await chat_with_ai(question)
    safe = _escape_html(response[:3800])

    await msg_wait.edit_text(safe, parse_mode=ParseMode.HTML)


# ─── /help ──────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


# ─── main ───────────────────────────────────────────────────────────

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

    logger.info("Telegram bot started")
    app.run_polling()


if __name__ == "__main__":
    import sys
    logger.remove()
    logger.add(sys.stdout, level="INFO")
    run_telegram_bot()
