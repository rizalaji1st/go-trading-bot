# go-trading-bot

Automated stock trading bot for Indonesian market (IDX/BEI) with AI-powered
analysis, Telegram monitoring, and Hermes Agent integration.

## Architecture

```
scheduler.py ──▶ ai.py (OpenCode Go) ──▶ Telegram alerts
    │
    ├── strategy.py (EMA crossover, RSI)
    ├── risk.py (position sizing, drawdown, daily loss limit)
    ├── broker.py (paper/live trading)
    └── db.py (SQLite: orders, positions, signals, trade logs)
```

## Features

- **AI Analysis** — DeepSeek V4 Pro via OpenCode Go API for technical analysis
- **Telegram Bot** — Real-time monitoring and control via Telegram
  - `/status` — portfolio positions and P&L
  - `/analyze BBCA` — AI analysis with BUY/SELL/HOLD signal
  - `/list` — watchlist signal summary
  - `/risk` — risk manager status
  - `/ai <question>` — ask AI any trading question
- **Auto Scheduler** — daily morning analysis (08:00 WIB), periodic market
  checks, closing summary (15:00 WIB)
- **Risk Manager** — max position size, daily loss limit, drawdown protection
- **Paper Trading** — test strategies safely before live trading
- **Hermes Agent** — AI agent with persistent memory, skills, and cron scheduler

## Watchlist

BBCA, BBRI, TLKM, ASII, UNVR, BMRI, BBNI, ICBP, HMSP, INDF, ADRO, ANTM, PGAS, GOTO, BRIS

## Setup

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys (see .env.example)

# Deploy as services
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-bot trading-telegram
```

## Requirements

- Python 3.11+
- OpenCode Go API key ([opencode.ai](https://opencode.ai/go))
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Ubuntu 24.04 (or any Linux with systemd)

## Environment Variables

| Key | Description |
|---|---|
| `OPENCODE_GO_API_KEY` | OpenCode Go subscription key |
| `OPENCODE_GO_MODEL` | Model ID (default: `deepseek-v4-pro`) |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your numeric Telegram user ID |
| `BROKER_API_KEY` | Broker API key (empty = paper trading) |
| `INITIAL_CAPITAL` | Starting capital (default: 100000000) |

## Roadmap

- [x] AI analysis engine (OpenCode Go / DeepSeek V4 Pro)
- [x] Telegram bot with 7 commands
- [x] 24/7 scheduler with morning/periodic/closing tasks
- [x] Risk manager (position sizing, drawdown limits)
- [x] Hermes Agent integration (v0.12.0)
- [x] Hermes cron jobs for automated analysis delivery
- [ ] Data pipeline — yfinance + SQLite historical OHLCV
- [ ] Backtesting — vectorbt walk-forward validation
- [ ] IDX-aware risk rules (auto-rejection, odd lots, trading halts)
- [ ] Hybrid execution — Telegram manual order approval
- [ ] Multi-strategy engine (MACD, Bollinger Bands, volume breakout)
- [ ] Broker API integration (Sinarmas / Mirae / Interactive Brokers)

See [docs/PHASE1_PLAN.md](docs/PHASE1_PLAN.md) for the detailed Phase 1 plan.

## Project Structure

```
trading-bot/
├── ai.py               # OpenCode Go API client
├── broker.py           # Abstract broker (paper trading by default)
├── config.py           # .env loader
├── db.py               # SQLAlchemy ORM (SQLite)
├── main.py             # Combined entry point
├── risk.py             # Risk manager
├── scheduler.py        # asyncio cron loop
├── strategy.py         # Trading strategies (EMA, RSI)
├── telegram_bot.py     # Telegram bot commands
├── docs/               # Planning documentation
│   └── PHASE1_PLAN.md
├── data/               # SQLite database
├── logs/               # Rotating log files
└── AGENTS.md           # Developer guide
```

## Development

See [AGENTS.md](AGENTS.md) for code conventions, testing instructions, and
architecture details.

## License

MIT
