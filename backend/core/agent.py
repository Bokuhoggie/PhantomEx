"""
Ollama agent loop for PhantomEx.
Each agent runs a model that analyzes market data and executes trades.
Supports autonomous mode (model decides) and advisory mode (human confirms).
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Callable, Optional

import ollama

from core.portfolio import Portfolio
from core.db import get_db


SYSTEM_PROMPT = """You are PhantomEx, an AI crypto trading agent. You analyze market data and make trading decisions.

You will receive:
- Current prices and 24h changes for available assets
- Your current portfolio (cash balance + holdings)
- Recent trade history

Respond ONLY with a valid JSON object in this exact format:
{
  "action": "buy" | "sell" | "hold",
  "symbol": "BTC" | "ETH" | "SOL" | ... (required if action is buy/sell),
  "quantity": <float> (required if action is buy/sell),
  "reasoning": "<brief explanation of your decision>"
}

Rules:
- Never spend more than 20% of total portfolio value on a single trade
- Never sell more than you own
- Be concise in reasoning (1-2 sentences max)
- If uncertain, prefer hold
"""


def build_market_context(prices: dict, portfolio: Portfolio) -> str:
    lines = ["=== MARKET PRICES ==="]
    for symbol, data in prices.items():
        change = data.get("change_24h", 0)
        arrow = "↑" if change >= 0 else "↓"
        lines.append(f"{symbol}: ${data['price']:,.2f}  {arrow}{abs(change):.2f}% 24h")

    lines.append("\n=== YOUR PORTFOLIO ===")
    lines.append(f"Cash: ${portfolio.cash:,.2f}")
    if portfolio.holdings:
        lines.append("Holdings:")
        for symbol, h in portfolio.holdings.items():
            price = prices.get(symbol, {}).get("price", 0)
            value = h["quantity"] * price
            lines.append(f"  {symbol}: {h['quantity']:.6f} units @ ${h['avg_cost']:,.2f} avg  (current value: ${value:,.2f})")
    else:
        lines.append("Holdings: none")

    total = portfolio.total_value(prices)
    lines.append(f"Total Portfolio Value: ${total:,.2f}")
    return "\n".join(lines)


class Agent:
    def __init__(
        self,
        agent_id: str,
        name: str,
        model: str,
        mode: str = "autonomous",
        allowance: float = 10000.0,
        on_trade: Optional[Callable] = None,
        on_decision: Optional[Callable] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.model = model
        self.mode = mode  # "autonomous" | "advisory"
        self.allowance = allowance
        self.on_trade = on_trade        # async callback when a trade executes
        self.on_decision = on_decision  # async callback for advisory mode (pending decisions)
        self.portfolio = Portfolio(agent_id)
        self._running = False
        self._pending_decision: Optional[dict] = None

    async def think(self, prices: dict) -> dict:
        """Ask the model what to do given current market conditions."""
        context = build_market_context(prices, self.portfolio)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]
        response = ollama.chat(model=self.model, messages=messages)
        raw = response["message"]["content"].strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        decision = json.loads(raw)
        decision["agent_id"] = self.agent_id
        decision["timestamp"] = datetime.utcnow().isoformat()
        return decision

    async def execute_decision(self, decision: dict, prices: dict) -> Optional[dict]:
        """Execute a trade decision. Returns trade record or None if hold."""
        action = decision.get("action", "hold").lower()
        if action == "hold":
            return None

        symbol = decision.get("symbol", "").upper()
        quantity = float(decision.get("quantity", 0))
        reasoning = decision.get("reasoning", "")
        price = prices.get(symbol, {}).get("price")

        if not price or quantity <= 0 or not symbol:
            return None

        try:
            trade = self.portfolio.execute_trade(
                symbol=symbol,
                side=action,
                quantity=quantity,
                price=price,
                reasoning=reasoning,
                mode="paper",
            )
            if self.on_trade:
                await self.on_trade(self.agent_id, trade)
            return trade
        except ValueError as e:
            print(f"[agent:{self.name}] Trade rejected: {e}")
            return None

    async def run_once(self, prices: dict):
        """Single decision cycle."""
        try:
            decision = await self.think(prices)
        except Exception as e:
            print(f"[agent:{self.name}] Model error: {e}")
            return

        if self.mode == "autonomous":
            await self.execute_decision(decision, prices)
        elif self.mode == "advisory":
            self._pending_decision = decision
            if self.on_decision:
                await self.on_decision(self.agent_id, decision)

    async def approve_pending(self, prices: dict):
        """Human approves the pending advisory decision."""
        if self._pending_decision:
            await self.execute_decision(self._pending_decision, prices)
            self._pending_decision = None

    def reject_pending(self):
        self._pending_decision = None

    def to_dict(self) -> dict:
        return {
            "id": self.agent_id,
            "name": self.name,
            "model": self.model,
            "mode": self.mode,
            "allowance": self.allowance,
            "running": self._running,
            "pending_decision": self._pending_decision,
        }


class AgentRegistry:
    """Manages all active agents."""

    def __init__(self):
        self._agents: dict[str, Agent] = {}

    def create_agent(
        self,
        name: str,
        model: str,
        mode: str = "autonomous",
        allowance: float = 10000.0,
        on_trade=None,
        on_decision=None,
    ) -> Agent:
        agent_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                "INSERT INTO agents (id, name, model, mode, allowance) VALUES (?, ?, ?, ?, ?)",
                (agent_id, name, model, mode, allowance),
            )
        agent = Agent(
            agent_id=agent_id,
            name=name,
            model=model,
            mode=mode,
            allowance=allowance,
            on_trade=on_trade,
            on_decision=on_decision,
        )
        self._agents[agent_id] = agent
        return agent

    def get(self, agent_id: str) -> Optional[Agent]:
        return self._agents.get(agent_id)

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    def remove(self, agent_id: str):
        self._agents.pop(agent_id, None)
        with get_db() as conn:
            conn.execute("UPDATE agents SET active = 0 WHERE id = ?", (agent_id,))
