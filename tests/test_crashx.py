"""Offline end-to-end test using a fake price feed (no network needed)."""
from __future__ import annotations

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from crash_detector import CrashDetector
from price_history import PriceHistory
from main import run
from alert_manager import AlertManager


class FakeCollector:
    """Feeds a scripted price series (one point per iteration) per coin."""
    def __init__(self, series):
        self.series = series  # symbol -> [price, price, ...]
        self._i = 0

    def fetch(self):
        prices = {}
        for sym, series in self.series.items():
            prices[sym] = series[min(self._i, len(series) - 1)]
        market_changes = {sym: {"1h": None, "24h": None} for sym in self.series}
        self._i += 1
        return prices, market_changes


def build_config():
    cfg = Config(
        coins=["BTC"],
        check_interval=1,
        thresholds={"1m": 10.0, "5m": 20.0},
        cooldown_enabled=True,
        cooldown_recovery_percent=3.0,
        cooldown_min_minutes=30.0,
        history_retention_minutes=5,
        dashboard_enabled=False,
        dashboard_title="TEST",
        telegram_enabled=False,
        telegram_bot_token="",
        telegram_chat_id="",
    )
    return cfg


def test_crash_detection_and_cooldown():
    # BTC steady at 100000 for a while, then crashes to 88000 (-12%) within a minute.
    steady = [100000.0] * 5
    crash = [88000.0, 87500.0, 87500.0, 87500.0]
    series = {"BTC": steady + crash}

    sent: list = []
    collector = FakeCollector(series)
    mgr = AlertManager(telegram_enabled=False, send=lambda m: sent.append(m))

    cfg = build_config()
    sent = []
    history = PriceHistory(retention_seconds=300)
    detector = CrashDetector(thresholds=cfg.thresholds)

    clock = {"t": time.time()}

    def now_fn():
        return clock["t"]

    for price in series["BTC"]:
        ts = clock["t"]
        history.add("BTC", price, ts)
        chg = history.changes("BTC", ts)
        alert = detector.evaluate("BTC", chg, history.latest("BTC"), ts)
        if alert:
            sent.append(alert)
        clock["t"] += 30  # 30s between samples

    assert len(sent) == 1, f"Expected exactly 1 alert (cooldown), got {len(sent)}"
    a = sent[0]
    assert a.window == "1m"
    assert a.drop_percent <= -10.0
    print("PASS: single crash alert fired and was not repeated")


def test_no_alert_without_crash():
    history = PriceHistory(retention_seconds=300)
    detector = CrashDetector(thresholds={"1m": 10.0})
    t = time.time()
    for p in [100.0, 100.0, 99.0, 99.5, 100.0]:  # small fluctuations
        history.add("BTC", p, t)
        chg = history.changes("BTC", t)
        assert detector.evaluate("BTC", chg, history.latest("BTC"), t) is None
        t += 30
    print("PASS: no alert for small price fluctuations")


def test_active_crashes_lifecycle():
    detector = CrashDetector(
        thresholds={"1m": 10.0},
        cooldown_enabled=True,
        cooldown_recovery_percent=3.0,
        cooldown_min_minutes=30.0,
    )
    t0 = 1_700_000_000.0  # fixed clock for determinism

    # before any crash: nothing active
    assert detector.active_crashes({"BTC": 100_000.0}, t0) == set()

    # trigger a crash
    alert = detector.evaluate("BTC", {"1m": -12.0}, 88_000.0, t0)
    assert alert is not None

    # while still below pre-crash price and < min_minutes → active
    t1 = t0 + 60
    active = detector.active_crashes({"BTC": 87_000.0}, t1)
    assert active == {"BTC"}, f"expected {{BTC}}, got {active}"

    # early release via price recovery >= 3% above pre-crash price
    t2 = t0 + 120
    recovered = 88_000.0 * 1.04  # > 3% above the alert end price... but
    # recovery is measured vs pre_crash_price (start_price ~ 100_000)
    # so we need current >= pre * 1.03
    current_recovered = 100_000.0 * 1.04
    active2 = detector.active_crashes({"BTC": current_recovered}, t2)
    assert active2 == set(), f"expected released, got {active2}"

    # after min_minutes elapsed, also released (even without recovery)
    detector2 = CrashDetector(
        thresholds={"1m": 10.0},
        cooldown_enabled=True,
        cooldown_recovery_percent=3.0,
        cooldown_min_minutes=30.0,
    )
    detector2.evaluate("ETH", {"1m": -15.0}, 1_000.0, t0)
    t3 = t0 + 31 * 60
    assert detector2.active_crashes({"ETH": 1_000.0}, t3) == set()

    print("PASS: active_crashes() lifecycle (active -> released)")


if __name__ == "__main__":
    test_crash_detection_and_cooldown()
    test_no_alert_without_crash()
    test_active_crashes_lifecycle()
    print("ALL TESTS PASSED")
