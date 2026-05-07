import asyncio
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
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


def format_rupiah(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"Rp {value/1_000_000_000:.2f}B"
    elif abs(value) >= 1_000_000:
        return f"Rp {value/1_000_000:.2f}M"
    return f"Rp {value:,.0f}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 *Trading Bot Assistant*\n\n"
        "Perintah yang tersedia:\n"
        "/status — Cek posisi & PnL\n"
        "/analyze <SYMBOL> — Analisis saham\n"
        "/watchlist — Cek watchlist\n"
        "/risk — Cek manajemen risiko\n"
        "/summary — Ringkasan pasar harian\n"
        "/chat <pertanyaan> — Tanya AI\n"
        "/help — Bantuan"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session()
    try:
        positions = session.query(Position).all()
        risk_summary = risk_manager.get_risk_summary()

        msg = "*📊 Portfolio Status*\n\n"

        if positions:
            for p in positions:
                value = p.quantity * (p.current_price or p.avg_price)
                pnl = p.quantity * ((p.current_price or p.avg_price) - p.avg_price)
                pnl_pct = ((p.current_price or p.avg_price) - p.avg_price) / p.avg_price * 100
                msg += (
                    f"*{p.symbol}*: {p.quantity} lot @ {format_rupiah(p.avg_price)}\n"
                    f"  Value: {format_rupiah(value)} | PnL: {format_rupiah(pnl)} ({pnl_pct:+.1f}%)\n\n"
                )
        else:
            msg += "Tidak ada posisi aktif.\n\n"

        msg += (
            "— — — — — — — — — —\n"
            f"*Capital*: {format_rupiah(risk_summary['current_capital'])}\n"
            f"*Daily PnL*: {format_rupiah(risk_summary['daily_pnl'])} ({risk_summary['daily_pnl_percent']:+.2%})\n"
            f"*Max DD*: {risk_summary['max_drawdown']:.2%}\n"
        )

        await update.message.reply_text(msg, parse_mode="Markdown")
    finally:
        session.close()


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Gunakan: /analyze <SYMBOL>\nContoh: /analyze BBCA")
        return

    symbol = context.args[0].upper()
    await update.message.reply_text(f"🔍 Menganalisis {symbol}...")

    result = await analyze_stock(symbol)

    msg = (
        f"*📈 {result.get('symbol', symbol)}*\n\n"
        f"*Signal*: {result.get('signal', 'HOLD')}\n"
        f"*Confidence*: {result.get('confidence', 0):.0%}\n"
        f"*Target Price*: {format_rupiah(result.get('price_target', 0)) if result.get('price_target') else 'N/A'}\n"
        f"*Stop Loss*: {format_rupiah(result.get('stop_loss', 0)) if result.get('stop_loss') else 'N/A'}\n"
        f"*R/R Ratio*: {result.get('risk_reward_ratio', 'N/A')}\n\n"
        f"*Alasan*: {result.get('reason', 'N/A')}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Menganalisis watchlist...")

    tasks = [analyze_stock(s) for s in WATCHLIST]
    results = await asyncio.gather(*tasks)

    msg = "*📋 Watchlist Analysis*\n\n"
    for r in results:
        signal_emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(r.get("signal", "HOLD"), "⚪")
        msg += f"{signal_emoji} *{r.get('symbol')}*: {r.get('signal')} ({r.get('confidence', 0):.0%})\n"
        if r.get("reason"):
            msg += f"  _{r['reason'][:80]}_\n"

    await update.message.reply_text(msg, parse_mode="Markdown")


async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary = risk_manager.get_risk_summary()

    total_return = summary["total_return"]
    emoji = "🟢" if total_return > 0 else "🔴" if total_return < 0 else "⚪"

    msg = (
        "*⚠️ Risk Management*\n\n"
        f"Capital: {format_rupiah(summary['current_capital'])}\n"
        f"Return: {emoji} {total_return:+.2%}\n"
        f"Daily PnL: {format_rupiah(summary['daily_pnl'])} ({summary['daily_pnl_percent']:+.2%})\n"
        f"Max Drawdown: {summary['max_drawdown']:.2%}\n"
        f"Position Limit: {summary['max_position_size']:.0%}\n"
        f"Daily Loss Limit: {summary['max_daily_loss']:.0%}\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Membuat ringkasan pasar...")
    result = await daily_market_summary(WATCHLIST)
    await update.message.reply_text(result)


async def chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Gunakan: /chat <pertanyaan>\nContoh: /chat Apakah IHSG sedang bearish?")
        return

    question = " ".join(context.args)
    await update.message.reply_text("🤔 Berpikir...")

    response = await chat_with_ai(question)
    await update.message.reply_text(response)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


def run_telegram_bot():
    if not config.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram bot disabled.")
        return

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("watchlist", watchlist_cmd))
    app.add_handler(CommandHandler("risk", risk_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("chat", chat_cmd))

    logger.info("Telegram bot started")
    app.run_polling()


if __name__ == "__main__":
    from loguru import logger
    import sys
    logger.remove()
    logger.add(sys.stdout, level="INFO")
    run_telegram_bot()
