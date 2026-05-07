import asyncio
import signal
from datetime import datetime, timezone
from loguru import logger

from config import config
from db import init_db, get_session, Signal as DbSignal, SignalType, Order, OrderStatus, OrderSide
from ai import analyze_stock
from risk import risk_manager
from broker import broker

WATCHLIST = [
    "BBCA", "BBRI", "TLKM", "ASII", "UNVR",
    "BMRI", "BBNI", "ICBP", "HMSP", "INDF",
    "ADRO", "ANTM", "PGAS", "GOTO", "BRIS",
]

_running = True


async def morning_analysis():
    logger.info("=== Morning Market Analysis ===")
    for symbol in WATCHLIST[:5]:
        result = await analyze_stock(symbol)
        signal_type = result.get("signal", "HOLD")
        session = get_session()
        try:
            db_signal = DbSignal(
                symbol=symbol, signal=SignalType(signal_type) if signal_type in ("BUY", "SELL", "HOLD") else SignalType.HOLD,
                price=result.get("price_target"), confidence=result.get("confidence", 0), reason=result.get("reason", ""),
            )
            session.add(db_signal)
            session.commit()
            if signal_type == "BUY":
                ok, msg = risk_manager.check_order(symbol, OrderSide.BUY, 10, result.get("price_target", 0))
                logger.info(f"SIGNAL BUY: {symbol} — {msg}" if ok else f"BUY BLOCKED: {symbol} — {msg}")
        finally:
            session.close()


async def market_check():
    logger.info("=== Market Check ===")
    for symbol in WATCHLIST[:5]:
        result = await analyze_stock(symbol)
        logger.info(f"{symbol}: {result.get('signal')} (conf: {result.get('confidence', 0):.0%})")


async def closing_summary():
    logger.info("=== Closing Summary ===")
    session = get_session()
    try:
        signals = session.query(DbSignal).filter(
            DbSignal.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        ).all()
        for s in signals:
            logger.info(f"{s.symbol}: {s.signal.value} @ {s.price} (conf: {s.confidence:.0%})")
    finally:
        session.close()


async def _sleep_or_stop(seconds: float) -> bool:
    for _ in range(int(seconds / 2)):
        if not _running:
            return True
        await asyncio.sleep(2)
    if not _running:
        return True
    return False


async def scheduler_loop():
    global _running
    logger.info("Scheduler started. Watchlist: {}", WATCHLIST)

    market_open = datetime.now(timezone.utc).replace(hour=1, minute=0, second=0, microsecond=0)
    market_close = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)

    last_morning_run = None
    last_check_run = None

    while _running:
        now = datetime.now(timezone.utc)

        if last_morning_run is None or (now - last_morning_run).total_seconds() > 3600:
            if market_open.hour <= now.hour < market_close.hour:
                await morning_analysis()
                last_morning_run = now

        if last_check_run is None or (now - last_check_run).total_seconds() > 7200:
            if market_open.hour <= now.hour < market_close.hour:
                await market_check()
                last_check_run = now

        if now.hour == market_close.hour and 0 <= now.minute < 10:
            await closing_summary()
            if await _sleep_or_stop(600):
                break

        if await _sleep_or_stop(30):
            break

    logger.info("Scheduler loop ended")


def _shutdown(signum, frame):
    global _running
    logger.info("Shutting down scheduler...")
    _running = False


def run_scheduler():
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    asyncio.run(scheduler_loop())


if __name__ == "__main__":
    init_db()
    broker.connect()
    try:
        run_scheduler()
    finally:
        broker.disconnect()
        logger.info("Scheduler shutdown complete")
