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
import os

from core.portfolio import Portfolio
from core.db import get_db

# Use OLLAMA_HOST env var if set (e.g. timone uses port 8081)
_ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
_ollama_client = ollama.Client(host=_ollama_host)


BASE_SYSTEM_PROMPT = """You are PhantomEx, an AI crypto trading agent. You analyze market data and make trading decisions.

You will receive:
- Current prices and 24h changes for available assets
- Your current portfolio (cash balance + holdings)

Respond ONLY with a valid JSON object in this exact format:
{{
  "action": "buy" | "sell" | "hold",
  "symbol": "BTC" | "ETH" | "SOL" | "BNB" | "XRP" | "ADA" | "DOGE" | "AVAX" | "DOT" | "MATIC",
  "quantity": <float> (required if action is buy/sell),
  "reasoning": "<your reasoning in 1-2 sentences>"
}}

Rules:
- quantity is the NUMBER OF COINS/TOKENS, not dollar amount. BTC costs ~$60000 each so 0.001 BTC = $60
- Never spend more than 20% of your cash balance on a single trade
- Never sell more than you own
- If uncertain, prefer hold
- quantity must be a positive number (can be fractional, e.g. 0.001)

{goal_section}"""


def build_system_prompt(goal: str) -> str:
    if goal:
        goal_section = f"Your trading goal: {goal}"
    else:
        goal_section = "Your trading goal: Grow the portfolio value over time."
    return BASE_SYSTEM_PROMPT.format(goal_section=goal_section)


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
        goal: str = "",
        trade_interval: float = 60.0,
        on_trade: Optional[Callable] = None,
        on_decision: Optional[Callable] = None,
        on_thought: Optional[Callable] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.model = model
        self.mode = mode  # "autonomous" | "advisory"
        self.allowance = allowance
        self.goal = goal
        self.trade_interval = trade_interval  # seconds between think cycles
        self._last_run_at: float = 0.0        # unix timestamp of last cycle
        self.on_trade = on_trade
        self.on_decision = on_decision
        self.on_thought = on_thought
        self.portfolio = Portfolio(agent_id)
        self._running = False
        self._pending_decision: Optional[dict] = None
        self.last_thought: Optional[dict] = None  # last model decision + reasoning

    async def think(self, prices: dict) -> dict:
        """Ask the model what to do given current market conditions."""
        context = build_market_context(prices, self.portfolio)
        messages = [
            {"role": "system", "content": build_system_prompt(self.goal)},
            {"role": "user", "content": context},
        ]
        response = _ollama_client.chat(model=self.model, messages=messages, keep_alive=0)
        raw = response["message"]["content"].strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw[3:]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        decision = json.loads(raw)
        decision["agent_id"] = self.agent_id
        decision["timestamp"] = datetime.utcnow().isoformat()
        return decision

    async def execute_decision(self, decision: dict, prices: dict) -> Optional[dict]:
        """Execute a trade decision. Returns trade record or None if hold."""
        action = decision.get("action", "hold").lower()

        # Store thought regardless of action
        self.last_thought = {
            "action": action,
            "symbol": decision.get("symbol", ""),
            "quantity": decision.get("quantity", 0),
            "reasoning": decision.get("reasoning", ""),
            "timestamp": decision.get("timestamp", datetime.utcnow().isoformat()),
        }

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
        """Single decision cycle. Skips if trade_interval has not elapsed."""
        import time
        if not prices:
            return
        if time.time() - self._last_run_at < self.trade_interval:
            return  # not time yet
        self._last_run_at = time.time()
        try:
            decision = await self.think(prices)
        except Exception as e:
            print(f"[agent:{self.name}] Model error: {e}")
            return

        if self.mode == "autonomous":
            await self.execute_decision(decision, prices)
        elif self.mode == "advisory":
            self.last_thought = {
                "action": decision.get("action", "hold"),
                "symbol": decision.get("symbol", ""),
                "quantity": decision.get("quantity", 0),
                "reasoning": decision.get("reasoning", ""),
                "timestamp": decision.get("timestamp", datetime.utcnow().isoformat()),
            }
            self._pending_decision = decision
            if self.on_decision:
                await self.on_decision(self.agent_id, decision)
        # Always broadcast updated agent state after a think cycle
        if self.on_thought:
            await self.on_thought(self.agent_id)

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
            "goal": self.goal,
            "trade_interval": self.trade_interval,
            "running": self._running,
            "pending_decision": self._pending_decision,
            "last_thought": self.last_thought,
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
        goal: str = "",
        trade_interval: float = 60.0,
        on_trade=None,
        on_decision=None,
        on_thought=None,
    ) -> Agent:
        agent_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                "INSERT INTO agents (id, name, model, mode, allowance, goal, trade_interval) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (agent_id, name, model, mode, allowance, goal, trade_interval),
            )
        agent = Agent(
            agent_id=agent_id,
            name=name,
            model=model,
            mode=mode,
            allowance=allowance,
            goal=goal,
            trade_interval=trade_interval,
            on_trade=on_trade,
            on_decision=on_decision,
            on_thought=on_thought,
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
