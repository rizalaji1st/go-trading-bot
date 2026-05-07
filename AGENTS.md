# go-trading-bot — Development Guide

Automated stock trading bot for IDX/BEI with AI analysis, Telegram monitoring,
and Hermes Agent integration. Runs on Ubuntu 24.04 VPS (2GB RAM, 40GB disk).

## Quick Start

```bash
source venv/bin/activate
cp .env.example .env   # fill API keys
python scheduler.py    # background scheduler (cron loop)
python telegram_bot.py # Telegram bot (separate process)
```

## Project Structure

```
trading-bot/
├── config.py           # load .env → Config singleton
├── db.py               # SQLAlchemy ORM: Order, Position, Signal, TradeLog, DailySummary
├── ai.py               # OpenCode Go API client (deepseek-v4-pro, retry logic)
├── broker.py           # Abstract broker connector (paper trading by default)
├── strategy.py         # EMA crossover + RSI strategies, StrategyResult dataclass
├── risk.py             # RiskManager: position sizing, drawdown, daily loss limits
├── scheduler.py        # asyncio cron loop: morning analysis, market check, closing summary
├── telegram_bot.py     # python-telegram-bot: /status /analyze /list /risk /ai
├── main.py             # Combined entry point (scheduler + telegram in one process)
├── data/trading.db     # SQLite database (auto-created)
├── logs/trading.log    # Rotating log (10MB, 7-day retention)
├── .env                # API keys (NEVER committed)
├── .env.example        # Template for .env
├── requirements.txt    # pip freeze output
├── docs/               # Planning and documentation
│   └── PHASE1_PLAN.md  # Phase 1 roadmap
└── AGENTS.md           # This file
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                 SYSTEMD SERVICES                         │
│  trading-bot.service     → scheduler.py (cron loop)     │
│  trading-telegram.service → telegram_bot.py (polling)   │
└─────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
     ┌──────────┐   ┌──────────────┐  ┌──────────┐
     │  ai.py   │   │  strategy.py  │  │ risk.py  │
     │ OpenCode │   │  EMA + RSI    │  │position  │
     │ Go API   │   │               │  │drawdown  │
     └────┬─────┘   └──────┬───────┘  └────┬─────┘
          │                │               │
          └────────────────┼───────────────┘
                           ▼
                   ┌──────────────┐
                   │  broker.py   │
                   │ paper/live   │
                   └──────┬───────┘
                          ▼
                   ┌──────────────┐
                   │   db.py      │
                   │   SQLite     │
                   └──────────────┘
```

## Tech Stack

| Component | Library | Why |
|---|---|---|
| AI Analysis | `openai` SDK → OpenCode Go endpoint | DeepSeek V4 Pro (reasoning model), $10/mo flat |
| Database | `SQLAlchemy` + SQLite | Zero-config, fits 2GB VPS |
| Telegram | `python-telegram-bot` 22.7 | Polling mode, HTML parse mode |
| Logging | `loguru` | Clean syntax, rotation, color |
| HTTP | `httpx` (via openai SDK) | Async, reliable |
| Time | `pendulum` | Timezone-aware, `Asia/Jakarta` support |

## Code Conventions

### Imports
- Standard lib → third-party → local modules (exact order)
- All config loaded from `config.py` singleton, never from `os.getenv` directly

### Async
- All AI calls are `async def` (OpenCode Go API is synchronous but wrapped)
- `scheduler.py` uses `asyncio` event loop with `signal.signal()` for graceful shutdown
- `telegram_bot.py` uses `app.run_polling()` (blocking, run as separate process)

### Logging
- Use `logger.info()` / `logger.warning()` / `logger.error()` from loguru
- NEVER use `print()` in production code
- Log to both file (`logs/trading.log`) and stdout (systemd journal)

### Error Handling
- All AI calls wrapped in try/except with fallback defaults
- Broker operations return `Optional` — check for `None`

### Database
- Always close sessions: `session = get_session(); try: ...; finally: session.close()`
- Use SQLAlchemy ORM, not raw SQL
- All timestamps are UTC (`datetime.now(timezone.utc)`)

### Telegram Messages
- Use `ParseMode.HTML`, NOT Markdown (avoids special char conflicts)
- Escape user-provided text with `_escape_html()` before inserting
- Keep messages under 4000 chars (Telegram limit)
- Use `<pre>` tags for aligned data columns

## Important Rules

### NEVER COMMIT .env
The `.env` file contains real API keys. It is in `.gitignore`. Never stage or
commit it. Always use `.env.example` as the template.

### Rate Limiting
- DeepSeek V4 Pro has ~250 reasoning tokens overhead per call
- Set `max_tokens` ≥ 1500 for JSON responses (500 is too small)
- RETRY_DELAY = 5 seconds between retries, MAX_RETRIES = 2
- Watchlist `/list` only analyzes 5 stocks at a time (not all 15)

### Service Management
```bash
systemctl status trading-bot trading-telegram  # check both
systemctl restart trading-telegram --no-block  # restart Telegram
journalctl -u trading-bot -f                   # tail scheduler logs
journalctl -u trading-telegram -f              # tail Telegram logs
```

Both services use `KillSignal=SIGKILL` + `TimeoutStopSec=5` because Python
asyncio signal handlers are unreliable with systemd.

### Paper Trading Mode
Bot runs in PAPER TRADING when `BROKER_API_KEY` is empty. Orders are logged but
not sent. This is intentional for testing.

## Adding a New Strategy

1. Add function to `strategy.py`:
   ```python
   def my_strategy(data: list[OHLCV]) -> StrategyResult:
       ...
       return StrategyResult(symbol=..., signal=..., confidence=..., reason=...)
   ```
2. Register in `async def run_strategy()`:
   ```python
   strategies = {"ema_crossover": ..., "my_strategy": my_strategy}
   ```
3. Backtest with vectorbt before deploying live.

## Testing

There is no formal test suite yet. Manual verification:

```bash
# Test AI connectivity
python -c "
from ai import analyze_stock
import asyncio
print(asyncio.run(analyze_stock('BBCA')))
"

# Test database
python -c "
from db import init_db, get_session
init_db()
s = get_session()
print(s.query(Position).count())
s.close()
"

# Test risk manager
python -c "
from risk import risk_manager
print(risk_manager.get_risk_summary())
"
```

## Environment Variables

| Key | Description | Required? |
|---|---|---|
| `OPENCODE_GO_API_KEY` | OpenCode Go subscription key | Yes |
| `OPENCODE_GO_MODEL` | Model ID (default: deepseek-v4-pro) | No |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | Yes |
| `TELEGRAM_CHAT_ID` | Your numeric Telegram user ID | Yes |
| `BROKER_API_KEY` | Broker API key (empty = paper trade) | No |
| `INITIAL_CAPITAL` | Starting capital for paper trading | No |
| `MAX_POSITION_SIZE` | Max % of capital per trade | No |
| `MAX_DAILY_LOSS` | Max daily loss as % of capital | No |
| `MAX_DRAWDOWN` | Max drawdown before auto-pause | No |
