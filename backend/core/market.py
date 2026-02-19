"""
Market data layer for PhantomEx.
Supports live CoinGecko prices and historical replay mode.
"""

import asyncio
import httpx
import json
import os
from datetime import datetime
from typing import Callable, Optional
from core.db import get_db

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Map common symbols to CoinGecko IDs
SYMBOL_TO_ID = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "MATIC": "matic-network",
}

DEFAULT_SYMBOLS = list(SYMBOL_TO_ID.keys())


class MarketFeed:
    """
    Streams price data either from CoinGecko (live) or a historical file (replay).
    Calls registered subscribers with each price update batch.
    """

    def __init__(self, mode: str = "live", replay_file: Optional[str] = None, interval: float = 15.0):
        self.mode = mode  # "live" | "replay"
        self.replay_file = replay_file
        self.interval = interval
        self.subscribers: list[Callable] = []
        self._running = False
        self._prices: dict[str, dict] = {}

    def subscribe(self, callback: Callable):
        self.subscribers.append(callback)

    def get_prices(self) -> dict:
        return self._prices

    async def _notify(self, prices: dict):
        self._prices = prices
        for cb in self.subscribers:
            await cb(prices)

    async def _fetch_live(self) -> dict:
        ids = ",".join(SYMBOL_TO_ID.values())
        url = f"{COINGECKO_BASE}/simple/price"
        params = {
            "ids": ids,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_24hr_vol": "true",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            raw = resp.json()

        prices = {}
        id_to_symbol = {v: k for k, v in SYMBOL_TO_ID.items()}
        for cg_id, data in raw.items():
            symbol = id_to_symbol.get(cg_id, cg_id.upper())
            prices[symbol] = {
                "price": data.get("usd", 0),
                "change_24h": data.get("usd_24h_change", 0),
                "volume_24h": data.get("usd_24h_vol", 0),
                "timestamp": datetime.utcnow().isoformat(),
            }
        return prices

    async def _save_snapshot(self, prices: dict):
        with get_db() as conn:
            for symbol, data in prices.items():
                conn.execute(
                    """INSERT INTO price_snapshots (symbol, price, volume_24h, change_24h)
                       VALUES (?, ?, ?, ?)""",
                    (symbol, data["price"], data.get("volume_24h"), data.get("change_24h")),
                )

    async def start(self):
        self._running = True
        if self.mode == "live":
            await self._run_live()
        elif self.mode == "replay":
            await self._run_replay()

    async def stop(self):
        self._running = False

    async def _run_live(self):
        print("[market] Starting live feed...")
        while self._running:
            try:
                prices = await self._fetch_live()
                await self._save_snapshot(prices)
                await self._notify(prices)
            except Exception as e:
                print(f"[market] Error fetching prices: {e}")
            await asyncio.sleep(self.interval)

    async def _run_replay(self):
        if not self.replay_file or not os.path.exists(self.replay_file):
            print(f"[market] Replay file not found: {self.replay_file}")
            return

        print(f"[market] Starting replay from {self.replay_file}...")
        with open(self.replay_file) as f:
            snapshots = json.load(f)  # List of {timestamp, prices: {symbol: {...}}}

        for snap in snapshots:
            if not self._running:
                break
            await self._notify(snap["prices"])
            await asyncio.sleep(self.interval)

        print("[market] Replay complete.")


async def fetch_historical(symbol: str, days: int = 30) -> list[dict]:
    """Fetch OHLC historical data from CoinGecko for charting."""
    cg_id = SYMBOL_TO_ID.get(symbol.upper(), symbol.lower())
    url = f"{COINGECKO_BASE}/coins/{cg_id}/ohlc"
    params = {"vs_currency": "usd", "days": days}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        raw = resp.json()  # [[timestamp_ms, open, high, low, close], ...]

    return [
        {
            "timestamp": datetime.utcfromtimestamp(row[0] / 1000).isoformat(),
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
        }
        for row in raw
    ]
