"""Rich-based local dashboard displaying each coin's status."""
from __future__ import annotations

import datetime as _dt
from typing import Dict, Optional

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

# canonical window order (matches crash_detector.WINDOW_ORDER)
ALL_WINDOWS = ["1m", "5m", "15m", "1h", "4h", "24h"]


def _pick_windows(thresholds: Dict[str, float]) -> list:
    """Show every configured threshold window, in canonical order."""
    return [w for w in ALL_WINDOWS if w in thresholds]


def _chg_cell(chg: Optional[float], alerted: bool) -> Text:
    if chg is None:
        return Text("N/A", style="dim")
    if alerted:
        return Text(f"{chg:+.2f}%", style="bold red")
    return Text(f"{chg:+.2f}%", style="red" if chg < 0 else "green")


def _fmt_ts(ts: Optional[float]) -> str:
    if not ts:
        return ""
    try:
        return _dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    except Exception:
        return ""


def render_dashboard(coins: list,
                     prices: Dict[str, Optional[float]],
                     changes: Dict[str, Dict[str, Optional[float]]],
                     thresholds: Dict[str, float],
                     alerted: set,
                     title: str = "CRYPTO CRASH DETECTOR",
                     updated_at: Optional[float] = None) -> None:
    windows = _pick_windows(thresholds)

    table = Table(box=box.SIMPLE_HEAVY, expand=False, pad_edge=False)
    table.add_column("Coin", style="bold cyan", no_wrap=True)
    table.add_column("Price", justify="right")
    for w in windows:
        table.add_column(f"{w} chg", justify="right")
    table.add_column("Status", justify="right")

    any_crash = False
    for coin in coins:
        price = prices.get(coin)
        coin_changes = changes.get(coin) or {}
        is_alerted = coin in alerted
        if is_alerted:
            any_crash = True
        status = Text("CRASH", style="bold red") if is_alerted else Text("NORMAL", style="green")
        price_s = f"${price:,.4f}" if price else "N/A"

        row = [coin, price_s]
        for w in windows:
            row.append(_chg_cell(coin_changes.get(w), is_alerted))
        row.append(status)
        table.add_row(*row)

    console.clear()
    console.print(Text(title, style="bold white on dark_blue"), justify="center")
    console.print()
    console.print(table)
    console.print()

    # threshold reference line
    thr_bits = "  ".join(f"{w} >= {abs(thresholds[w]):g}%" for w in windows)
    if thr_bits:
        console.print(Text(f"Thresholds: {thr_bits}", style="dim"), justify="center")

    ts = _fmt_ts(updated_at)
    if ts:
        console.print(Text(f"Last update: {ts}", style="dim"), justify="center")

    console.print()
    overall = (Text("Status: BIG CRASH DETECTED", style="bold red")
               if any_crash else Text("Status: NO BIG CRASH"))
    console.print(overall, justify="center")