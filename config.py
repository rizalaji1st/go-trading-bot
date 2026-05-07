import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")


class Config:
    OPENCODE_GO_API_KEY = os.getenv("OPENCODE_GO_API_KEY", "")
    OPENCODE_GO_BASE_URL = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")
    OPENCODE_GO_MODEL = os.getenv("OPENCODE_GO_MODEL", "deepseek-v4-pro")

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    BROKER_API_KEY = os.getenv("BROKER_API_KEY", "")
    BROKER_API_SECRET = os.getenv("BROKER_API_SECRET", "")
    BROKER_BASE_URL = os.getenv("BROKER_BASE_URL", "")

    MAX_POSITION_SIZE = float(os.getenv("MAX_POSITION_SIZE", "0.1"))
    MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.05"))
    MAX_DRAWDOWN = float(os.getenv("MAX_DRAWDOWN", "0.15"))
    INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "100000000"))

    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/data/trading.db")

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", f"{BASE_DIR}/logs/trading.log")


config = Config()
