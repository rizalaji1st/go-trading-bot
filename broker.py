from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from config import config
from db import OrderSide, OrderStatus


@dataclass
class Quote:
    symbol: str
    bid: float
    ask: float
    last_price: float
    volume: int
    timestamp: datetime


@dataclass
class OrderResult:
    broker_order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    status: OrderStatus
    timestamp: datetime


class BrokerAPI:
    """Abstract broker connector — sesuaikan implementasi setelah broker dipilih."""

    def __init__(self):
        self.api_key = config.BROKER_API_KEY
        self.api_secret = config.BROKER_API_SECRET
        self.base_url = config.BROKER_BASE_URL
        self._connected = False

    def connect(self) -> bool:
        if not self.api_key or not self.base_url:
            logger.warning("Broker not configured. Running in PAPER TRADING mode.")
            self._connected = True
            return True
        try:
            logger.info(f"Connecting to broker at {self.base_url}...")
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"Broker connection failed: {e}")
            return False

    def disconnect(self):
        self._connected = False

    def get_quote(self, symbol: str) -> Optional[Quote]:
        if not self._connected:
            return None
        return Quote(
            symbol=symbol,
            bid=0.0,
            ask=0.0,
            last_price=0.0,
            volume=0,
            timestamp=datetime.now(timezone.utc),
        )

    def place_order(self, symbol: str, side: OrderSide, quantity: int, price: Optional[float] = None) -> Optional[OrderResult]:
        if not self._connected:
            return None
        logger.info(f"ORDER: {side.value} {quantity} {symbol} @ {price or 'MARKET'}")
        return OrderResult(
            broker_order_id=f"PAPER-{datetime.now(timezone.utc).timestamp()}",
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price or 0.0,
            status=OrderStatus.FILLED,
            timestamp=datetime.now(timezone.utc),
        )

    def cancel_order(self, broker_order_id: str) -> bool:
        logger.info(f"Cancel order: {broker_order_id}")
        return True

    def get_positions(self) -> list[dict]:
        return []

    def get_account_summary(self) -> dict:
        return {
            "capital": config.INITIAL_CAPITAL,
            "available": config.INITIAL_CAPITAL,
            "pnl": 0.0,
            "pnl_percent": 0.0,
        }

    @property
    def is_connected(self) -> bool:
        return self._connected


broker = BrokerAPI()
