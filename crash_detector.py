"""Crash detection with per-coin cooldown / anti-spam state."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional

# window label -> seconds (must stay in sync with price_history.WINDOW_SECONDS)
WINDOW_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "24h": 86400,
}
# order for "most severe window first" tie-breaking
WINDOW_ORDER = ["1m", "5m", "15m", "1h", "4h", "24h"]


@dataclass
class Alert:
    symbol: str
    window: str        # e.g. "15m"
    drop_percent: float  # negative, e.g. -10.6
    start_price: float
    end_price: float
    timestamp: float


@dataclass
class _CooldownState:
    last_alert_ts: float
    alert_drop_percent: float  # the drop at alert time (negative)
    pre_crash_price: float     # price before the crash (start_price)
    active: bool = True


class CrashDetector:
    def __init__(self,
                 thresholds: Dict[str, float],
                 cooldown_enabled: bool = True,
                 cooldown_recovery_percent: float = 3.0,
                 cooldown_min_minutes: float = 30.0):
        self.thresholds = thresholds
        self.cooldown_enabled = cooldown_enabled
        self.recovery_percent = cooldown_recovery_percent
        self.min_minutes = cooldown_min_minutes
        self._state: Dict[str, _CooldownState] = {}

    # -- helpers ---------------------------------------------------------
    def _window_label(self, seconds: int) -> str:
        for label, sec in WINDOW_SECONDS.items():
            if sec == seconds:
                return label
        return f"{seconds}s"

    def _reset(self, symbol: str, now: float) -> None:
        self._state[symbol] = _CooldownState(
            last_alert_ts=now, alert_drop_percent=0.0,
            pre_crash_price=0.0, active=False)

    def _cooldown_released(self, state: _CooldownState,
                           current_price: float, now: float) -> bool:
        if not self.cooldown_enabled:
            return True
        minutes_since = (now - state.last_alert_ts) / 60.0
        if minutes_since >= self.min_minutes:
            return True
        # released early if price has recovered above the alert-time price
        if state.pre_crash_price > 0:
            recovery = (current_price - state.pre_crash_price) / state.pre_crash_price * 100.0
            if recovery >= self.recovery_percent:
                return True
        return False

    # -- main API --------------------------------------------------------
    def evaluate(self, symbol: str,
                 changes: Dict[str, Optional[float]],
                 latest_price: Optional[float],
                 now: Optional[float] = None) -> Optional[Alert]:
        """Check all windows for this coin. Returns the single most severe
        triggering Alert (if any and not in cooldown), else None."""
        now = now if now is not None else time.time()
        if latest_price is None:
            return None

        # find the best (most severe) trigger
        best: Optional[Alert] = None
        for label in WINDOW_ORDER:
            if label not in self.thresholds:
                continue
            pct = changes.get(label)
            if pct is None:
                continue
            threshold = self.thresholds[label]
            if pct <= -abs(threshold):
                # start price implied from current + pct
                start_price = latest_price / (1 + pct / 100.0)
                alert = Alert(
                    symbol=symbol, window=label, drop_percent=pct,
                    start_price=start_price, end_price=latest_price,
                    timestamp=now)
                # prefer the largest drop percent
                if best is None or alert.drop_percent < best.drop_percent:
                    best = alert

        if best is None:
            return None

        # cooldown check
        state = self._state.get(symbol)
        if state and state.active and not self._cooldown_released(state, latest_price, now):
            return None  # still the same ongoing crash

        # record / update cooldown
        self._state[symbol] = _CooldownState(
            last_alert_ts=now,
            alert_drop_percent=best.drop_percent,
            pre_crash_price=best.start_price,
            active=True)
        return best

    # -- public query ----------------------------------------------------
    def active_crashes(self,
                       latest_prices: Dict[str, Optional[float]],
                       now: Optional[float] = None) -> set:
        """Return the set of coins whose crash event is still active
        (i.e. not yet released from cooldown).

        A coin is "active" if it has an active cooldown state AND the
        release conditions (min-minutes elapsed OR price recovery) have
        NOT been met yet.
        """
        now = now if now is not None else time.time()
        active: set = set()
        for symbol, state in self._state.items():
            if not state.active:
                continue
            price = latest_prices.get(symbol) or 0.0
            if not self._cooldown_released(state, price, now):
                active.add(symbol)
        return active
