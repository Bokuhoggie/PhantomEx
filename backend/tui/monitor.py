"""
PhantomEx TUI - server-side terminal monitor.
Connects to the running PhantomEx WebSocket and displays live state.
Run with: python -m tui.monitor
"""

import asyncio
import json
from datetime import datetime

import websockets
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Label, Static
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive


WS_URL = "ws://localhost:8000/ws"


class PriceTable(Static):
    prices: reactive[dict] = reactive({})

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]── MARKET PRICES ──[/]")
        yield DataTable(id="price-table")

    def on_mount(self):
        table = self.query_one("#price-table", DataTable)
        table.add_columns("Symbol", "Price", "24h Change")

    def watch_prices(self, prices: dict):
        table = self.query_one("#price-table", DataTable)
        table.clear()
        for symbol, data in prices.items():
            change = data.get("change_24h", 0)
            color = "green" if change >= 0 else "red"
            table.add_row(
                symbol,
                f"${data['price']:,.2f}",
                f"[{color}]{change:+.2f}%[/]",
            )


class AgentTable(Static):
    agents: reactive[list] = reactive([])

    def compose(self) -> ComposeResult:
        yield Label("[bold magenta]── AGENTS ──[/]")
        yield DataTable(id="agent-table")

    def on_mount(self):
        table = self.query_one("#agent-table", DataTable)
        table.add_columns("Name", "Model", "Mode", "Cash", "Portfolio Value")

    def watch_agents(self, agents: list):
        table = self.query_one("#agent-table", DataTable)
        table.clear()
        for agent in agents:
            portfolio = agent.get("portfolio", {})
            table.add_row(
                agent.get("name", "?"),
                agent.get("model", "?"),
                agent.get("mode", "?"),
                f"${portfolio.get('cash', 0):,.2f}",
                f"${portfolio.get('total_value', 0):,.2f}",
            )


class TradeLog(Static):
    trades: reactive[list] = reactive([])

    def compose(self) -> ComposeResult:
        yield Label("[bold yellow]── RECENT TRADES ──[/]")
        yield DataTable(id="trade-table")

    def on_mount(self):
        table = self.query_one("#trade-table", DataTable)
        table.add_columns("Time", "Agent", "Side", "Symbol", "Qty", "Price", "Total")

    def watch_trades(self, trades: list):
        table = self.query_one("#trade-table", DataTable)
        table.clear()
        for t in trades[-20:]:
            side_color = "green" if t.get("side") == "buy" else "red"
            ts = t.get("timestamp", "")[:19].replace("T", " ")
            table.add_row(
                ts,
                t.get("agent_id", "?")[:8],
                f"[{side_color}]{t.get('side', '?').upper()}[/]",
                t.get("symbol", "?"),
                f"{t.get('quantity', 0):.6f}",
                f"${t.get('price', 0):,.2f}",
                f"${t.get('total', 0):,.2f}",
            )


class PhantomExTUI(App):
    CSS = """
    Screen { layout: vertical; }
    PriceTable { height: 1fr; }
    AgentTable { height: 1fr; }
    TradeLog   { height: 1fr; }
    DataTable  { height: 1fr; }
    """

    TITLE = "PhantomEx Monitor"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self):
        super().__init__()
        self._prices = {}
        self._agents = {}
        self._trades = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield PriceTable()
            yield AgentTable()
            yield TradeLog()
        yield Footer()

    def on_mount(self):
        self.run_worker(self._ws_loop(), exclusive=True)

    async def _ws_loop(self):
        async with websockets.connect(WS_URL) as ws:
            async for raw in ws:
                msg = json.loads(raw)
                await self._handle(msg)

    async def _handle(self, msg: dict):
        t = msg.get("type")
        if t == "prices":
            self._prices = msg["data"]
            self.query_one(PriceTable).prices = self._prices
        elif t == "agent_state":
            agent = msg["data"]
            self._agents[agent["id"]] = agent
            self.query_one(AgentTable).agents = list(self._agents.values())
        elif t == "agent_removed":
            self._agents.pop(msg["agent_id"], None)
            self.query_one(AgentTable).agents = list(self._agents.values())
        elif t == "trade":
            self._trades.append(msg["data"])
            self.query_one(TradeLog).trades = list(self._trades)
        elif t == "portfolio":
            agent_id = msg["agent_id"]
            if agent_id in self._agents:
                self._agents[agent_id]["portfolio"] = msg["data"]
                self.query_one(AgentTable).agents = list(self._agents.values())


if __name__ == "__main__":
    PhantomExTUI().run()
