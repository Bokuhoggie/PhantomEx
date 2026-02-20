"""
PhantomEx - FastAPI backend with WebSocket hub.
Serves real-time market data, agent state, and trade events to connected clients.
"""

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.db import init_db, get_db
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
        port = agent.portfolio.to_dict(prices)
        await ws_manager.broadcast({
            "type": "agent_state",
            "data": {**agent.to_dict(), "portfolio": port},
        })
        # Persist equity snapshot so chart survives page refresh
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with get_db() as conn:
            conn.execute(
                "INSERT INTO equity_snapshots (agent_id, total_value, cash, timestamp) VALUES (?, ?, ?, ?)",
                (agent_id, port.get("total_value", 0), port.get("cash", 0), ts),
            )
            # Keep only last 500 snapshots per agent to avoid unbounded growth
            conn.execute(
                """DELETE FROM equity_snapshots WHERE agent_id = ? AND id NOT IN (
                    SELECT id FROM equity_snapshots WHERE agent_id = ?
                    ORDER BY timestamp DESC LIMIT 500
                )""",
                (agent_id, agent_id),
            )


# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Restore agents that were active before last shutdown
    agent_registry.load_agents(
        on_trade=on_trade,
        on_decision=on_decision,
        on_thought=on_thought,
    )
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
    max_duration: Optional[float] = None    # seconds; None = run forever
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
        max_duration=req.max_duration,
        on_trade=on_trade,
        on_decision=on_decision,
        on_thought=on_thought,
    )

    # Seed initial holdings if provided — inserted directly (no cash deducted)
    if req.initial_holdings:
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
    with get_db() as conn:
        conn.execute("UPDATE agents SET risk_profile = ? WHERE id = ?", (profile, agent_id))
    prices = market_feed.get_prices()
    await ws_manager.broadcast({
        "type": "agent_state",
        "data": {**agent.to_dict(), "portfolio": agent.portfolio.to_dict(prices)},
    })
    return {"ok": True}


@app.patch("/api/agents/{agent_id}/duration")
async def set_agent_duration(agent_id: str, body: dict):
    """Set or clear the max session duration for an agent (in seconds). None = unlimited."""
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    max_duration = body.get("max_duration")  # None clears the limit
    agent.max_duration = max_duration
    from core.db import get_db
    with get_db() as conn:
        conn.execute("UPDATE agents SET max_duration = ? WHERE id = ?", (max_duration, agent_id))
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


@app.post("/api/agents/{agent_id}/save_session")
async def save_session(agent_id: str, body: dict = {}):
    """Snapshot the current agent session into saved_sessions for training data / review."""
    import json as _json  # avoid conflict with module-level json
    from datetime import datetime, timezone
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    prices = market_feed.get_prices()
    port = agent.portfolio.to_dict(prices)
    now = time.time()
    ended_at = now
    started_at = agent.started_at
    duration = (ended_at - started_at) if started_at else None
    final_value = port.get("total_value", 0)
    allowance = agent.allowance
    pnl = final_value - allowance
    pnl_pct = (pnl / allowance * 100) if allowance else 0
    saved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    notes = body.get("notes", "")

    with get_db() as conn:
        # Pull all trades for this agent
        trade_rows = conn.execute(
            "SELECT * FROM trades WHERE agent_id = ? ORDER BY timestamp ASC",
            (agent_id,),
        ).fetchall()
        trades_data = [dict(r) for r in trade_rows]

        buy_count  = sum(1 for t in trades_data if t["side"] == "buy")
        sell_count = sum(1 for t in trades_data if t["side"] == "sell")
        hold_count = sum(1 for t in trades_data if t["side"] == "hold")
        trade_count = buy_count + sell_count

        # Pull equity curve
        eq_rows = conn.execute(
            "SELECT total_value, cash, timestamp FROM equity_snapshots WHERE agent_id = ? ORDER BY timestamp ASC",
            (agent_id,),
        ).fetchall()
        equity_data = [dict(r) for r in eq_rows]

        conn.execute(
            """INSERT INTO saved_sessions
               (agent_id, agent_name, model, risk_profile, allowance, final_value,
                pnl, pnl_pct, trade_count, buy_count, sell_count, hold_count,
                started_at, ended_at, duration_secs, notes, trades_json, equity_json, saved_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                agent_id, agent.name, agent.model, agent.risk_profile,
                allowance, final_value, pnl, pnl_pct,
                trade_count, buy_count, sell_count, hold_count,
                started_at, ended_at, duration,
                notes,
                _json.dumps(trades_data),
                _json.dumps(equity_data),
                saved_at,
            ),
        )
        session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return {
        "ok": True,
        "session_id": session_id,
        "agent_name": agent.name,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "trade_count": trade_count,
        "saved_at": saved_at,
    }


@app.get("/api/sessions")
async def list_sessions():
    """List all saved sessions (summary only, no trade JSON)."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, agent_id, agent_name, model, risk_profile, allowance,
                      final_value, pnl, pnl_pct, trade_count, buy_count, sell_count,
                      hold_count, started_at, ended_at, duration_secs, notes, saved_at
               FROM saved_sessions ORDER BY saved_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: int):
    """Get full session detail including trades and equity curve."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM saved_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    import json as _json
    data = dict(row)
    data["trades"] = _json.loads(data.pop("trades_json", "[]"))
    data["equity"] = _json.loads(data.pop("equity_json", "[]"))
    return data


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: int):
    """Delete a saved session."""
    with get_db() as conn:
        conn.execute("DELETE FROM saved_sessions WHERE id = ?", (session_id,))
    return {"ok": True}


@app.get("/api/agents/{agent_id}/equity")
async def get_equity(agent_id: str, limit: int = 500):
    """Return persisted equity snapshots for chart seeding on page load."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT total_value, cash, timestamp FROM equity_snapshots WHERE agent_id = ? ORDER BY timestamp ASC LIMIT ?",
            (agent_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/trades")
async def get_trades(agent_id: Optional[str] = None, limit: int = 1000):
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
