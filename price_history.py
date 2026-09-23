"""Rolling local price history with multi-timeframe change calculation."""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

Point = Tuple[float, float]  # (timestamp_seconds, price)

# window label -> seconds
WINDOW_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "24h": 86400,
}


class PriceHistory:
    def __init__(self, retention_seconds: int):
        self.retention_seconds = retention_seconds
        self._data: Dict[str, List[Point]] = defaultdict(list)

    def add(self, symbol: str, price: Optional[float], ts: Optional[float] = None) -> None:
        if price is None:
            return
        ts = ts if ts is not None else time.time()
        self._data[symbol].append((ts, float(price)))
        self._trim(symbol, ts)

    def _trim(self, symbol: str, now: float) -> None:
        cutoff = now - self.retention_seconds
        series = self._data[symbol]
        # drop points older than cutoff (keep it cheap: only trim when long)
        if len(series) > 2 and series[0][0] < cutoff:
            self._data[symbol] = [p for p in series if p[0] >= cutoff]

    def latest(self, symbol: str) -> Optional[float]:
        s = self._data.get(symbol)
        return s[-1][1] if s else None

    def price_at_or_before(self, symbol: str, ts: float) -> Optional[float]:
        """Price at the oldest point at or after the requested ts (the point
        closest to 'now - window'). Returns None if not enough history."""
        s = self._data.get(symbol)
        if not s:
            return None
        # If the OLDEST point is newer than ts, we don't have data going back
        # far enough for this window.
        if s[0][0] > ts:
            return None
        # find the last point with timestamp <= ts (at or before the target time)
        result = None
        for t, p in s:
            if t <= ts:
                result = p
            else:
                break
        return result

    def changes(self, symbol: str, now: Optional[float] = None) -> Dict[str, Optional[float]]:
        """Return {window_label: percent_change} for all configured windows.

        Negative percent = drop. Returns None if not enough history.
        """
        now = now if now is not None else time.time()
        s = self._data.get(symbol)
        if not s:
            return {label: None for label in WINDOW_SECONDS}

        current = s[-1][1]
        out: Dict[str, Optional[float]] = {}
        for label, seconds in WINDOW_SECONDS.items():
            past_ts = now - seconds
            ref = self.price_at_or_before(symbol, past_ts)
            if ref is None or ref <= 0:
                # not enough history for this window
                out[label] = None
                continue
            out[label] = (current - ref) / ref * 100.0
        return out