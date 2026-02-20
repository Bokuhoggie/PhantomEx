"""
Ollama agent loop for PhantomEx.
Each agent runs a model that analyzes market data and executes trades.
Supports autonomous mode (model decides) and advisory mode (human confirms).
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import ollama
import os

from core.portfolio import Portfolio
from core.db import get_db

# Use OLLAMA_HOST env var if set (e.g. timone uses port 8081)
_ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
_ollama_client = ollama.Client(host=_ollama_host)

# How many user+assistant message pairs to keep in rolling history
MAX_HISTORY_PAIRS = 10  # = 20 messages


def _utcnow() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


BASE_SYSTEM_PROMPT = """You are PhantomEx, an AI crypto portfolio manager. Your job is to grow the total value of a mixed portfolio of cash and crypto assets.

You will receive:
- Current market prices and 24h changes for all available assets
- Your full portfolio: cash balance + each holding with its live USD value and P&L

Respond ONLY with a valid JSON object in this exact format:
{{
  "action": "buy" | "sell" | "hold",
  "symbol": "BTC" | "ETH" | "SOL" | "BNB" | "XRP" | "ADA" | "DOGE" | "AVAX" | "DOT" | "MATIC",
  "quantity": <float>,
  "reasoning": "<your reasoning in 1-2 sentences>"
}}

Rules:
- You manage a portfolio of cash AND crypto holdings — optimise the TOTAL portfolio value
- You can: hold cash, hold coins, buy coins with cash, sell coins to cash, or swap coins (sell X → buy Y)
- quantity is the NUMBER OF COINS/TOKENS, not a dollar amount. Check prices carefully before sizing
- Never sell more coins than you currently hold (check Holdings carefully)
- A coin swap takes two cycles: SELL the source coin now; BUY the target next cycle
- If your cash is insufficient for a buy, choose SELL or HOLD instead — never force an unaffordable buy
- If uncertain about direction, HOLD — capital preservation matters
- Optimise for total portfolio value growth, not just accumulating cash

{goal_section}"""


RISK_INSTRUCTIONS = {
    "aggressive": """Risk profile: AGGRESSIVE
- Trade frequently — act on smaller signals, don't wait for certainty
- You may spend up to 40% of your cash balance on a single trade
- Prefer higher-volatility altcoins (SOL, AVAX, DOGE, MATIC, ADA) for bigger gains
- Buy dips aggressively, ride momentum
- Take profits quickly — hold positions for shorter periods
- Maximise returns, accept higher risk
- Actively swap between coins to chase the best opportunities""",

    "neutral": """Risk profile: NEUTRAL
- Standard approach: spend up to 20% of cash per trade
- Balance between BTC/ETH and mid-cap altcoins
- Hold for medium-term trends, act on clear signals
- Consider coin swaps when a better opportunity is obvious""",

    "safe": """Risk profile: SAFE
- Trade conservatively — only act on very strong, clear signals
- Never spend more than 10% of cash on a single trade
- Stick to BTC and ETH only — avoid high-volatility altcoins
- When uncertain, ALWAYS hold
- Capital preservation is the priority over gains
- Require stronger confirmation before entering any position""",
}


def build_system_prompt(goal: str, risk_profile: str = "neutral") -> str:
    if goal:
        goal_section = f"Your trading goal: {goal}"
    else:
        goal_section = "Your trading goal: Grow the total portfolio value over time."
    risk_text = RISK_INSTRUCTIONS.get(risk_profile, RISK_INSTRUCTIONS["neutral"])
    return BASE_SYSTEM_PROMPT.format(goal_section=goal_section + "\n\n" + risk_text)


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
            cost_basis = h["quantity"] * h["avg_cost"]
            pnl_pct = ((value - cost_basis) / cost_basis * 100) if cost_basis else 0
            pnl_sign = "+" if value >= cost_basis else ""
            lines.append(
                f"  {symbol}: {h['quantity']:.6f} coins  "
                f"worth ${value:,.2f}  "
                f"(avg cost ${h['avg_cost']:,.2f}, {pnl_sign}{pnl_pct:.1f}% P&L)"
            )
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
        risk_profile: str = "neutral",
        max_duration: Optional[float] = None,
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
        self.risk_profile = risk_profile      # "aggressive" | "neutral" | "safe"
        self.max_duration = max_duration      # seconds; None = run forever
        self._last_run_at: float = 0.0        # unix timestamp of last cycle
        self.started_at: Optional[float] = None  # set on first run_once()
        self.on_trade = on_trade
        self.on_decision = on_decision
        self.on_thought = on_thought
        self.portfolio = Portfolio(agent_id)
        self._running = False
        self._pending_decision: Optional[dict] = None
        self.last_thought: Optional[dict] = None  # last model decision + reasoning
        self._chat_history: list[dict] = []  # rolling conversation history (user+assistant pairs)

    async def think(self, prices: dict) -> dict:
        """Ask the model what to do given current market conditions.
        Maintains a rolling conversation history so the model stays context-aware
        across cycles without reloading from scratch each time.
        """
        context = build_market_context(prices, self.portfolio)
        system_msg = {"role": "system", "content": build_system_prompt(self.goal, self.risk_profile)}
        user_msg   = {"role": "user",   "content": context}

        # Build messages: system + rolling history + current context
        messages = [system_msg] + self._chat_history + [user_msg]

        # keep_alive keeps model loaded in GPU VRAM between cycles (5 min)
        response = _ollama_client.chat(
            model=self.model,
            messages=messages,
            keep_alive=300,
        )
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
        decision["timestamp"] = _utcnow()

        # Append this exchange to rolling history
        self._chat_history.append(user_msg)
        self._chat_history.append({"role": "assistant", "content": raw})
        # Trim to last MAX_HISTORY_PAIRS pairs (2 messages each)
        max_msgs = MAX_HISTORY_PAIRS * 2
        if len(self._chat_history) > max_msgs:
            self._chat_history = self._chat_history[-max_msgs:]

        return decision

    def _persist_hold(self, reasoning: str, timestamp: str):
        """Write a HOLD think cycle to the trades table so it appears in the log."""
        with get_db() as conn:
            conn.execute(
                """INSERT INTO trades (agent_id, symbol, side, quantity, price, total, reasoning, mode, timestamp)
                   VALUES (?, ?, 'hold', 0, 0, 0, ?, 'paper', ?)""",
                (self.agent_id, "", reasoning, timestamp),
            )

    async def execute_decision(self, decision: dict, prices: dict) -> Optional[dict]:
        """Execute a trade decision. Returns trade record or None if hold."""
        action = decision.get("action", "hold").lower()
        reasoning = decision.get("reasoning", "")
        timestamp = decision.get("timestamp", _utcnow())

        # Store thought regardless of action
        self.last_thought = {
            "action": action,
            "symbol": decision.get("symbol", ""),
            "quantity": decision.get("quantity", 0),
            "reasoning": reasoning,
            "timestamp": timestamp,
        }

        if action == "hold":
            # Persist hold to DB so it shows in trade log and survives page refresh
            self._persist_hold(reasoning, timestamp)
            # Emit as a trade event so the frontend log updates live
            hold_record = {
                "agent_id": self.agent_id,
                "symbol": "",
                "side": "hold",
                "quantity": 0,
                "price": 0,
                "total": 0,
                "reasoning": reasoning,
                "mode": "paper",
                "timestamp": timestamp,
            }
            if self.on_trade:
                await self.on_trade(self.agent_id, hold_record)
            return None

        symbol = decision.get("symbol", "").upper()
        quantity = float(decision.get("quantity", 0))
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
        if not prices:
            return
        now = time.time()
        if now - self._last_run_at < self.trade_interval:
            return  # not time yet

        # Set started_at on first run and persist it
        if self.started_at is None:
            self.started_at = now
            with get_db() as conn:
                conn.execute(
                    "UPDATE agents SET started_at = ? WHERE id = ?",
                    (now, self.agent_id),
                )

        # Check max_duration auto-stop
        if self.max_duration and (now - self.started_at) >= self.max_duration:
            print(f"[agent:{self.name}] Session limit ({self.max_duration}s) reached — stopping.")
            self._running = False
            if self.on_thought:
                await self.on_thought(self.agent_id)  # broadcast stopped state
            return

        self._last_run_at = now
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
                "timestamp": decision.get("timestamp", _utcnow()),
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
            "risk_profile": self.risk_profile,
            "max_duration": self.max_duration,
            "started_at": self.started_at,
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
        risk_profile: str = "neutral",
        max_duration: Optional[float] = None,
        on_trade=None,
        on_decision=None,
        on_thought=None,
    ) -> "Agent":
        agent_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                "INSERT INTO agents (id, name, model, mode, allowance, goal, trade_interval, risk_profile, max_duration) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (agent_id, name, model, mode, allowance, goal, trade_interval, risk_profile, max_duration),
            )
        agent = Agent(
            agent_id=agent_id,
            name=name,
            model=model,
            mode=mode,
            allowance=allowance,
            goal=goal,
            trade_interval=trade_interval,
            risk_profile=risk_profile,
            max_duration=max_duration,
            on_trade=on_trade,
            on_decision=on_decision,
            on_thought=on_thought,
        )
        self._agents[agent_id] = agent
        return agent

    def get(self, agent_id: str) -> Optional["Agent"]:
        return self._agents.get(agent_id)

    def all(self) -> list["Agent"]:
        return list(self._agents.values())

    def load_agents(self, on_trade=None, on_decision=None, on_thought=None) -> int:
        """Restore all active agents from DB on startup. Returns count loaded."""
        with get_db() as conn:
            rows = conn.execute(
                """SELECT id, name, model, mode, allowance, goal,
                          trade_interval, risk_profile, max_duration, started_at
                   FROM agents WHERE active = 1"""
            ).fetchall()
        for row in rows:
            agent = Agent(
                agent_id=row["id"],
                name=row["name"],
                model=row["model"],
                mode=row["mode"],
                allowance=row["allowance"],
                goal=row["goal"] or "",
                trade_interval=row["trade_interval"] or 60.0,
                risk_profile=row["risk_profile"] or "neutral",
                max_duration=row["max_duration"],
                on_trade=on_trade,
                on_decision=on_decision,
                on_thought=on_thought,
            )
            # Restore started_at so session timer survives restarts
            agent.started_at = row["started_at"]
            # Portfolio._load() already reconstructs cash + holdings from DB
            self._agents[row["id"]] = agent
        count = len(rows)
        if count:
            print(f"[registry] Restored {count} agent(s) from database.")
        return count

    def remove(self, agent_id: str):
        self._agents.pop(agent_id, None)
        with get_db() as conn:
            conn.execute(
                "UPDATE agents SET active = 0, started_at = NULL WHERE id = ?",
                (agent_id,),
            )
