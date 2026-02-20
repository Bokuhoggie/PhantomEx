"""
PhantomEx TUI — full terminal monitor.
Connects to the running PhantomEx WebSocket and displays live state.

Launch:  phantomex monitor
         python -m tui.monitor [ws://host:port/ws]

Controls: ESC or Q to exit. No other inputs.
"""

import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

import websockets
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Header, Footer, Static, Label


WS_URL = "ws://localhost:8000/ws"


# ─── helpers ─────────────────────────────────────────────────────────────────

def _fmt_ts(ts: Optional[str]) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%I:%M:%S %p")
    except Exception:
        return ts[:19]


def _fmt_dur(secs: float) -> str:
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _compact(n: float) -> str:
    if abs(n) >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"${n/1_000:.1f}k"
    return f"${n:,.2f}"


def _bar(val: float, lo: float, hi: float, width: int = 15) -> str:
    """Render an ASCII progress bar."""
    pct = max(0.0, min(1.0, (val - lo) / (hi - lo) if hi > lo else 0))
    filled = round(pct * width)
    return "█" * filled + "░" * (width - filled)


def _temp_color(t: float) -> str:
    if t < 50:  return "green"
    if t < 75:  return "yellow"
    return "red"


def _fan_color(f: float) -> str:
    if f < 30:  return "cyan"
    if f < 70:  return "yellow"
    return "red"


def _pnl_color(v: float) -> str:
    return "green" if v >= 0 else "red"


def _side_color(side: str) -> str:
    return {"buy": "green", "sell": "red", "hold": "dim"}.get(side, "white")


# ─── GPU polling ─────────────────────────────────────────────────────────────

def query_gpus() -> list:
    """
    Returns list of dicts with keys: index, name, temp, fan, util
    Returns [] if nvidia-smi is not available.
    """
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,temperature.gpu,fan.speed,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=4,
        )
        if out.returncode != 0:
            return []
        gpus = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue

            def safe_float(s):
                try:
                    return float(s)
                except (ValueError, TypeError):
                    return None

            gpus.append({
                "index": int(parts[0]),
                "name":  parts[1],
                "temp":  safe_float(parts[2]),
                "fan":   safe_float(parts[3]),
                "util":  safe_float(parts[4]),
            })
        return gpus
    except Exception:
        return []


# ─── Widgets ─────────────────────────────────────────────────────────────────

class TickerBar(Static):
    """Single-line price ticker."""
    prices: reactive[dict] = reactive({})

    def render(self) -> str:
        if not self.prices:
            return "[dim]  Waiting for market data…[/]"
        parts = []
        for sym, data in self.prices.items():
            price = data.get("price", 0)
            chg   = data.get("change_24h", 0)
            arrow = "▲" if chg >= 0 else "▼"
            color = "green" if chg >= 0 else "red"
            parts.append(
                f"[bold white]{sym}[/] [white]${price:,.2f}[/] "
                f"[{color}]{arrow}{abs(chg):.2f}%[/]"
            )
        return "   ".join(parts) + "   [dim]● LIVE[/]"


class GpuPanel(Static):
    """One row per GPU showing temp + fan bar."""
    gpus: reactive[list] = reactive([])

    def compose(self) -> ComposeResult:
        yield Label("[bold dim]── GPU STATUS ─────────────────────────────────────────────────────────────[/]")
        yield Static(id="gpu-body")

    def watch_gpus(self, gpus: list) -> None:
        body = self.query_one("#gpu-body")
        if not gpus:
            body.update("[dim]  nvidia-smi not available — GPU monitoring disabled[/]")
            return
        lines = []
        for g in gpus:
            name = g["name"].replace("NVIDIA GeForce ", "").replace("NVIDIA ", "")
            temp = g["temp"]
            fan  = g["fan"]
            util = g["util"]
            tc = _temp_color(temp) if temp is not None else "dim"
            fc = _fan_color(fan)   if fan  is not None else "dim"
            t_str = f"[{tc}]{temp:.0f}°C[/]"  if temp is not None else "[dim]--°C[/]"
            f_str = f"[{fc}]{fan:.0f}%[/]"    if fan  is not None else "[dim]--%[/]"
            u_str = f"[white]{util:.0f}%[/]"  if util is not None else "[dim]--%[/]"
            t_bar = f"[{tc}]{_bar(temp or 0, 0, 100)}[/]" if temp is not None else "[dim]" + "░"*15 + "[/]"
            f_bar = f"[{fc}]{_bar(fan  or 0, 0, 100)}[/]" if fan  is not None else "[dim]" + "░"*15 + "[/]"
            lines.append(
                f"  [bold]GPU {g['index']}[/] [dim]{name:<22}[/]  "
                f"Temp {t_str} {t_bar}  "
                f"Fan {f_str} {f_bar}  "
                f"Load {u_str}"
            )
        body.update("\n".join(lines))


class AgentPanel(Static):
    """Live agent list with portfolio state and last thought."""
    agents: reactive[dict] = reactive({})

    def compose(self) -> ComposeResult:
        yield Label("[bold dim]── AGENTS ─────────────────────────────────────────────────────────────────[/]")
        yield Static(id="agent-body")

    def watch_agents(self, agents: dict) -> None:
        body = self.query_one("#agent-body")
        if not agents:
            body.update("[dim]  No agents deployed — visit the web UI to deploy one.[/]")
            return
        lines = []
        now = time.time()
        for a in agents.values():
            port    = a.get("portfolio", {})
            tv      = port.get("total_value", 0)
            cash    = port.get("cash", 0)
            allow   = a.get("allowance", 0)
            pnl     = tv - allow
            ppc     = (pnl / allow * 100) if allow else 0
            pc      = _pnl_color(pnl)
            risk    = a.get("risk_profile", "neutral")
            risk_ic = {"aggressive": "🔴", "safe": "🟢", "neutral": "⚪"}.get(risk, "⚪")
            running = a.get("running", True)
            started = a.get("started_at")
            max_dur = a.get("max_duration")

            status = "[green]●[/]" if running else "[dim]○[/]"

            timer_str = ""
            if started:
                elapsed = now - started
                if max_dur:
                    pct = elapsed / max_dur
                    col = "red" if pct > 0.75 else "yellow" if pct > 0.5 else "white"
                    timer_str = f"  [dim]⏱[/][{col}]{_fmt_dur(elapsed)}[/][dim]/{_fmt_dur(max_dur)}[/]"
                else:
                    timer_str = f"  [dim]⏱ {_fmt_dur(elapsed)}[/]"

            # Holdings (top 3 by quantity)
            holdings = port.get("holdings", {})
            hold_parts = []
            for sym, h in list(holdings.items())[:4]:
                hold_parts.append(f"[cyan]{sym}[/][white] {h['quantity']:.3f}[/]")
            hold_str = "  ".join(hold_parts) if hold_parts else "[dim]no holdings[/]"

            # Last thought
            thought = a.get("last_thought")
            if thought:
                act   = thought.get("action", "hold").upper()
                act_c = _side_color(thought.get("action", "hold"))
                sym_q = ""
                if thought.get("symbol") and thought.get("action") != "hold":
                    sym_q = f" {thought['symbol']} ×{thought.get('quantity', '')}"
                ts  = _fmt_ts(thought.get("timestamp"))
                rsn = (thought.get("reasoning") or "")[:90]
                thought_line = (
                    f"     [dim]└[/] [{act_c}]{act}[/][white]{sym_q}[/] "
                    f"[dim]{ts}[/]\n"
                    f"       [dim italic]{rsn}…[/]" if len(rsn) == 90 else
                    f"     [dim]└[/] [{act_c}]{act}[/][white]{sym_q}[/] "
                    f"[dim]{ts}[/]\n"
                    f"       [dim italic]{rsn}[/]"
                )
            else:
                thought_line = "     [dim]└ idle[/]"

            pnl_str = (
                f"[{pc}]{'+' if pnl>=0 else ''}{pnl:,.0f}[/] "
                f"[dim]([/][{pc}]{'+' if ppc>=0 else ''}{ppc:.1f}%[/][dim])[/]"
            )

            lines.append(
                f"\n  {status} [bold white]{a['name']}[/]"
                f"  [dim]{a.get('model','').split(':')[0]}[/]"
                f"  {risk_ic}[dim]{risk}[/]{timer_str}\n"
                f"     [dim]Portfolio[/] [white]{_compact(tv)}[/]  "
                f"[dim]Cash[/] [white]{_compact(cash)}[/]  "
                f"[dim]P&L[/] {pnl_str}\n"
                f"     {hold_str}"
            )
            lines.append(thought_line)

        body.update("\n".join(lines))


class TradePanel(Static):
    """Last 20 trades, newest first."""
    trade_list: reactive[list] = reactive([])

    def compose(self) -> ComposeResult:
        yield Label("[bold dim]── TRADE LOG ───────────────────────────────────────────────────────────────[/]")
        yield Static(id="trade-body")

    def watch_trade_list(self, trades: list) -> None:
        body = self.query_one("#trade-body")
        if not trades:
            body.update("[dim]  No trades yet.[/]")
            return
        lines = []
        for t in trades[:20]:
            side  = t.get("side", "hold")
            sc    = _side_color(side)
            sym   = t.get("symbol") or "—"
            qty   = t.get("quantity", 0)
            price = t.get("price", 0)
            total = t.get("total", 0)
            ts    = _fmt_ts(t.get("timestamp"))
            agent = (t.get("agent_name") or t.get("agent_id", "?"))[:12]
            if side == "hold":
                lines.append(
                    f"  [dim]{ts}[/]  [dim]{agent:<12}[/]  [{sc}]{side.upper():<4}[/]"
                )
            else:
                lines.append(
                    f"  [dim]{ts}[/]  [dim]{agent:<12}[/]  [{sc}]{side.upper():<4}[/]  "
                    f"[cyan]{sym:<5}[/] [white]{qty:.4f}[/]  "
                    f"[dim]@[/] [white]${price:,.2f}[/]  "
                    f"[dim]=[/] [white]{_compact(total)}[/]"
                )
        body.update("\n".join(lines))


# ─── App ─────────────────────────────────────────────────────────────────────

class PhantomExMonitor(App):
    """PhantomEx terminal monitor. Press Q or ESC to exit."""

    CSS = """
    Screen {
        background: #030308;
        layout: vertical;
    }
    TickerBar {
        height: 1;
        background: #0a0a1a;
        border-bottom: solid #1a1a3a;
        padding: 0 1;
        content-align: left middle;
    }
    GpuPanel {
        height: auto;
        min-height: 4;
        background: #06060f;
        border-bottom: solid #1a1a3a;
        padding: 0 1 1 1;
    }
    AgentPanel {
        height: 1fr;
        background: #08080f;
        border-bottom: solid #1a1a3a;
        padding: 0 1;
        overflow-y: auto;
    }
    TradePanel {
        height: 12;
        background: #06060f;
        padding: 0 1 1 1;
        overflow-y: auto;
    }
    Label {
        color: #2a2a4a;
        padding: 0 0;
        height: 1;
    }
    Footer {
        background: #0a0a1a;
    }
    """

    BINDINGS = [
        Binding("q",      "quit", "Quit", show=True),
        Binding("escape", "quit", "Quit", show=False),
    ]

    TITLE = "⚡ PhantomEx Monitor"

    def __init__(self, ws_url: str = WS_URL):
        super().__init__()
        self._ws_url       = ws_url
        self._prices: dict = {}
        self._agents: dict = {}
        self._trades: list = []
        self._agent_names: dict = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield TickerBar()
        yield GpuPanel()
        yield AgentPanel()
        yield TradePanel()
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._ws_loop(),  exclusive=True, name="ws")
        self.run_worker(self._gpu_loop(), exclusive=True, name="gpu")

    async def _gpu_loop(self) -> None:
        while True:
            gpus = await asyncio.get_event_loop().run_in_executor(None, query_gpus)
            self.query_one(GpuPanel).gpus = list(gpus)
            await asyncio.sleep(5)

    async def _ws_loop(self) -> None:
        http_base = self._ws_url.replace("ws://", "http://").replace("/ws", "")
        while True:
            try:
                async with websockets.connect(self._ws_url, open_timeout=5) as ws:
                    # Seed trades from REST
                    try:
                        import httpx
                        async with httpx.AsyncClient(timeout=5) as client:
                            resp = await client.get(f"{http_base}/api/trades?limit=100")
                            raw = resp.json()
                            for t in raw:
                                aid = t.get("agent_id", "")
                                t["agent_name"] = self._agent_names.get(aid, aid[:8])
                            self._trades = sorted(raw, key=lambda x: x.get("timestamp", ""), reverse=True)
                            self.query_one(TradePanel).trade_list = list(self._trades)
                    except Exception:
                        pass

                    async for raw in ws:
                        self._handle(json.loads(raw))

            except Exception:
                await asyncio.sleep(3)

    def _handle(self, msg: dict) -> None:
        t = msg.get("type")

        if t == "prices":
            self._prices = msg["data"]
            self.query_one(TickerBar).prices = dict(self._prices)

        elif t == "agent_state":
            agent = msg["data"]
            aid   = agent["id"]
            self._agents[aid] = agent
            self._agent_names[aid] = agent.get("name", aid[:8])
            self.query_one(AgentPanel).agents = dict(self._agents)

        elif t == "agent_removed":
            self._agents.pop(msg.get("agent_id", ""), None)
            self.query_one(AgentPanel).agents = dict(self._agents)

        elif t == "trade":
            trade = msg["data"]
            aid   = trade.get("agent_id", "")
            trade["agent_name"] = self._agent_names.get(aid, aid[:8])
            self._trades.insert(0, trade)
            self._trades = self._trades[:200]
            self.query_one(TradePanel).trade_list = list(self._trades)

        elif t == "portfolio":
            aid = msg.get("agent_id")
            if aid and aid in self._agents:
                self._agents[aid]["portfolio"] = msg["data"]
                self.query_one(AgentPanel).agents = dict(self._agents)


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else WS_URL
    PhantomExMonitor(ws_url=url).run()


if __name__ == "__main__":
    main()
