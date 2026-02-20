"""
PhantomEx TUI — terminal monitor, no frameworks.
Uses curses for raw terminal drawing + asyncio + websockets.

Launch:  phantomex monitor
         python -m tui.monitor [ws://host:port/ws]

Controls: Q or ESC to exit.
"""

import asyncio
import curses
import json
import subprocess
import sys
import time
import threading
from datetime import datetime, timezone
from typing import Optional

import httpx
import websockets


WS_URL  = "ws://localhost:8000/ws"
HTTP_URL = "http://localhost:8000"


# ─── ANSI / curses color pairs ────────────────────────────────────────────────
# Defined in init_colors():
#   1 = green    2 = red     3 = cyan    4 = yellow
#   5 = dim/grey 6 = white   7 = magenta 8 = header blue

def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN,   -1)
    curses.init_pair(2, curses.COLOR_RED,     -1)
    curses.init_pair(3, curses.COLOR_CYAN,    -1)
    curses.init_pair(4, curses.COLOR_YELLOW,  -1)
    curses.init_pair(5, 8,                    -1)  # dark grey (bright black)
    curses.init_pair(6, curses.COLOR_WHITE,   -1)
    curses.init_pair(7, curses.COLOR_MAGENTA, -1)
    curses.init_pair(8, 12,                   -1)  # bright blue for headers

GREEN  = lambda: curses.color_pair(1)
RED    = lambda: curses.color_pair(2)
CYAN   = lambda: curses.color_pair(3)
YELLOW = lambda: curses.color_pair(4)
DIM    = lambda: curses.color_pair(5)
WHITE  = lambda: curses.color_pair(6)
MAG    = lambda: curses.color_pair(7)
BLUE   = lambda: curses.color_pair(8)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _fmt_ts(ts: Optional[str]) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%I:%M %p")
    except Exception:
        return ts[:16]


def _fmt_dur(secs: float) -> str:
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
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


def _query_gpus() -> list:
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,name,temperature.gpu,fan.speed,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4,
        )
        if out.returncode != 0:
            return []
        gpus = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue
            def sf(s):
                try: return float(s)
                except: return None
            gpus.append({"index": int(parts[0]), "name": parts[1],
                         "temp": sf(parts[2]), "fan": sf(parts[3]), "util": sf(parts[4])})
        return gpus
    except Exception:
        return []


def _bar(val, width=10):
    pct = max(0.0, min(1.0, val / 100.0))
    f = round(pct * width)
    return "█" * f + "░" * (width - f)


# ─── safe addstr ─────────────────────────────────────────────────────────────

def _put(win, y, x, text, attr=0):
    """Write text clipped to window width, ignore out-of-bounds."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h - 1 or x >= w:
        return
    avail = w - x - 1
    if avail <= 0:
        return
    try:
        win.addstr(y, x, str(text)[:avail], attr)
    except curses.error:
        pass


def _hline(win, y, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h - 1:
        return
    try:
        win.hline(y, 0, "─", w, attr)
    except curses.error:
        pass


# ─── draw functions ───────────────────────────────────────────────────────────

def draw_header(win, prices: dict, connected: bool):
    h, w = win.getmaxyx()
    win.erase()

    # Title
    _put(win, 0, 0, " ⚡ PhantomEx Monitor", curses.A_BOLD | MAG())
    # Clock
    clock = datetime.now().strftime("%I:%M:%S %p %Z")
    _put(win, 0, w - len(clock) - 2, clock, DIM())
    # Status dot
    status = "● LIVE" if connected else "○ ---"
    sc = GREEN() if connected else RED()
    _put(win, 0, w - len(clock) - len(status) - 4, status, sc | curses.A_BOLD)

    # Price ticker on row 1
    x = 1
    for sym, data in list(prices.items())[:8]:
        price = data.get("price", 0)
        chg   = data.get("change_24h", 0)
        arrow = "▲" if chg >= 0 else "▼"
        col   = GREEN() if chg >= 0 else RED()
        part  = f" {sym} ${price:,.0f} "
        _put(win, 1, x, part, curses.A_BOLD | WHITE())
        x += len(part)
        pct = f"{arrow}{abs(chg):.1f}%  "
        _put(win, 1, x, pct, col)
        x += len(pct)
        if x > w - 20:
            break

    _hline(win, 2, DIM())
    win.noutrefresh()


def draw_gpus(win, gpus: list):
    win.erase()
    _put(win, 0, 0, " GPU STATUS", DIM() | curses.A_BOLD)

    if not gpus:
        _put(win, 1, 2, "nvidia-smi not available", DIM())
    else:
        for i, g in enumerate(gpus):
            row = i + 1
            name = g["name"].replace("NVIDIA GeForce ", "").replace("NVIDIA ", "")[:18]
            temp = g["temp"]
            fan  = g["fan"]
            util = g["util"]

            tc = GREEN() if (temp or 0) < 50 else YELLOW() if (temp or 0) < 75 else RED()
            fc = CYAN()  if (fan  or 0) < 30 else YELLOW() if (fan  or 0) < 70 else RED()

            x = 2
            _put(win, row, x, f"GPU{g['index']} {name:<18}", curses.A_BOLD | WHITE())
            x += 24
            t_str = f"{temp:.0f}°C" if temp is not None else "--°C"
            _put(win, row, x, f"Temp ", DIM())
            _put(win, row, x+5, f"{t_str} ", tc | curses.A_BOLD)
            _put(win, row, x+10, _bar(temp or 0), tc)
            x += 22
            f_str = f"{fan:.0f}%" if fan is not None else "--%"
            _put(win, row, x, f"Fan ", DIM())
            _put(win, row, x+4, f"{f_str} ", fc | curses.A_BOLD)
            _put(win, row, x+9, _bar(fan or 0), fc)
            x += 21
            u_str = f"{util:.0f}%" if util is not None else "--%"
            _put(win, row, x, f"Load ", DIM())
            _put(win, row, x+5, u_str, WHITE() | curses.A_BOLD)

    _hline(win, len(gpus) + 1 if gpus else 2, DIM())
    win.noutrefresh()


def draw_agents(win, agents: dict, prices: dict):
    win.erase()
    h, w = win.getmaxyx()
    _put(win, 0, 0, " ACTIVE AGENTS", DIM() | curses.A_BOLD)

    if not agents:
        _put(win, 2, 2, "No agents deployed — visit the web UI to deploy one.", DIM())
        win.noutrefresh()
        return

    row = 1
    now = time.time()
    for a in agents.values():
        if row >= h - 2:
            break
        port    = a.get("portfolio", {})
        tv      = port.get("total_value", 0)
        cash    = port.get("cash", 0)
        allow   = a.get("allowance", 0)
        pnl     = tv - allow
        ppc     = (pnl / allow * 100) if allow else 0
        risk    = a.get("risk_profile", "neutral")
        running = a.get("running", True)
        started = a.get("started_at")
        max_dur = a.get("max_duration")

        pc = GREEN() if pnl >= 0 else RED()
        sc = GREEN() if running else DIM()
        dot = "●" if running else "○"

        # ── Row 1: name + meta ────────────────────────────────────────────
        _put(win, row, 1, dot, sc | curses.A_BOLD)
        _put(win, row, 3, a.get("name", "?"), curses.A_BOLD | WHITE())
        model = a.get("model", "").split(":")[0]
        x = 3 + len(a.get("name", "?")) + 1
        _put(win, row, x, f" {model}", DIM())
        x += len(model) + 2

        risk_col = RED() if risk == "aggressive" else GREEN() if risk == "safe" else YELLOW()
        _put(win, row, x, f" [{risk}]", risk_col)
        x += len(risk) + 3

        if started:
            elapsed = now - started
            if max_dur:
                pct = elapsed / max_dur
                tc = RED() if pct > 0.75 else YELLOW() if pct > 0.5 else DIM()
                _put(win, row, x, f" ⏱ {_fmt_dur(elapsed)}/{_fmt_dur(max_dur)}", tc)
            else:
                _put(win, row, x, f" ⏱ {_fmt_dur(elapsed)}", DIM())
        row += 1
        if row >= h - 2:
            break

        # ── Row 2: portfolio stats ────────────────────────────────────────
        _put(win, row, 4, "Portfolio ", DIM())
        _put(win, row, 14, _compact(tv), WHITE() | curses.A_BOLD)
        x = 14 + len(_compact(tv)) + 2
        _put(win, row, x, "Cash ", DIM())
        x += 5
        _put(win, row, x, _compact(cash), WHITE())
        x += len(_compact(cash)) + 2
        _put(win, row, x, "P&L ", DIM())
        x += 4
        pnl_str = f"{'+' if pnl>=0 else ''}{_compact(pnl)}  ({'+' if ppc>=0 else ''}{ppc:.1f}%)"
        _put(win, row, x, pnl_str, pc | curses.A_BOLD)
        row += 1
        if row >= h - 2:
            break

        # ── Row 3: holdings ───────────────────────────────────────────────
        holdings = port.get("holdings", {})
        if holdings:
            _put(win, row, 4, "Holdings ", DIM())
            x = 13
            for sym, h in list(holdings.items())[:6]:
                qty      = h.get("quantity", 0)
                avg      = h.get("avg_cost", 0)
                lp       = prices.get(sym, {}).get("price", avg)
                pos_val  = qty * lp
                cost_val = qty * avg
                upnl     = pos_val - cost_val
                upnl_pct = (upnl / cost_val * 100) if cost_val else 0
                uc       = GREEN() if upnl >= 0 else RED()
                sign     = "+" if upnl >= 0 else ""
                chunk    = f"{sym} {qty:.4g} ≈{_compact(pos_val)} {sign}{upnl_pct:.1f}%   "
                if x + len(chunk) > w - 2:
                    break
                _put(win, row, x, sym + " ", CYAN() | curses.A_BOLD)
                _put(win, row, x + len(sym) + 1, f"{qty:.4g} ", WHITE())
                _put(win, row, x + len(sym) + len(f"{qty:.4g}") + 2, f"≈{_compact(pos_val)} ", DIM())
                pct_str  = f"{sign}{upnl_pct:.1f}%   "
                _put(win, row, x + len(sym) + len(f"{qty:.4g}") + 2 + len(f"≈{_compact(pos_val)} "), pct_str, uc)
                x += len(chunk)
            row += 1
            if row >= h - 2:
                break

        # ── Row 4: last thought ───────────────────────────────────────────
        thought = a.get("last_thought")
        if thought:
            act  = thought.get("action", "hold")
            ac   = GREEN() if act == "buy" else RED() if act == "sell" else DIM()
            sym_q = ""
            if thought.get("symbol") and act != "hold":
                sym_q = f" {thought['symbol']} ×{thought.get('quantity','')}"
            ts_str = _fmt_ts(thought.get("timestamp"))
            rsn    = (thought.get("reasoning") or "").strip()
            avail  = w - 6
            rsn    = rsn[:avail] + ("…" if len(rsn) > avail else "")

            _put(win, row, 4, "└ ", DIM())
            _put(win, row, 6, act.upper(), ac | curses.A_BOLD)
            x = 6 + len(act)
            _put(win, row, x, sym_q, WHITE())
            x += len(sym_q)
            _put(win, row, x, f"  {ts_str}", DIM())
            row += 1
            if row < h - 2 and rsn:
                _put(win, row, 6, rsn, DIM())
                row += 1
        else:
            _put(win, row, 4, "└ idle", DIM())
            row += 1

        # spacer between agents
        row += 1

    _hline(win, h - 1, DIM())
    win.noutrefresh()


def draw_trades(win, trades: list):
    win.erase()
    h, w = win.getmaxyx()
    _put(win, 0, 0, " RECENT TRADES", DIM() | curses.A_BOLD)

    shown = [t for t in trades if t.get("side") != "hold"][:h - 2]
    if not shown:
        _put(win, 1, 2, "No trades yet.", DIM())
        win.noutrefresh()
        return

    row = 1
    for t in shown:
        if row >= h - 1:
            break
        side  = t.get("side", "hold")
        sc    = GREEN() if side == "buy" else RED()
        sym   = t.get("symbol") or "—"
        qty   = t.get("quantity", 0)
        price = t.get("price", 0)
        total = t.get("total", 0)
        ts    = _fmt_ts(t.get("timestamp"))
        agent = (t.get("agent_name") or t.get("agent_id","?"))[:12]

        _put(win, row, 1, f"{ts:<10}", DIM())
        _put(win, row, 12, f"{agent:<13}", WHITE())
        _put(win, row, 26, f"{side.upper():<5}", sc | curses.A_BOLD)
        _put(win, row, 32, f"{sym:<5}", CYAN() | curses.A_BOLD)
        _put(win, row, 38, f"{qty:.4f}", WHITE())
        _put(win, row, 48, f"@ ${price:,.2f}", DIM())
        _put(win, row, 62, f"= {_compact(total)}", WHITE())
        row += 1

    win.noutrefresh()


# ─── main monitor loop ────────────────────────────────────────────────────────

class State:
    def __init__(self):
        self.prices:      dict  = {}
        self.agents:      dict  = {}
        self.agent_names: dict  = {}
        self.trades:      list  = []
        self.gpus:        list  = []
        self.connected:   bool  = False
        self.lock = threading.Lock()


def redraw(stdscr, state: State):
    """Partition terminal and redraw all panels."""
    h, w = stdscr.getmaxyx()
    state_copy = (state.prices.copy(), state.agents.copy(),
                  state.trades[:], state.gpus[:], state.connected)
    prices, agents, trades, gpus, connected = state_copy

    # Heights
    hdr_h   = 3
    gpu_h   = max(3, len(gpus) + 2) if gpus else 3
    trade_h = min(12, max(4, len([t for t in trades if t.get("side") != "hold"]) + 2))
    agent_h = max(4, h - hdr_h - gpu_h - trade_h)

    row = 0
    hdr_win   = stdscr.derwin(hdr_h,   w, row, 0); row += hdr_h
    gpu_win   = stdscr.derwin(gpu_h,   w, row, 0); row += gpu_h
    agent_win = stdscr.derwin(agent_h, w, row, 0); row += agent_h
    trade_win = stdscr.derwin(trade_h, w, row, 0)

    draw_header(hdr_win,   prices,  connected)
    draw_gpus  (gpu_win,   gpus)
    draw_agents(agent_win, agents,  prices)
    draw_trades(trade_win, trades)

    curses.doupdate()


async def gpu_loop(state: State):
    while True:
        gpus = await asyncio.get_event_loop().run_in_executor(None, _query_gpus)
        with state.lock:
            state.gpus = gpus
        await asyncio.sleep(5)


async def ws_loop(state: State):
    http_base = HTTP_URL
    while True:
        # Seed from REST
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                a_resp = await client.get(f"{http_base}/api/agents")
                with state.lock:
                    for a in a_resp.json():
                        aid = a.get("id", "")
                        state.agents[aid] = a
                        state.agent_names[aid] = a.get("name", aid[:8])

                t_resp = await client.get(f"{http_base}/api/trades?limit=60")
                raw = t_resp.json()
                with state.lock:
                    for t in raw:
                        aid = t.get("agent_id", "")
                        t["agent_name"] = state.agent_names.get(aid, aid[:8])
                    state.trades = sorted(raw, key=lambda x: x.get("timestamp",""), reverse=True)
        except Exception:
            pass

        # Open WS
        try:
            async with websockets.connect(
                f"{http_base.replace('http','ws')}/ws", open_timeout=5
            ) as ws:
                with state.lock:
                    state.connected = True
                async for raw in ws:
                    msg = json.loads(raw)
                    t   = msg.get("type")
                    with state.lock:
                        if t == "prices":
                            state.prices = msg["data"]
                        elif t == "agent_state":
                            ag  = msg["data"]
                            aid = ag["id"]
                            state.agents[aid] = ag
                            state.agent_names[aid] = ag.get("name", aid[:8])
                        elif t == "agent_removed":
                            state.agents.pop(msg.get("agent_id",""), None)
                        elif t == "trade":
                            tr  = msg["data"]
                            aid = tr.get("agent_id","")
                            tr["agent_name"] = state.agent_names.get(aid, aid[:8])
                            state.trades.insert(0, tr)
                            state.trades = state.trades[:200]
                        elif t == "portfolio":
                            aid = msg.get("agent_id")
                            if aid and aid in state.agents:
                                state.agents[aid]["portfolio"] = msg["data"]
        except Exception:
            with state.lock:
                state.connected = False
            await asyncio.sleep(3)


async def redraw_loop(stdscr, state: State):
    while True:
        with state.lock:
            try:
                redraw(stdscr, state)
            except Exception:
                pass
        await asyncio.sleep(0.5)


async def input_loop(stdscr):
    """Non-blocking key reader — returns when Q/ESC pressed."""
    while True:
        key = stdscr.getch()
        if key in (ord('q'), ord('Q'), 27):  # ESC = 27
            return
        await asyncio.sleep(0.05)


def run(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)   # getch() returns -1 immediately when no key
    stdscr.timeout(0)
    init_colors()
    stdscr.clear()

    state = State()

    async def main():
        tasks = [
            asyncio.create_task(ws_loop(state)),
            asyncio.create_task(gpu_loop(state)),
            asyncio.create_task(redraw_loop(stdscr, state)),
            asyncio.create_task(input_loop(stdscr)),
        ]
        # Exit when input_loop finishes (Q or ESC)
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()

    asyncio.run(main())


def main():
    global HTTP_URL
    if len(sys.argv) > 1:
        # Accept either ws:// or http:// base
        arg = sys.argv[1]
        if arg.startswith("ws://"):
            HTTP_URL = arg.replace("ws://", "http://").rstrip("/ws").rstrip("/")
        elif arg.startswith("http://"):
            HTTP_URL = arg.rstrip("/")
    curses.wrapper(run)


if __name__ == "__main__":
    main()
