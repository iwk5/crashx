# CrashX — Crypto Big-Crash Detector

A real-time detector for **big drops in crypto prices**. It polls the public **Binance** API (no API key required), tracks each coin's change across multiple timeframes (1m → 24h), and raises an **alert** the moment any coin drops more than its configured threshold within a given window.

- Pure Python 3.10+
- Read-only: uses **public** market data only — never places orders
- Pluggable alerting (Telegram, or log-only)
- Live terminal dashboard rendered with [Rich](https://github.com/Textualize/rich)
- Per-coin anti-spam cooldown with early release on price recovery

---

## How it works

```
                ┌──────────────────────────────┐
   public REST  │        price_collector       │
  ────────────► │  BinanceCollector.fetch()    │  1 batch call / interval
                └──────────────┬───────────────┘
                               │  prices + 24h change
                               ▼
                ┌──────────────────────────────┐
                │         price_history        │  rolling local series
                │  (per coin, retention cap)   │  → 1m/5m/15m/1h/4h change %
                └──────────────┬───────────────┘
                               ▼
                ┌──────────────────────────────┐
                │        crash_detector        │  for each window: if
                │  thresholds + cooldown state │  change ≤ -threshold
                └──────────────┬───────────────┘        → Alert
                               ▼
                ┌──────────────────────────────┐
                │         alert_manager        │  format → Telegram / log
                └──────────────┬───────────────┘
                               ▼
                ┌──────────────────────────────┐
                │          dashboard          │  Rich table: coin, price,
                │   (terminal, per interval)  │  per-window %, CRASH/NORMAL
                └──────────────────────────────┘
```

**Modules**

| File | Role |
|------|------|
| `main.py` | Entry point. Runs the polling loop (`check_interval` seconds), wires everything together, handles CLI flags. |
| `price_collector.py` | `BinanceCollector` — one batch REST call returns current prices + 24h change for all coins. Also fetches 1m klines to seed local history. |
| `price_history.py` | Rolling per-coin time series with a retention cap. Computes change % across the 1m/5m/15m/1h/4h/24h windows. |
| `crash_detector.py` | `CrashDetector` — checks every configured window against its threshold, returns the single most-severe triggering `Alert`. Tracks per-coin cooldown state. |
| `alert_manager.py` | Formats an alert and dispatches it (Telegram, or an injectable sender for tests; falls back to logging). |
| `dashboard.py` | `render_dashboard` — draws a Rich table: coin, price, per-window change %, and a CRASH/NORMAL status per row. |
| `config.py` | Loads `config.yaml` (with sensible defaults) and exposes a typed `Config`. |
| `config.yaml` | User-facing configuration (coins, thresholds, polling, cooldown, Telegram, dashboard). |

---

## Crash detection algorithm

For each coin the detector evaluates **every configured window** independently. A window triggers an alert when:

```
change_pct(window)  ≤  -threshold(window)
```

where `change_pct` is the percent change over that window (negative = drop) and the threshold is the configured value for that window (see `config.yaml`). If multiple windows trigger, the **most severe** (largest drop) alert wins.

**Sources of change %**

- `1m / 5m / 15m / 1h / 4h` — computed locally from `price_history` (seeded on startup with ~8h of Binance 1m klines so longer windows are available immediately).
- `24h` — taken directly from Binance's `/ticker/24hr` endpoint (no need to keep 24h of local samples).

**Anti-spam / cooldown** (per coin)

After a coin alerts, it stays in an **active** state and will not alert again until **either**:

- the price recovers by `cooldown.recovery_percent`% (default 3%) above the pre-crash price, **or**
- `cooldown.min_minutes_between_alerts` minutes (default 30) have elapsed.

Coins that are still in an active crash are reported as `CRASH` in the dashboard; all others as `NORMAL`.

---

## Quick start

### 1. Install

```bat
pip install -r requirements.txt
```

Python 3.10+ required. Dependencies: `requests`, `rich`, `pyyaml`, `pytest` (dev).

### 2. Configure (optional)

Edit `config.yaml`:

```yaml
coins: [BTC, ETH, SOL, BNB, LINK, LTC, SUI, APT, TAO, FET]

thresholds:        # min drop % per window to trigger
  1m: 5
  5m: 7
  15m: 10
  1h: 15
  4h: 20
  24h: 30

check_interval: 30          # seconds between polls

cooldown:
  enabled: true
  recovery_percent: 3       # release early if price recovers this %
  min_minutes_between_alerts: 30

history_retention_minutes: 1500   # >= 24h so the 24h window works locally

telegram:
  enabled: true
  bot_token: "PASTE_YOUR_BOT_TOKEN_HERE"
  chat_id: "PASTE_YOUR_CHAT_ID_HERE"

dashboard:
  enabled: true
  title: "CRYPTO CRASH DETECTOR"
```

> **Telegram**: create a bot with [@BotFather](https://t.me/BotFather), copy the token, then message your bot once and get your `chat_id` from `https://api.telegram.org/bot<TOKEN>/getUpdates`. Leave `telegram.enabled: false` (or use the placeholders) to fall back to log-only alerts.

### 3. Run

```bat
start.bat
```

or directly:

```bat
python main.py                 # normal run (dashboard + alerts)
python main.py --no-dashboard  # log-only
python main.py --once          # single check then exit (smoke test)
python main.py --quiet         # reduce log noise
```

---

## Configuration reference (`config.yaml`)

| Key | Default | Meaning |
|-----|---------|---------|
| `coins` | `[BTC, ETH, SOL, BNB, ...]` | Tickers to monitor. Pairs are auto-derived as `<coin>USDT`. |
| `thresholds.<window>` | see above | Minimum drop % (positive) that triggers an alert for that window. |
| `check_interval` | `10` | Seconds between price polls. |
| `cooldown.enabled` | `true` | Toggle per-coin anti-spam. |
| `cooldown.recovery_percent` | `3` | % price must recover above the pre-crash price to release early. |
| `cooldown.min_minutes_between_alerts` | `30` | Hard minimum minutes between two alerts on the same coin. |
| `history_retention_minutes` | `1500` | How long local price history is kept. Keep ≥ the longest threshold window. |
| `telegram.enabled` | `false` | Send alerts to Telegram (falls back to log when disabled). |
| `telegram.bot_token` | placeholder | Telegram bot token. |
| `telegram.chat_id` | placeholder | Target chat/user id. |
| `dashboard.enabled` | `true` | Draw the live terminal dashboard. |
| `dashboard.title` | `CRYPTO CRASH DETECTOR` | Title shown above the table. |

---

## Project layout

```
crashx/
├── main.py              # entry point + polling loop + CLI
├── price_collector.py   # Binance public REST (prices + klines)
├── price_history.py     # rolling local time series, multi-window change %
├── crash_detector.py    # threshold check + per-coin cooldown
├── alert_manager.py     # alert formatting + Telegram dispatch
├── dashboard.py         # Rich terminal dashboard
├── config.py            # config loader
├── config.yaml          # user configuration
├── requirements.txt
├── start.bat            # Windows launcher
└── tests/test_crashx.py # unit tests
```

## Run the tests

```bat
python -m pytest tests/ -q
```

---

## Notes & limitations

- **Binance only** (single source). Adding another exchange means writing a new collector and wiring it into `main.py`/`price_history`.
- **Binance geo-restrictions**: if your region cannot reach `api.binance.com`, the collector logs a warning and prices show as `N/A` until it recovers.
- **Read-only**: no trading, no API key needed.
- **Cross-platform**: pure Python + terminal. The GUI/dashboard is a terminal table, so it runs on Windows, macOS, and Linux.