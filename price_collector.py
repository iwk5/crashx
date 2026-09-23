"""Price collector — Binance backend (no API key needed).

Symbols are just tickers like "BTC", "ETH", "SOL".
The pair is auto-derived as  SYMBOL + "USDT"  (e.g. "BTCUSDT").
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

FetchResult = Tuple[Dict[str, Optional[float]], Dict[str, Dict[str, Optional[float]]]]
HistoryPoint = Tuple[float, float]


class BinanceCollector:
    """Binance public REST API — no key required.

    * Prices + 24h change:  GET /api/v3/ticker/24hr?symbols=[...]  (1 call)
    * History seeding:      GET /api/v3/klines?symbol=BTCUSDT&interval=1m
    """

    BASE = "https://api.binance.com"

    def __init__(self, coins: List[str], timeout: int = 20):
        self.coins = list(coins)
        self.timeout = timeout
        self._pair_to_sym: Dict[str, str] = {}
        for c in self.coins:
            pair = f"{c}USDT"
            self._pair_to_sym[pair] = c

    # ------------------------------------------------------------------
    def fetch(self) -> FetchResult:
        """One batch call → (prices, market_changes)."""
        pairs = [f"{c}USDT" for c in self.coins]
        url = f"{self.BASE}/api/v3/ticker/24hr"
        # NOTE: Binance rejects whitespace in the `symbols` array, so we must
        # use compact JSON separators (no spaces after commas/colons).
        params = {"symbols": json.dumps(pairs, separators=(",", ":"))}

        try:
            r = requests.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning("Binance fetch failed: %s", e)
            return ({c: None for c in self.coins},
                    {c: {"1h": None, "24h": None} for c in self.coins})

        prices: Dict[str, Optional[float]] = {}
        market_changes: Dict[str, Dict[str, Optional[float]]] = {}

        for entry in data:
            sym = self._pair_to_sym.get(entry.get("symbol", ""))
            if sym is None:
                continue
            prices[sym] = float(entry["lastPrice"])
            market_changes[sym] = {
                "1h": None,  # not in 24hr ticker — use local history
                "24h": float(entry["priceChangePercent"]),
            }

        # fill any missing coins
        for c in self.coins:
            prices.setdefault(c, None)
            market_changes.setdefault(c, {"1h": None, "24h": None})

        return prices, market_changes

    # ------------------------------------------------------------------
    def fetch_history(self, symbol: str, limit: int = 500) -> List[HistoryPoint]:
        """Fetch 1-min klines → [(ts_seconds, close_price), ...].

        500 candles ≈ 8 h, enough to cover the 15m / 1h / 4h windows
        on the very first dashboard render.
        """
        pair = f"{symbol}USDT"
        url = f"{self.BASE}/api/v3/klines"
        params = {"symbol": pair, "interval": "1m", "limit": limit}

        try:
            r = requests.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning("Binance klines fetch failed for %s: %s", symbol, e)
            return []

        return [(k[0] / 1000.0, float(k[4])) for k in data]