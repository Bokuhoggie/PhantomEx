# PhantomEx

> AI-powered crypto paper trading platform. Deploy Ollama models as autonomous trading agents, watch them compete in real-time, and eventually graduate them to real wallets.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python · FastAPI · WebSocket |
| AI Agents | Ollama (local LLMs) |
| Market Data | CoinGecko API (live) + historical replay |
| Persistence | SQLite |
| Frontend | Svelte + Vite |
| Server Monitor | Textual TUI |

---

## Features

- **Multi-agent trading** — deploy multiple Ollama models simultaneously, each with their own portfolio and allowance
- **Autonomous mode** — model reads market data and executes trades on its own
- **Advisory mode** — model proposes trades, human approves or rejects from the UI
- **Live prices** — CoinGecko feed updated every 15 seconds across 10 major crypto pairs
- **Historical replay** — replay past market data for controlled backtesting
- **Real-time dashboard** — Svelte UI connected via WebSocket; price bar, agent cards, trade log
- **TUI monitor** — Textual terminal UI for SSH sessions on the server

---

## Quickstart

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`

### TUI Monitor (optional, on the server)

```bash
cd backend
python -m tui.monitor
```

---

## Architecture

```
Browser (Svelte)
    ↕  WebSocket + REST
FastAPI Server
    ├── MarketFeed  →  CoinGecko / historical replay
    ├── AgentRegistry  →  Ollama model agent loops
    ├── Portfolio  →  trade execution + P&L
    └── SQLite  →  agents, trades, price snapshots
```

### WebSocket Events

| Event | Direction | Description |
|---|---|---|
| `prices` | server→client | Latest price snapshot for all symbols |
| `agent_state` | server→client | Full agent + portfolio state |
| `trade` | server→client | A trade just executed |
| `portfolio` | server→client | Updated portfolio after trade |
| `pending_decision` | server→client | Advisory mode: model proposes a trade |
| `approve_trade` | client→server | Human approves pending trade |
| `reject_trade` | client→server | Human rejects pending trade |

---

## Roadmap

- [ ] Price charts (lightweight-charts OHLC)
- [ ] Per-agent performance metrics (P&L over time, win rate, Sharpe)
- [ ] Historical replay mode UI controls
- [ ] Multi-session support
- [ ] Real wallet integration (future)
