from dataclasses import dataclass
from enum import Enum
from typing import Optional
from loguru import logger


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class StrategyResult:
    symbol: str
    signal: Signal
    confidence: float
    reason: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass
class OHLCV:
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: str


def ema_crossover_strategy(data: list[OHLCV], short_period: int = 12, long_period: int = 26) -> StrategyResult:
    """EMA crossover — BUY if short EMA crosses above long EMA."""
    if len(data) < long_period + 1:
        return StrategyResult(
            symbol=data[-1].symbol if data else "UNKNOWN",
            signal=Signal.HOLD,
            confidence=0.0,
            reason="Insufficient data",
        )

    closes = [c.close for c in data]

    def ema(values, period):
        multiplier = 2 / (period + 1)
        result = [values[0]]
        for v in values[1:]:
            result.append((v - result[-1]) * multiplier + result[-1])
        return result

    short_ema = ema(closes, short_period)
    long_ema = ema(closes, long_period)

    prev_diff = short_ema[-2] - long_ema[-2]
    curr_diff = short_ema[-1] - long_ema[-1]

    symbol = data[-1].symbol
    price = data[-1].close

    if prev_diff <= 0 and curr_diff > 0:
        return StrategyResult(
            symbol=symbol,
            signal=Signal.BUY,
            confidence=0.7,
            reason=f"EMA {short_period} crossed above EMA {long_period}",
            entry_price=price,
        )
    elif prev_diff >= 0 and curr_diff < 0:
        return StrategyResult(
            symbol=symbol,
            signal=Signal.SELL,
            confidence=0.7,
            reason=f"EMA {short_period} crossed below EMA {long_period}",
            entry_price=price,
        )
    return StrategyResult(symbol=symbol, signal=Signal.HOLD, confidence=0.5, reason="No crossover signal")


def rsi_strategy(data: list[OHLCV], period: int = 14, oversold: float = 30, overbought: float = 70) -> StrategyResult:
    """RSI-based strategy — BUY when oversold, SELL when overbought."""
    if len(data) < period + 1:
        return StrategyResult(
            symbol=data[-1].symbol if data else "UNKNOWN",
            signal=Signal.HOLD,
            confidence=0.0,
            reason="Insufficient data",
        )

    closes = [c.close for c in data]
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
    rsi = 100 - (100 / (1 + rs))

    symbol = data[-1].symbol
    price = data[-1].close

    if rsi <= oversold:
        return StrategyResult(
            symbol=symbol,
            signal=Signal.BUY,
            confidence=0.65,
            reason=f"RSI oversold: {rsi:.1f}",
            entry_price=price,
        )
    elif rsi >= overbought:
        return StrategyResult(
            symbol=symbol,
            signal=Signal.SELL,
            confidence=0.65,
            reason=f"RSI overbought: {rsi:.1f}",
            entry_price=price,
        )
    return StrategyResult(symbol=symbol, signal=Signal.HOLD, confidence=0.5, reason=f"RSI neutral: {rsi:.1f}")


async def run_strategy(data: list[OHLCV], strategy_type: str = "ema_crossover") -> StrategyResult:
    strategies = {
        "ema_crossover": ema_crossover_strategy,
        "rsi": rsi_strategy,
    }

    strategy_fn = strategies.get(strategy_type)
    if not strategy_fn:
        return StrategyResult(
            symbol=data[-1].symbol if data else "UNKNOWN",
            signal=Signal.HOLD,
            confidence=0,
            reason=f"Unknown strategy: {strategy_type}",
        )

    result = strategy_fn(data)
    logger.info(f"Strategy {strategy_type} for {result.symbol}: {result.signal.value} ({result.confidence:.2f})")
    return result
