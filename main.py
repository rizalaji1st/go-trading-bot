import sys
import asyncio
from loguru import logger

from config import config
from db import init_db

logger.remove()
logger.add(
    config.LOG_FILE,
    level=config.LOG_LEVEL,
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
)
logger.add(
    sys.stdout,
    level=config.LOG_LEVEL,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)


async def run_all():
    logger.info("=" * 50)
    logger.info("Trading Bot Starting...")
    logger.info(f"Model: {config.OPENCODE_GO_MODEL}")
    logger.info(f"Database: {config.DATABASE_URL}")
    logger.info("=" * 50)

    init_db()
    logger.info("Database initialized")

    from scheduler import run_scheduler
    from telegram_bot import run_telegram_bot

    loop = asyncio.get_event_loop()

    telegram_task = loop.run_in_executor(None, run_telegram_bot)

    try:
        await run_scheduler()
    finally:
        logger.info("Shutting down...")


def main():
    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
