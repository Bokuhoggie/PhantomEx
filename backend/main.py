"""
PhantomEx - FastAPI backend with WebSocket hub.
Serves real-time market data, agent state, and trade events to connected clients.
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.db import init_db
from core.market import MarketFeed, fetch_historical, DEFAULT_SYMBOLS
from core.agent import AgentRegistry
from core.portfolio import Portfolio


# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, message: dict):
        data = json.dumps(message)
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)

    async def send_to(self, ws: WebSocket, message: dict):
        await ws.send_text(json.dumps(message))


ws_manager = ConnectionManager()
market_feed = MarketFeed(mode="live", interval=60.0)
agent_registry = AgentRegistry()


# ── Callbacks ─────────────────────────────────────────────────────────────────

async def on_price_update(prices: dict):
    await ws_manager.broadcast({"type": "prices", "data": prices})
    # Trigger agent decision cycles
    for agent in agent_registry.all():
        asyncio.create_task(agent.run_once(prices))


async def on_trade(agent_id: str, trade: dict):
    await ws_manager.broadcast({"type": "trade", "agent_id": agent_id, "data": trade})
    agent = agent_registry.get(agent_id)
    if agent:
        prices = market_feed.get_prices()
        # Broadcast updated portfolio
        await ws_manager.broadcast({
            "type": "portfolio",
            "agent_id": agent_id,
            "data": agent.portfolio.to_dict(prices),
        })
        # Broadcast updated agent state (includes last_thought)
        await ws_manager.broadcast({
            "type": "agent_state",
            "data": {**agent.to_dict(), "portfolio": agent.portfolio.to_dict(prices)},
        })


async def on_decision(agent_id: str, decision: dict):
    """Advisory mode: broadcast pending decision for human review."""
    await ws_manager.broadcast({
        "type": "pending_decision",
        "agent_id": agent_id,
        "data": decision,
    })


async def on_thought(agent_id: str):
    """Broadcast updated agent state after any think cycle (holds, rejections, advisory)."""
    agent = agent_registry.get(agent_id)
    if agent:
        prices = market_feed.get_prices()
        await ws_manager.broadcast({
            "type": "agent_state",
            "data": {**agent.to_dict(), "portfolio": agent.portfolio.to_dict(prices)},
        })


# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    market_feed.subscribe(on_price_update)
    asyncio.create_task(market_feed.start())
    print("[phantomex] Server started.")
    yield
    await market_feed.stop()
    print("[phantomex] Server stopped.")


app = FastAPI(title="PhantomEx", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    # Send current state on connect
    prices = market_feed.get_prices()
    if prices:
        await ws_manager.send_to(ws, {"type": "prices", "data": prices})
    for agent in agent_registry.all():
        await ws_manager.send_to(ws, {
            "type": "agent_state",
            "data": {
                **agent.to_dict(),
                "portfolio": agent.portfolio.to_dict(prices),
            },
        })
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            await handle_ws_message(ws, msg)
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


async def handle_ws_message(ws: WebSocket, msg: dict):
    """Handle incoming messages from the browser over WebSocket."""
    event = msg.get("type")

    if event == "approve_trade":
        agent_id = msg.get("agent_id")
        agent = agent_registry.get(agent_id)
        if agent:
            await agent.approve_pending(market_feed.get_prices())

    elif event == "reject_trade":
        agent_id = msg.get("agent_id")
        agent = agent_registry.get(agent_id)
        if agent:
            agent.reject_pending()

    elif event == "ping":
        await ws_manager.send_to(ws, {"type": "pong"})


# ── REST API ──────────────────────────────────────────────────────────────────

class CreateAgentRequest(BaseModel):
    name: str
    model: str
    mode: str = "autonomous"
    allowance: float = 10000.0
    goal: str = ""
    trade_interval: float = 60.0            # seconds between think cycles
    risk_profile: str = "neutral"           # "aggressive" | "neutral" | "safe"
    initial_holdings: dict[str, float] = {} # {symbol: quantity} — declared, not bought


@app.post("/api/agents")
async def create_agent(req: CreateAgentRequest):
    agent = agent_registry.create_agent(
        name=req.name,
        model=req.model,
        mode=req.mode,
        allowance=req.allowance,
        goal=req.goal,
        trade_interval=req.trade_interval,
        risk_profile=req.risk_profile,
        on_trade=on_trade,
        on_decision=on_decision,
        on_thought=on_thought,
    )

    # Seed initial holdings if provided — inserted directly (no cash deducted)
    if req.initial_holdings:
        from core.db import get_db
        prices = market_feed.get_prices()
        for symbol, quantity in req.initial_holdings.items():
            symbol = symbol.upper()
            if symbol not in prices or quantity <= 0:
                continue
            price = prices[symbol]["price"]
            with get_db() as conn:
                conn.execute(
                    """INSERT INTO portfolios (agent_id, symbol, quantity, avg_cost, updated_at)
                       VALUES (?, ?, ?, ?, datetime('now'))
                       ON CONFLICT(agent_id, symbol) DO UPDATE SET
                           quantity = excluded.quantity,
                           avg_cost = excluded.avg_cost,
                           updated_at = excluded.updated_at""",
                    (agent.agent_id, symbol, quantity, price),
                )
            agent.portfolio._holdings[symbol] = {"quantity": quantity, "avg_cost": price}

    prices = market_feed.get_prices()
    data = {**agent.to_dict(), "portfolio": agent.portfolio.to_dict(prices)}
    await ws_manager.broadcast({"type": "agent_state", "data": data})
    return data


@app.get("/api/agents")
async def list_agents():
    prices = market_feed.get_prices()
    return [
        {**a.to_dict(), "portfolio": a.portfolio.to_dict(prices)}
        for a in agent_registry.all()
    ]


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent_registry.remove(agent_id)
    await ws_manager.broadcast({"type": "agent_removed", "agent_id": agent_id})
    return {"ok": True}


@app.post("/api/agents/{agent_id}/trade")
async def trigger_trade(agent_id: str):
    """Manually trigger one decision cycle for an agent (for testing)."""
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    prices = market_feed.get_prices()
    if not prices:
        raise HTTPException(status_code=503, detail="No market data yet")
    asyncio.create_task(agent.run_once(prices))
    # Broadcast updated agent state (last_thought will update async)
    await asyncio.sleep(0)  # yield so task can start
    return {"ok": True, "message": "Decision cycle triggered"}


@app.patch("/api/agents/{agent_id}/mode")
async def set_agent_mode(agent_id: str, body: dict):
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    mode = body.get("mode")
    if mode not in ("autonomous", "advisory"):
        raise HTTPException(status_code=400, detail="Invalid mode")
    agent.mode = mode
    await ws_manager.broadcast({"type": "agent_state", "data": agent.to_dict()})
    return {"ok": True}


@app.patch("/api/agents/{agent_id}/risk")
async def set_risk_profile(agent_id: str, body: dict):
    """Change an agent's risk profile on the fly. Takes effect on the next think cycle."""
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    profile = body.get("risk_profile")
    if profile not in ("aggressive", "neutral", "safe"):
        raise HTTPException(status_code=400, detail="Invalid risk profile")
    agent.risk_profile = profile
    from core.db import get_db
    with get_db() as conn:
        conn.execute("UPDATE agents SET risk_profile = ? WHERE id = ?", (profile, agent_id))
    prices = market_feed.get_prices()
    await ws_manager.broadcast({
        "type": "agent_state",
        "data": {**agent.to_dict(), "portfolio": agent.portfolio.to_dict(prices)},
    })
    return {"ok": True}


class DepositRequest(BaseModel):
    amount: float


@app.post("/api/agents/{agent_id}/deposit")
async def deposit_to_agent(agent_id: str, req: DepositRequest):
    """Add fake cash to an agent's wallet."""
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    agent.portfolio.deposit(req.amount)
    agent.allowance += req.amount  # keep in-memory allowance in sync for to_dict() P&L
    prices = market_feed.get_prices()
    await ws_manager.broadcast({
        "type": "agent_state",
        "data": {**agent.to_dict(), "portfolio": agent.portfolio.to_dict(prices)},
    })
    return {"ok": True, "new_cash": agent.portfolio.cash}


@app.get("/api/market/prices")
async def get_prices():
    return market_feed.get_prices()


@app.get("/api/market/history/{symbol}")
async def get_history(symbol: str, days: int = 30):
    try:
        data = await fetch_historical(symbol.upper(), days)
        return {"symbol": symbol.upper(), "data": data}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/market/symbols")
async def get_symbols():
    return DEFAULT_SYMBOLS


@app.get("/api/trades")
async def get_trades(agent_id: Optional[str] = None, limit: int = 1000):
    from core.db import get_db
    with get_db() as conn:
        if agent_id:
            rows = conn.execute(
                "SELECT * FROM trades WHERE agent_id = ? ORDER BY timestamp DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/ollama/models")
async def list_ollama_models(host: Optional[str] = None):
    """List available models from the Ollama instance at the given host."""
    try:
        import ollama, os
        effective_host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        client = ollama.Client(host=effective_host)
        models = client.list()
        return [m["model"] for m in models.get("models", [])]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama error: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ── Serve frontend static files (must be last) ───────────────────────────────

import os
from fastapi.responses import FileResponse

_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        index = os.path.join(_frontend_dist, "index.html")
        return FileResponse(index)
