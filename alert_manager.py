"""Alert manager: formats alerts and dispatches to Telegram (or logs)."""
from __future__ import annotations

import logging
from typing import Callable, Optional

import requests

from crash_detector import Alert

log = logging.getLogger("crashx.alerts")


class AlertManager:
    def __init__(self,
                 telegram_enabled: bool = False,
                 bot_token: str = "",
                 chat_id: str = "",
                 send: Optional[Callable[[str], None]] = None):
        self.telegram_enabled = telegram_enabled
        self.bot_token = bot_token
        self.chat_id = chat_id
        # overridable for tests / offline mode
        self._send = send

    @staticmethod
    def format_message(alert: Alert) -> str:
        time_str = _fmt_time(alert.timestamp)
        lines = [
            "\U0001F6A8 CRYPTO CRASH ALERT",
            "",
            f"Coin: {alert.symbol}",
            f"Drop: {alert.drop_percent:.1f}%",
            f"Window: {_fmt_window(alert.window)}",
            f"Price: {_money(alert.start_price)} -> {_money(alert.end_price)}",
            f"Time: {time_str}",
        ]
        return "\n".join(lines)

    def send(self, alert: Alert) -> None:
        message = self.format_message(alert)
        log.info("ALERT SENT: %s", alert.symbol)
        log.debug(message)

        if self._send is not None:
            try:
                self._send(message)
            except Exception as exc:
                log.warning("Custom sender failed: %s", exc)
            return

        if self.telegram_enabled and self.bot_token and self.bot_token != "PASTE_YOUR_BOT_TOKEN_HERE":
            self._telegram(message)
        # if no Telegram configured, the log above is the only channel.

    def _telegram(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": message,
                      "disable_web_page_preview": True},
                timeout=15,
            )
            if resp.status_code != 200:
                log.warning("Telegram returned %s: %s", resp.status_code, resp.text)
        except Exception as exc:
            log.warning("Telegram send failed: %s", exc)


def _fmt_window(window: str) -> str:
    mapping = {"1m": "1 minute", "5m": "5 minutes", "15m": "15 minutes",
               "1h": "1 hour", "4h": "4 hours", "24h": "24 hours"}
    return mapping.get(window, window)


def _fmt_time(ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M")


def _money(v: float) -> str:
    if v >= 1000:
        return f"${v:,.0f}"
    if v >= 1:
        return f"${v:,.2f}"
    return f"${v:,.4f}"