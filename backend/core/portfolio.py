"""
Portfolio management for PhantomEx.
Handles trade execution, balance tracking, and P&L calculation.
"""

from datetime import datetime, timezone
from typing import Optional
from core.db import get_db


class Portfolio:
    """
    Manages an agent's cash balance and crypto holdings.
    All trades are paper trades by default; real mode is a future extension.
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._cash: float = 0.0
        self._holdings: dict[str, dict] = {}  # symbol -> {quantity, avg_cost}
        self._load()

    def _load(self):
        with get_db() as conn:
            agent = conn.execute(
                "SELECT allowance FROM agents WHERE id = ?", (self.agent_id,)
            ).fetchone()
            if agent:
                self._cash = agent["allowance"]

            # Subtract spent cash from open positions
            holdings = conn.execute(
                "SELECT symbol, quantity, avg_cost FROM portfolios WHERE agent_id = ?",
                (self.agent_id,),
            ).fetchall()
            for row in holdings:
                self._holdings[row["symbol"]] = {
                    "quantity": row["quantity"],
                    "avg_cost": row["avg_cost"],
                }

            # Recalculate cash from trade history
            trades = conn.execute(
                "SELECT side, total FROM trades WHERE agent_id = ?", (self.agent_id,)
            ).fetchall()
            agent_row = conn.execute(
                "SELECT allowance FROM agents WHERE id = ?", (self.agent_id,)
            ).fetchone()
            if agent_row:
                cash = agent_row["allowance"]
                for t in trades:
                    if t["side"] == "buy":
                        cash -= t["total"]
                    elif t["side"] == "sell":
                        cash += t["total"]
                self._cash = cash

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def holdings(self) -> dict:
        return self._holdings

    def total_value(self, prices: dict) -> float:
        total = self._cash
        for symbol, holding in self._holdings.items():
            price = prices.get(symbol, {}).get("price", 0)
            total += holding["quantity"] * price
        return total

    def unrealized_pnl(self, prices: dict) -> dict:
        pnl = {}
        for symbol, holding in self._holdings.items():
            price = prices.get(symbol, {}).get("price", 0)
            cost_basis = holding["quantity"] * holding["avg_cost"]
            current_value = holding["quantity"] * price
            pnl[symbol] = {
                "unrealized": current_value - cost_basis,
                "pct": ((current_value - cost_basis) / cost_basis * 100) if cost_basis else 0,
            }
        return pnl

    def deposit(self, amount: float):
        """Add fake cash to the portfolio. Bumps agents.allowance in DB so _load() stays consistent."""
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        with get_db() as conn:
            conn.execute(
                "UPDATE agents SET allowance = allowance + ? WHERE id = ?",
                (amount, self.agent_id),
            )
        self._cash += amount

    def execute_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        reasoning: Optional[str] = None,
        mode: str = "paper",
    ) -> dict:
        total = quantity * price

        if side == "buy":
            if total > self._cash:
                raise ValueError(f"Insufficient cash: need {total:.2f}, have {self._cash:.2f}")
            self._cash -= total
            if symbol in self._holdings:
                existing = self._holdings[symbol]
                new_qty = existing["quantity"] + quantity
                new_avg = (existing["avg_cost"] * existing["quantity"] + price * quantity) / new_qty
                self._holdings[symbol] = {"quantity": new_qty, "avg_cost": new_avg}
            else:
                self._holdings[symbol] = {"quantity": quantity, "avg_cost": price}

        elif side == "sell":
            if symbol not in self._holdings or self._holdings[symbol]["quantity"] < quantity:
                raise ValueError(f"Insufficient holdings to sell {quantity} {symbol}")
            self._cash += total
            self._holdings[symbol]["quantity"] -= quantity
            if self._holdings[symbol]["quantity"] <= 0:
                del self._holdings[symbol]

        else:
            raise ValueError(f"Invalid side: {side}")

        # Generate timestamp once — used for both DB insert and returned trade dict
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Persist to DB
        with get_db() as conn:
            conn.execute(
                """INSERT INTO trades (agent_id, symbol, side, quantity, price, total, reasoning, mode, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.agent_id, symbol, side, quantity, price, total, reasoning, mode, ts),
            )
            # Upsert portfolio holdings
            if symbol in self._holdings:
                conn.execute(
                    """INSERT INTO portfolios (agent_id, symbol, quantity, avg_cost, updated_at)
                       VALUES (?, ?, ?, ?, datetime('now'))
                       ON CONFLICT(agent_id, symbol) DO UPDATE SET
                           quantity = excluded.quantity,
                           avg_cost = excluded.avg_cost,
                           updated_at = excluded.updated_at""",
                    (
                        self.agent_id,
                        symbol,
                        self._holdings[symbol]["quantity"],
                        self._holdings[symbol]["avg_cost"],
                    ),
                )
            else:
                conn.execute(
                    "DELETE FROM portfolios WHERE agent_id = ? AND symbol = ?",
                    (self.agent_id, symbol),
                )

        trade = {
            "agent_id": self.agent_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "total": total,
            "reasoning": reasoning,
            "mode": mode,
            "timestamp": ts,
        }
        return trade

    def to_dict(self, prices: dict = None) -> dict:
        prices = prices or {}
        return {
            "agent_id": self.agent_id,
            "cash": self._cash,
            "holdings": self._holdings,
            "total_value": self.total_value(prices),
            "unrealized_pnl": self.unrealized_pnl(prices),
        }
