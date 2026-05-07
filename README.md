# Go Trading Bot

Automated stock trading bot for Indonesian market (IDX/BEI) with AI analysis, Telegram monitoring, and Hermes Agent integration.

## Features

- **AI Analysis** — DeepSeek V4 Pro via OpenCode Go API for technical & fundamental analysis
- **Telegram Bot** — Real-time monitoring with /status, /analyze, /watchlist, /risk, /chat commands
- **Scheduler** — Auto morning analysis (08:00 WIB), periodic market checks, closing summary (15:00 WIB)
- **Risk Manager** — Max position size, daily loss limit, drawdown protection
- **Paper Trading** — Test strategies safely before live trading
- **Hermes Agent** — AI agent with persistent memory, skills, and multi-platform support

## Setup

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
python scheduler.py        # Background scheduler
python telegram_bot.py     # Telegram bot
```

## Architecture

```
scheduler.py ──▶ ai.py (OpenCode Go) ──▶ Telegram alerts
    │
    ├── strategy.py (EMA crossover, RSI)
    ├── risk.py (position size, drawdown)
    ├── broker.py (paper/live trading)
    └── db.py (SQLite)
```

## Watchlist

BBCA, BBRI, TLKM, ASII, UNVR, BMRI, BBNI, ICBP, HMSP, INDF, ADRO, ANTM, PGAS, GOTO, BRIS

## Requirements

- Python 3.11+
- OpenCode Go API key (opencode.ai)
- Telegram Bot Token

## License

MIT
