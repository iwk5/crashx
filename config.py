"""Configuration loader for the crash detector."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List

import yaml

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


@dataclass
class Config:
    # coins to monitor (just ticker symbols, e.g. ["BTC", "ETH", "SOL"])
    coins: List[str] = field(default_factory=list)

    # thresholds: label -> percent (e.g. "1m": 5.0)
    thresholds: Dict[str, float] = field(default_factory=dict)

    check_interval: int = 10

    cooldown_enabled: bool = True
    cooldown_recovery_percent: float = 3.0
    cooldown_min_minutes: float = 30.0

    history_retention_minutes: int = 1500

    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    dashboard_enabled: bool = True
    dashboard_title: str = "CRYPTO CRASH DETECTOR"


def load_config(path: str | None = DEFAULT_CONFIG_PATH) -> Config:
    if path is None:
        path = DEFAULT_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    th = raw.get("thresholds", {}) or {}
    cd = raw.get("cooldown", {}) or {}
    tg = raw.get("telegram", {}) or {}
    dash = raw.get("dashboard", {}) or {}

    cfg = Config()

    # coins can be a simple list under "coins" or legacy "coin_ids"
    coins_raw = raw.get("coins") or raw.get("coin_ids") or []
    if isinstance(coins_raw, list):
        cfg.coins = [str(c) for c in coins_raw]
    elif isinstance(coins_raw, dict):
        cfg.coins = list(coins_raw.keys())

    # convert "1m"/"1h"/"24h" -> float percent
    cfg.thresholds = {k: float(v) for k, v in th.items()}

    cfg.check_interval = int(raw.get("check_interval", 10))
    cfg.cooldown_enabled = bool(cd.get("enabled", True))
    cfg.cooldown_recovery_percent = float(cd.get("recovery_percent", 3))
    cfg.cooldown_min_minutes = float(cd.get("min_minutes_between_alerts", 30))

    cfg.history_retention_minutes = int(raw.get("history_retention_minutes", 1500))

    cfg.telegram_enabled = bool(tg.get("enabled", False))
    cfg.telegram_bot_token = str(tg.get("bot_token", "")).strip()
    cfg.telegram_chat_id = str(tg.get("chat_id", "")).strip()

    cfg.dashboard_enabled = bool(dash.get("enabled", True))
    cfg.dashboard_title = dash.get("title", "CRYPTO CRASH DETECTOR")
    return cfg