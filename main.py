"""Main entry point for the Crypto Big-Crash Detector."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Optional

from alert_manager import AlertManager
from config import Config, load_config
from crash_detector import CrashDetector
from dashboard import render_dashboard
from price_collector import BinanceCollector
from price_history import PriceHistory


def setup_logging(quiet: bool = False) -> None:
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


def run(cfg: Config,
        collector: Optional[BinanceCollector] = None,
        alert_mgr: Optional[AlertManager] = None,
        max_iterations: Optional[int] = None,
        quiet: bool = False) -> None:
    setup_logging(quiet)
    log = logging.getLogger("crashx.main")

    coins = cfg.coins
    if not coins:
        log.error("No coins configured. Edit config.yaml -> price_source.coin_ids")
        return

    collector = collector or BinanceCollector(coins=cfg.coins)
    log.info("Price source: Binance")
    history = PriceHistory(retention_seconds=cfg.history_retention_minutes * 60)

    # Seed local history from Binance 1m klines (~8h of data)
    # so that 15m / 1h / 4h windows are available on first render.
    for coin in coins:
        try:
            points = collector.fetch_history(coin, limit=500)
            for ts, price in points:
                history.add(coin, price, ts)
            if points:
                log.info("Seeded %d history points for %s", len(points), coin)
        except Exception as e:
            log.warning("History seeding failed for %s: %s", coin, e)

    detector = CrashDetector(
        thresholds=cfg.thresholds,
        cooldown_enabled=cfg.cooldown_enabled,
        cooldown_recovery_percent=cfg.cooldown_recovery_percent,
        cooldown_min_minutes=cfg.cooldown_min_minutes,
    )
    alert_mgr = alert_mgr or AlertManager(
        telegram_enabled=cfg.telegram_enabled,
        bot_token=cfg.telegram_bot_token,
        chat_id=cfg.telegram_chat_id,
    )

    log.info("Monitoring %d coins: %s", len(coins), ", ".join(coins))
    log.info("Thresholds: %s", ", ".join(f"{k}={v}%" for k, v in cfg.thresholds.items()))

    iteration = 0
    try:
        while True:
            now = time.time()

            # Single API call returns current prices + 24h change %
            prices, market_changes = collector.fetch()
            changes: dict = {}
            for coin in coins:
                price = prices.get(coin)
                if price is not None:
                    history.add(coin, price, now)
                # local history covers 1m/5m/15m/1h/4h (once enough samples
                # accumulate); 24h comes from the API when available.
                ch = dict(history.changes(coin, now))
                mc = market_changes.get(coin, {}) or {}
                for key in ("1h", "24h"):
                    val = mc.get(key)
                    if val is not None:
                        ch[key] = val
                changes[coin] = ch

                latest = history.latest(coin)
                alert = detector.evaluate(coin, ch, latest, now)
                if alert:
                    alert_mgr.send(alert)

            # Public query for coins still in an active (unreleased) crash.
            alerted = detector.active_crashes(prices, now)

            if cfg.dashboard_enabled and not quiet:
                render_dashboard(coins, prices, changes, cfg.thresholds, alerted,
                                 title=cfg.dashboard_title,
                                 updated_at=now)

            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                break
            time.sleep(cfg.check_interval)
    except KeyboardInterrupt:
        log.info("Interrupted — shutting down.")
    finally:
        log.info("Bye. (iterations=%d)", iteration)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crypto Big-Crash Detector")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--no-dashboard", action="store_true",
                        help="Disable the live dashboard (log only)")
    parser.add_argument("--quiet", action="store_true", help="Reduce log output")
    parser.add_argument("--once", action="store_true",
                        help="Run a single check then exit (useful for testing)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.no_dashboard:
        cfg.dashboard_enabled = False
    run(cfg, max_iterations=1 if args.once else None, quiet=args.quiet)


if __name__ == "__main__":
    main()