from datetime import datetime, timezone, timedelta
from loguru import logger

from config import config
from db import get_session, DailySummary, TradeLog, Position, OrderSide


class RiskManager:
    def __init__(self):
        self.max_position_size = config.MAX_POSITION_SIZE
        self.max_daily_loss = config.MAX_DAILY_LOSS
        self.max_drawdown = config.MAX_DRAWDOWN
        self.initial_capital = config.INITIAL_CAPITAL

    def get_current_capital(self) -> float:
        session = get_session()
        try:
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            summary = session.query(DailySummary).filter(DailySummary.date >= today).first()
            if summary and summary.ending_capital:
                return summary.ending_capital
            return self.initial_capital
        finally:
            session.close()

    def get_daily_pnl(self) -> float:
        session = get_session()
        try:
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            trades = session.query(TradeLog).filter(TradeLog.exit_date >= today).all()
            return sum(t.pnl or 0 for t in trades)
        finally:
            session.close()

    def get_max_drawdown(self) -> float:
        session = get_session()
        try:
            summaries = session.query(DailySummary).order_by(DailySummary.date).all()
            if not summaries:
                return 0.0

            peak = self.initial_capital
            max_dd = 0.0
            for s in summaries:
                capital = s.ending_capital or s.starting_capital
                peak = max(peak, capital)
                dd = (peak - capital) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)
            return max_dd
        finally:
            session.close()

    def check_order(self, symbol: str, side: OrderSide, quantity: int, estimated_price: float) -> tuple[bool, str]:
        order_value = quantity * estimated_price
        current_capital = self.get_current_capital()

        if order_value > current_capital * self.max_position_size:
            return False, f"Position size {order_value:,.0f} exceeds max {self.max_position_size*100}% ({current_capital * self.max_position_size:,.0f})"

        daily_pnl = self.get_daily_pnl()
        daily_pnl_pct = daily_pnl / current_capital if current_capital > 0 else 0
        if daily_pnl_pct < -self.max_daily_loss:
            return False, f"Daily loss {daily_pnl_pct:.2%} exceeds max {self.max_daily_loss:.2%}"

        max_dd = self.get_max_drawdown()
        if max_dd > self.max_drawdown:
            return False, f"Max drawdown {max_dd:.2%} exceeds limit {self.max_drawdown:.2%}"

        return True, "OK"

    def get_risk_summary(self) -> dict:
        current_capital = self.get_current_capital()
        daily_pnl = self.get_daily_pnl()
        max_dd = self.get_max_drawdown()
        daily_pnl_pct = daily_pnl / current_capital if current_capital > 0 else 0

        return {
            "current_capital": current_capital,
            "initial_capital": self.initial_capital,
            "total_return": ((current_capital - self.initial_capital) / self.initial_capital) if self.initial_capital > 0 else 0,
            "daily_pnl": daily_pnl,
            "daily_pnl_percent": daily_pnl_pct,
            "max_drawdown": max_dd,
            "max_position_size": self.max_position_size,
            "max_daily_loss": self.max_daily_loss,
        }


risk_manager = RiskManager()
