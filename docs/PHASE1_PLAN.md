# Phase 1 — Data Pipeline & Backtesting Foundation

> **Status:** Planned | **Timeline:** 4 weeks | **Goal:** Data-driven strategy validation

## Overview

Currently the bot relies entirely on AI analysis (OpenCode Go / DeepSeek V4 Pro)
to generate trading signals. The AI has no access to real market data — it
generates signals based on its training knowledge, not actual price action.

Phase 1 builds the data foundation: fetch real IDX market data, backtest
strategies against history, and make the bot data-driven.

## Target Architecture After Phase 1

```
scheduler.py ──▶ ai.py (OpenCode Go) ──▶ Telegram alerts
    │
    ├── data_feed.py (NEW)      yfinance + SQLite historical data
    ├── backtest.py (NEW)       vectorbt walk-forward backtester
    ├── strategy.py             EMA crossover, RSI
    ├── risk.py                 Position sizing, drawdown (+ IDX rules)
    ├── broker.py               Paper trading (+ manual approval flow)
    └── db.py                   SQLite (+ market_data table)
```

---

## Week 1 — IDX Data Pipeline

### 1.1 Install Data Dependencies

```bash
pip install yfinance pandas numpy
```

### 1.2 Create `data_feed.py`

```python
# data_feed.py — IDX market data fetcher
#
# Sources:
#   yfinance  — EOD OHLCV, suffix .JK (free, ~15 min delay)
#
# Functions:
#   fetch_daily(symbol: str)         → pulls OHLCV for one stock
#   fetch_bulk(symbols: list[str])   → pulls multiple stocks
#   update_all()                     → daily EOD pull for entire watchlist
#   get_history(symbol, days)        → query from SQLite cache
#
# Table: market_data (SQLite via SQLAlchemy)
#   symbol, date, open, high, low, close, volume, source, fetched_at
```

### 1.3 Add `market_data` table to `db.py`

```python
class MarketData(Base):
    __tablename__ = "market_data"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False)
    date = Column(DateTime, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(BigInteger)
    source = Column(String(20), default="yfinance")
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # Unique constraint: (symbol, date)
```

### 1.4 Populate 6 Months Historical Data

- Pull EOD data from 2025-11-01 to present for all 15 watchlist stocks
- Run as one-time script: `python -m data_feed --seed`
- Validate: no gaps, no zero-volume days, splits adjusted

### 1.5 Add Daily EOD Update to Scheduler

- Cron trigger: 16:00 WIB (after market close)
- New function `async def eod_data_update()` in scheduler.py

---

## Week 2 — Backtesting Engine

### 2.1 Install Backtesting Framework

```bash
pip install vectorbt
```

Vectorbt was chosen over alternatives:

| Framework | Memory (2GB VPS) | IDX Compatible | Speed |
|---|---|---|---|
| **vectorbt** | ~200MB | Yes | Very fast (Numba JIT) |
| zipline-rel | ~500MB-1GB | Needs adapter | Moderate |
| bt | ~100MB | Yes | Slow on large universe |
| Custom pandas | ~50MB | Yes | Manual work |

### 2.2 Create `backtest.py`

```python
# backtest.py — Strategy backtester
#
# Functions:
#   run_backtest(strategy_fn, symbol, start, end) → BacktestResult
#   walk_forward(strategy_fn, symbol, train_years=3, test_years=1, step_months=6)
#   compare_strategies(strategies, symbols) → DataFrame
#
# BacktestResult dataclass:
#   total_return, sharpe_ratio, max_drawdown, win_rate,
#   profit_factor, total_trades, avg_win, avg_loss
```

### 2.3 Backtest Existing Strategies

- EMA Crossover on BBCA, BBRI, TLKM (5 years data)
- RSI on BBCA, BBRI, TLKM (5 years data)
- Walk-forward: train 3 years → test 1 year → slide 6 months → repeat
- Record results in SQLite table `backtest_results`

### 2.4 Define Minimum Acceptance Criteria

| Metric | Threshold |
|---|---|
| Win rate | > 55% |
| Sharpe ratio | > 1.0 |
| Profit factor | > 1.3 |
| Max drawdown | < 20% |
| Total trades | > 100 |

Strategies failing these criteria are NOT deployed live.

---

## Week 3 — IDX-Aware Risk Rules

### 3.1 Implement IDX-Specific Validations

```python
# risk.py additions:

def validate_lot_quantity(quantity: int) -> int:
    """Round down to 100-share lots (IDX standard lot size)."""
    return (quantity // 100) * 100

def check_auto_rejection(price: float, prev_close: float) -> tuple[bool, str]:
    """IDX auto-rejection bands: ±20-35% depending on price range."""
    if prev_close >= 5000:
        band = 0.20
    elif prev_close >= 200:
        band = 0.25
    else:
        band = 0.35
    upper = prev_close * (1 + band)
    lower = prev_close * (1 - band)
    if not (lower <= price <= upper):
        return False, f"Price {price} outside AR band [{lower}-{upper}]"
    return True, "OK"

def is_trading_halted(symbol: str) -> bool:
    """Check if stock is suspended or market-wide halt."""
    # Query IDX status endpoint
    ...
```

### 3.2 Market Schedule Awareness

```python
def is_trading_session() -> bool:
    """Check if IDX is in continuous trading session."""
    # Session 1: 09:00-11:30 WIB (02:00-04:30 UTC)
    # Session 2: 13:30-14:49 WIB (06:30-07:49 UTC)
    # Pre-open (08:45-08:55) and pre-close (14:49-15:00) are NOT trading
    ...

def is_settled(date: datetime) -> bool:
    """T+2 settlement check."""
    ...
```

---

## Week 4 — Hybrid Execution Flow

### 4.1 Telegram Manual Approval

Since no Indonesian broker provides a public retail API, execute trades via
manual approval:

```
Bot detects signal (e.g., BUY BBCA)
    │
    ▼
Risk checks pass
    │
    ▼
Telegram message: "🟢 BUY BBCA 10 lot @ 10250. Konfirmasi?"
    │
    ├── User: /confirm → bot logs order, user executes manually
    └── User: /reject  → bot logs rejection, updates signal as skipped
```

### 4.2 Persist Manual Orders

```python
# New Telegram commands:

/order BUY BBCA 10 10250  → Create manual order record
/confirm <id>              → Confirm pending order
/reject <id>               → Reject pending order
/fill <id> <price>         → Mark order as filled with actual price
```

### 4.3 Signal Tracking & Accuracy

```python
# Track signal → order → outcome chain:

# New columns in signals table:
#   order_id (FK to orders)
#   outcome_price (actual fill price)
#   outcome_pnl (profit/loss from this signal)

# Accuracy report:
#   /accuracy → "Signals this month: 45 BUY, 12 SELL. Win rate: 68%"
```

---

## Success Criteria for Phase 1

- [ ] `data_feed.py` pulls and stores 6+ months of OHLCV
- [ ] `backtest.py` runs walk-forward test on 2+ strategies
- [ ] EMA crossover meets minimum acceptance criteria (win rate >55%, sharpe >1.0)
- [ ] IDX auto-rejection bands validated in risk.py
- [ ] Telegram manual approval flow functional
- [ ] 100% of signals tracked with accuracy metrics

## Dependencies for Phase 2

Phase 1 must be complete before Phase 2 can begin:

- **Phase 2** depends on historical data (Phase 1 Week 1)
- **Phase 2** depends on backtesting validation (Phase 1 Week 2)
- **Phase 2** adds: multi-strategy engine, dynamic watchlist, broker API research

---

## Related Files

| File | Phase 1 Changes |
|---|---|
| `data_feed.py` | NEW — IDX data pipeline |
| `backtest.py` | NEW — vectorbt backtesting |
| `db.py` | Add MarketData, BacktestResult tables |
| `risk.py` | Add IDX rules (lot size, AR bands, halt) |
| `scheduler.py` | Add EOD data update trigger |
| `telegram_bot.py` | Add /order, /confirm, /reject, /accuracy |
