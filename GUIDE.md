# PhantomEx — Guide for Dummies 👻

## What Is This?

**PhantomEx** is an AI-powered crypto paper trading platform.

- You give an AI model (running on your own hardware via Ollama) a fake wallet with fake money
- The AI watches live crypto prices and makes real trading decisions autonomously
- Nothing is real — no real money, no real wallets, no exchanges. It's a sandbox
- Multiple agents can run at once, each with a different model, goal, and wallet
- You can watch them trade in real-time from any browser on your network

The end goal is to eventually wire this into real wallets once the agents prove themselves.

---

## The Stack (What It's Built On)

```
┌─────────────────────────────────────────────────────┐
│  Browser  (Svelte + Vite frontend)                  │
│  → Real-time UI via WebSocket                       │
│  → http://192.168.86.51:8000                        │
└────────────────────┬────────────────────────────────┘
                     │ WebSocket + REST
┌────────────────────▼────────────────────────────────┐
│  FastAPI Backend  (Python, runs on timone)          │
│  → Serves the web UI                                │
│  → Manages agents, portfolios, trade history        │
│  → Fetches live prices from CoinGecko               │
│  → SQLite database (data/phantomex.db)              │
└────────────────────┬────────────────────────────────┘
                     │ HTTP (Ollama API)
┌────────────────────▼────────────────────────────────┐
│  Ollama  (LLM runtime, runs on timone GPU)          │
│  → Hosts the AI models locally                      │
│  → Port 8081 on timone                              │
│  → Models: qwen2.5-coder:14b, gemma3:12b            │
└─────────────────────────────────────────────────────┘
```

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | Svelte 4 + Vite | Reactive web UI |
| Backend | FastAPI (Python) | REST API + WebSocket hub |
| Database | SQLite (WAL mode) | Agents, trades, portfolios |
| AI runtime | Ollama | Runs LLM models locally |
| Prices | CoinGecko API | Live crypto prices, no API key |
| Deployment | systemd | Auto-starts on timone boot |

---

## Servers

| Server | What It Is | Access |
|---|---|---|
| **timone** | Your Linux GPU server | `ssh timone@timone` |
| **timone IP** | Local network address | `192.168.86.51` |
| **PhantomEx UI** | Web app | `http://192.168.86.51:8000` |
| **Ollama API** | Model runtime | `http://localhost:8081` (on timone) |
| **Open WebUI** | Separate chat UI | `http://192.168.86.51:3000` |

---

## File Structure

```
PhantomEx/
├── backend/
│   ├── main.py              ← FastAPI app, all API routes, WebSocket hub
│   ├── core/
│   │   ├── agent.py         ← Agent logic, Ollama chat calls, decision loop
│   │   ├── portfolio.py     ← Wallet: cash, holdings, trade execution
│   │   ├── market.py        ← CoinGecko price feed (60s interval)
│   │   └── db.py            ← SQLite schema & connection
│   └── requirements.txt     ← Python dependencies
│
├── frontend/
│   └── src/
│       ├── App.svelte        ← Main layout: header, price bar, agents, trade log
│       ├── components/
│       │   ├── AgentCard.svelte     ← Per-agent card: wallet, thoughts, trades
│       │   ├── OllamaSetup.svelte   ← Connect to Ollama, pick a model
│       │   ├── AddAgentModal.svelte ← Deploy new agent form
│       │   ├── PriceBar.svelte      ← Live price ticker
│       │   └── TradeLog.svelte      ← All trades table
│       └── lib/
│           ├── ws.js         ← WebSocket store (live data)
│           └── ollama.js     ← Ollama connection store
│
├── bin/
│   └── phantomex            ← CLI script (symlinked to /usr/local/bin)
├── deploy/
│   └── phantomex.service    ← systemd service file (reference copy)
├── data/
│   └── phantomex.db         ← SQLite database (auto-created)
├── install.sh               ← Install CLI on your Mac (run once)
└── start.sh                 ← Dev launcher (local Mac only)
```

---

## CLI Commands

### On Your Mac

```bash
# Install the CLI first (one-time, needs your Mac password)
cd ~/Desktop/Coding/GitHub/PhantomEx
./install.sh

# Then from anywhere:
phantomex              # Start the server
phantomex start        # Same thing
phantomex stop         # Stop the server
phantomex restart      # Restart it
phantomex status       # Is it running?
phantomex logs         # Watch the server output (Ctrl+C to exit)
phantomex build        # Rebuild the frontend after UI changes
```

### Managing timone (Remote Server)

```bash
phantomex server status    # Check if it's running on timone
phantomex server start     # Start it on timone
phantomex server stop      # Stop it on timone
phantomex server restart   # Restart on timone
phantomex server logs      # Stream live logs from timone
phantomex server deploy    # Full deploy: git pull + rebuild + restart
```

### Direct SSH (when you need to debug)

```bash
ssh timone@timone                          # SSH into timone
sudo systemctl status phantomex            # Check service status
sudo systemctl restart phantomex           # Restart service
sudo journalctl -u phantomex -f            # Stream service logs
curl http://localhost:8000/health          # Health check from timone
```

---

## How Agents Work

```
Every 60 seconds:
┌─────────────────────┐
│  CoinGecko prices   │  → 10 coins updated
└────────┬────────────┘
         │ triggers
┌────────▼────────────────────────────────────────────┐
│  For each agent: run_once(prices)                   │
│                                                     │
│  1. Build context:                                  │
│     "BTC: $66,846 ↓1.53%"                          │
│     "ETH: $1,962 ↓2.11%"                           │
│     "Your cash: $4,332 | Holdings: 0.01 BTC"       │
│                                                     │
│  2. Send to Ollama model with system prompt         │
│     (includes agent's goal)                         │
│                                                     │
│  3. Model returns JSON:                             │
│     {"action":"buy","symbol":"BTC",                 │
│      "quantity":0.01,"reasoning":"..."}             │
│                                                     │
│  4. Execute or broadcast (based on mode)            │
│  5. Unload model from GPU immediately               │
└─────────────────────────────────────────────────────┘
```

### Trading Modes

| Mode | Behavior |
|---|---|
| **Autonomous** | Agent trades immediately when it decides to |
| **Advisory** | Agent shows you its decision — you Approve or Reject |

Switch modes by clicking the mode button on any agent card.

### The Wallet

Each agent has:
- **Allowance** — Starting fake money (you set this when deploying)
- **Cash** — What's left after buying positions
- **Holdings** — Crypto positions with quantity + average cost
- **P&L** — Gain/loss vs starting allowance

Click **Wallet ▼** on an agent card to expand the wallet view and use the **+ Deposit** button to add more fake cash at any time.

---

## Database

SQLite file lives at `data/phantomex.db`. Tables:

| Table | What's In It |
|---|---|
| `agents` | Name, model, mode, allowance, goal |
| `portfolios` | Holdings per agent (symbol, quantity, avg cost) |
| `trades` | Every trade ever: side, symbol, quantity, price, reasoning |
| `price_snapshots` | Historical price data |
| `sessions` | Future: session tracking |

---

## Ollama Models on timone

```bash
# SSH to timone and check what's loaded
ssh timone@timone
curl http://localhost:8081/api/tags | python3 -m json.tool
```

Current models:
- `qwen2.5-coder:14b` — Strong reasoning, good at following JSON format
- `gemma3:12b` — Google's model, fast, creative reasoning
- `deepseek-r1:14b` — Shows up in UI (3 models detected)

Add a new model on timone:
```bash
ssh timone@timone
ollama pull llama3.2:3b     # smaller/faster
ollama pull mistral:7b      # another option
```

---

## Making Changes

### Backend change (Python):

```bash
# Edit a file, then:
phantomex server deploy    # pulls git, restarts automatically
```

### Frontend change (Svelte):

```bash
# Edit a file locally, then:
git add . && git commit -m "your message" && git push
phantomex server deploy    # pulls, rebuilds frontend, restarts
```

### Quick local test (Mac):

```bash
phantomex build            # rebuild frontend
phantomex restart          # restart local server
open http://localhost:8000
```

---

## API Endpoints

Hit these directly with `curl` or a browser for debugging:

```
GET  /health                         → {"status":"ok"}
GET  /api/agents                     → all agents + portfolios
POST /api/agents                     → create agent
DELETE /api/agents/{id}              → remove agent
POST /api/agents/{id}/trade          → trigger immediate decision
POST /api/agents/{id}/deposit        → add cash to wallet
PATCH /api/agents/{id}/mode          → switch autonomous/advisory
GET  /api/market/prices              → current prices
GET  /api/trades                     → trade history
GET  /api/ollama/models?host=...     → list Ollama models
```

Example:
```bash
# From timone or your Mac (replace IP):
curl http://192.168.86.51:8000/api/market/prices | python3 -m json.tool
curl http://192.168.86.51:8000/api/agents
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| UI won't load | `phantomex server status` — is it active? |
| No prices showing | CoinGecko rate limit — wait 60s, they reset |
| Ollama not connecting | Check host is `http://localhost:8081` in the panel |
| Agent not trading | Click ⚡ Make Trade to force one cycle immediately |
| Model keeps GPU busy | `keep_alive=0` is set — should release after each trade |
| Changes not showing | Run `phantomex server deploy` to pull + rebuild + restart |
| Service won't start | `ssh timone@timone` → `sudo journalctl -u phantomex -n 50` |

---

## What's Next (Ideas in Progress)

- **Session system** — run agents for a fixed time (1hr, 24hr), then generate a summary
- **Session P&L** — show gain/loss since deployment with a running timer
- **Session summaries** — periodic AI-generated recap of agent activity
- **Real trades** — wire to actual wallets once agents prove themselves
- **Historical replay** — backtest agents against recorded price data
- **Agent leaderboard** — rank agents by P&L across sessions
