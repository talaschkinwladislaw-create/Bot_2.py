from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd

# ----------------------------- Einstellungen -----------------------------

QUOTE = "USDT"
TIMEFRAME = "1h"
CANDLE_LIMIT = 220

TOP_PAIRS = 20
TRADE_EUR = 5.0
MAX_OPEN_TRADES = 2
MAX_TRADES_PER_CANDLE = 1

MAX_SPREAD = 0.002             # 0,2 %
MIN_VOLUME_MULTIPLE = 1.5
RSI_MIN, RSI_MAX = 50.0, 70.0

STOP_LOSS_PCT = 0.05           # 5 % unter Einstieg
TRAIL_ACTIVATION_PCT = 0.02     # Aktivierung bei +2 %
TRAIL_DROP_PCT = 0.01           # 1 % unter Hoch nach Aktivierung

DAILY_LOSS_LIMIT_EUR = 1.50
PAUSE_AFTER_WINS = 5
PAUSE_HOURS = 1

# Platzhalter-Schätzungen. Für einen belastbaren Test mit deinen
# tatsächlichen Gebühren und Slippage-Werten ersetzen.
FEE_RATE = 0.001
SLIPPAGE_RATE = 0.001

STATE_FILE = Path("paper_state.json")
STARTING_BALANCE_EUR = 15.0

# Für den Live-Paper-Scanner. Das Skript selbst sendet keine Orders.
PAPER_LOOP_SECONDS = 60

# Für den historischen Backtest:
BACKTEST_DAYS = 90
BACKTEST_START_EUR = 15.0

# ----------------------------- Börsenzugang -----------------------------

exchange = ccxt.kucoin({
    "enableRateLimit": True,
    "options": {"defaultType": "spot"},
})

# ----------------------------- Indikatoren -----------------------------

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi14"] = 100 - (100 / (1 + rs))
    df["rsi14"] = df["rsi14"].fillna(100)

    # Volumen der laufenden Kerze verglichen mit den 20 vorherigen Kerzen.
    df["vol_avg20_prev"] = df["volume"].shift(1).rolling(20).mean()
    df["vol_multiple"] = df["volume"] / df["vol_avg20_prev"]

    return df

def has_entry_signal(row: pd.Series) -> bool:
    values = [
        row.get("close"),
        row.get("ema50"),
        row.get("ema200"),
        row.get("rsi14"),
        row.get("vol_multiple"),
    ]
    if any(pd.isna(value) for value in values):
        return False

    return (
        row["close"] > row["ema50"]
        and row["ema50"] > row["ema200"]
        and RSI_MIN <= row["rsi14"] <= RSI_MAX
        and row["vol_multiple"] >= MIN_VOLUME_MULTIPLE
    )

# ----------------------------- Marktdaten -----------------------------

def get_top_symbols(limit: int = TOP_PAIRS) -> list[str]:
    """Aktuelle Auswahl der volumenstärksten aktiven Spot-USDT-Paare."""
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()

    ranked = []

    for symbol, market in markets.items():
        if not market.get("active", True):
            continue
        if market.get("spot") is not True:
            continue
        if market.get("quote") != QUOTE:
            continue
        if market.get("base") in {"USDT", "USDC", "DAI", "TUSD"}:
            continue

        ticker = tickers.get(symbol) or {}
        quote_volume = ticker.get("quoteVolume")

        if quote_volume is None:
            continue

        try:
            quote_volume = float(quote_volume)
        except (TypeError, ValueError):
            continue

        if quote_volume > 0:
            ranked.append((symbol, quote_volume))

    ranked.sort(key=lambda item: item[1], reverse=True)
    return [symbol for symbol, _ in ranked[:limit]]

def fetch_closed_candles(symbol: str, limit: int = CANDLE_LIMIT) -> pd.DataFrame:
    """Lädt OHLCV und entfernt die noch offene letzte Stundenkerze."""
    rows = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=limit)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

    now = pd.Timestamp.now(tz="UTC")
    current_hour = now.floor("h")
    df = df[df["timestamp"] < current_hour].copy()

    return add_indicators(df).reset_index(drop=True)

def get_spread(symbol: str) -> float | None:
    """Spread als Anteil des Mittelpunkts zwischen Best Bid und Best Ask."""
    try:
        book = exchange.fetch_order_book(symbol, limit=5)
        if not book["bids"] or not book["asks"]:
            return None

        bid = float(book["bids"][0][0])
        ask = float(book["asks"][0][0])
        mid = (bid + ask) / 2

        if mid <= 0:
            return None

        return (ask - bid) / mid
    except Exception as exc:
        print(f"Orderbuchfehler für {symbol}: {exc}")
        return None

# ----------------------------- Paper-Trading -----------------------------

@dataclass
class Position:
    symbol: str
    quantity: float
    entry_price: float
    entry_cost_eur: float
    opened_at: str
    highest_price: float
    trailing_active: bool = False

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {
            "cash_eur": STARTING_BALANCE_EUR,
            "positions": [],
            "realized_today_eur": 0.0,
            "daily_date_utc": datetime.now(timezone.utc).date().isoformat(),
            "consecutive_wins": 0,
            "pause_until": None,
            "last_entry_candle": None,
        }

    with STATE_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)

def save_state(state: dict) -> None:
    with STATE_FILE.open("w", encoding="utf-8") as file:
        json.dump(state, file, indent=2)

def roll_daily_counter(state: dict) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    if state.get("daily_date_utc") != today:
        state["daily_date_utc"] = today
        state["realized_today_eur"] = 0.0
        save_state(state)

def paper_sell(state: dict, position: dict, price: float, reason: str) -> None:
    """Verkauft eine Paper-Position und aktualisiert Gebühren und P/L."""
    gross_value = position["quantity"] * price
    exit_fee = gross_value * FEE_RATE
    proceeds = gross_value - exit_fee

    entry_cost = position["entry_cost_eur"]
    pnl = proceeds - entry_cost

    state["cash_eur"] += proceeds
    state["realized_today_eur"] += pnl

    if pnl > 0:
        state["consecutive_wins"] += 1
    else:
        state["consecutive_wins"] = 0

    print(
        f"VERKAUF {position['symbol']} | {reason} | "
        f"P/L: {pnl:.4f} EUR | Kasse: {state['cash_eur']:.2f} EUR"
    )

    state["positions"].remove(position)

    if state["consecutive_wins"] >= PAUSE_AFTER_WINS:
        pause_until = pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=PAUSE_HOURS)
        state["pause_until"] = pause_until.isoformat()
        state["consecutive_wins"] = 0
        print(f"Pause bis {pause_until.isoformat()}")

    save_state(state)

def manage_positions(state: dict, candle_time: str) -> None:
    """Verwaltet offene Positionen anhand des letzten abgeschlossenen Kurses."""
    for position in list(state["positions"]):
        try:
            df = fetch_closed_candles(position["symbol"], limit=3)
            if df.empty:
                continue

            row = df.iloc[-1]
            price = float(row["close"])
            position["highest_price"] = max(position["highest_price"], price)

            if price >= position["entry_price"] * (1 + TRAIL_ACTIVATION_PCT):
                position["trailing_active"] = True

            stop_price = position["entry_price"] * (1 - STOP_LOSS_PCT)
            trailing_price = (
                position["highest_price"] * (1 - TRAIL_DROP_PCT)
                if position["trailing_active"]
                else None
            )

            # Bei Stundenkerzen ist dies ein Schlusskurs-basierter Ausstieg.
            # Ein schneller Kursrutsch innerhalb der Stunde wird damit nicht
            # exakt simuliert; Live-Systeme brauchen eine separate Überwachung.
            if price <= stop_price:
                paper_sell(state, position, price, "5-%-Stop-Loss")
            elif (
                trailing_price is not None
                and price <= trailing_price
            ):
                paper_sell(state, position, price, "Trailing-Stop")
            else:
                # Trendwechsel-Exit als zusätzliche Regel:
                if (
                    not pd.isna(row["ema50"])
                    and price < row["ema50"]
                ):
                    paper_sell(state, position, price, "Schlusskurs unter EMA 50")
                else:
                    save_state(state)

        except Exception as exc:
            print(f"Positionsprüfung fehlgeschlagen ({position['symbol']}): {exc}")

def marked_to_market_loss_eur(state: dict) -> float:
    """Berechnet den unrealisierten Verlust gegenüber den Einstiegskosten."""
    unrealized = 0.0

    for position in state["positions"]:
        try:
            ticker = exchange.fetch_ticker(position["symbol"])
            price = ticker.get("last")
            if price is None:
                continue

            current_value = position["quantity"] * float(price) * (1 - FEE_RATE)
            unrealized += current_value - position["entry_cost_eur"]
        except Exception as exc:
            print(f"Bewertungsfehler ({position['symbol']}): {exc}")

    return unrealized

def scan_once(state: dict) -> None:
    roll_daily_counter(state)

    # Offene Positionen werden auch während einer Kaufpause verwaltet.
    manage_positions(state, datetime.now(timezone.utc).isoformat())

    unrealized_pnl = marked_to_market_loss_eur(state)
    total_daily_pnl = state["realized_today_eur"] + min(0.0, unrealized_pnl)

    if total_daily_pnl <= -DAILY_LOSS_LIMIT_EUR:
        print(
            f"Tagesverlustlimit erreicht: {total_daily_pnl:.2f} EUR. "
            "Keine neuen Käufe."
        )
        return

    if len(state["positions"]) >= MAX_OPEN_TRADES:
        print("Maximale Anzahl offener Positionen erreicht.")
        return

    pause_until = state.get("pause_until")
    if pause_until:
        if pd.Timestamp.now(tz="UTC") < pd.Timestamp(pause_until):
            print(f"Kaufpause bis {pause_until}")
            return
        state["pause_until"] = None
        save_state(state)

    symbols = get_top_symbols(TOP_PAIRS)
    candidates = []
    current_candle_ids = []

    for symbol in symbols:
        if any(p["symbol"] == symbol for p in state["positions"]):
            continue

        try:
            df = fetch_closed_candles(symbol)
            if len(df) < 205:
                continue

            row = df.iloc[-1]
            candle_id = row["timestamp"].isoformat()
            current_candle_ids.append(candle_id)

            if not has_entry_signal(row):
                continue

            spread = get_spread(symbol)
            if spread is None or spread > MAX_SPREAD:
                continue

            candidates.append(
                {
                    "symbol": symbol,
                    "row": row,
                    "spread": spread,
                    "quote_volume": float(
                        (exchange.fetch_ticker(symbol) or {}).get("quoteVolume") or 0
                    ),
                    "candle_id": candle_id,
                }
            )
        except Exception as exc:
            print(f"Scanfehler für {symbol}: {exc}")

    if not candidates:
        print("Kein passendes Einstiegssignal.")
        return

    # Höchstes 24-h-Quotevolumen unter den Signal-Kandidaten.
    candidates.sort(key=lambda item: item["quote_volume"], reverse=True)
    chosen = candidates[0]

    if state.get("last_entry_candle") == chosen["candle_id"]:
        print("Für diese geschlossene Kerze wurde bereits ein Trade eröffnet.")
        return

    # Euro-Betrag wird für Paper-Trading hier 1:1 als USDT behandelt.
    # Für echte Umrechnung wäre ein EUR/USDT-Kurs nötig.
    stake_eur = TRADE_EUR
    if state["cash_eur"] < stake_eur:
        print("Nicht genügend Paper-Guthaben für eine 5-EUR-Position.")
        return

    price = float(chosen["row"]["close"])
    simulated_buy_price = price * (1 + SLIPPAGE_RATE)
    buy_fee = stake_eur * FEE_RATE
    investable = stake_eur - buy_fee
    quantity = investable / simulated_buy_price

    position = asdict(
        Position(
            symbol=chosen["symbol"],
            quantity=quantity,
            entry_price=simulated_buy_price,
            entry_cost_eur=stake_eur,
            opened_at=chosen["row"]["timestamp"].isoformat(),
            highest_price=simulated_buy_price,
        )
    )

    state["cash_eur"] -= stake_eur
    state["positions"].append(position)
    state["last_entry_candle"] = chosen["candle_id"]
    save_state(state)

    print(
        f"PAPER-KAUF {chosen['symbol']} | Einsatz {stake_eur:.2f} EUR | "
        f"Preis {simulated_buy_price:.8f} | Spread {chosen['spread']:.3%}"
    )

def run_paper_trading() -> None:
    state = load_state()
    print("Paper-Trading gestartet. Es werden keine echten Orders gesendet.")

    while True:
        try:
            scan_once(state)
        except KeyboardInterrupt:
            print("Beendet.")
            save_state(state)
            break
        except Exception as exc:
            print(f"Unerwarteter Fehler: {exc}")

        time.sleep(PAPER_LOOP_SECONDS)

# ----------------------------- Backtest -----------------------------

def fetch_history(symbol: str, since_ms: int, until_ms: int) -> pd.DataFrame:
    """Lädt Stundenkerzen paginiert für einen Zeitraum."""
    all_rows = []
    cursor = since_ms

    while cursor < until_ms:
        rows = exchange.fetch_ohlcv(
            symbol,
            timeframe=TIMEFRAME,
            since=cursor,
            limit=1500,
        )
        if not rows:
            break

        all_rows.extend(rows)
        next_cursor = rows[-1][0] + 60 * 60 * 1000

        if next_cursor <= cursor:
            break

        cursor = next_cursor
        time.sleep(exchange.rateLimit / 1000)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        all_rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df[df["timestamp"] < pd.to_datetime(until_ms, unit="ms", utc=True)]
    return add_indicators(df).reset_index(drop=True)

def backtest() -> None:
    """
    Baseline-Backtest:
    - tägliche Top-20-Auswahl aus dem aktuell verfügbaren Tickervolumen
      wird hier NICHT als historische Rangliste verwendet;
    - stattdessen werden die aktuellen Top-20 über den Testzeitraum getestet.

    Für einen validen historischen Universe-Backtest braucht man historische
    24h-Ticker-Snapshots. KuCoin OHLCV allein enthält diese Rangliste nicht.
    """
    symbols = get_top_symbols(TOP_PAIRS)
    if not symbols:
        raise RuntimeError("Keine Spot-USDT-Paare gefunden.")

    end = pd.Timestamp.now(tz="UTC").floor("h")
    start = end - pd.Timedelta(days=BACKTEST_DAYS)
    since_ms = int(start.timestamp() * 1000)
    until_ms = int(end.timestamp() * 1000)

    print(f"Backtest {start} bis {end}; Paare: {', '.join(symbols)}")
    histories = {}

    for symbol in symbols:
        try:
            df = fetch_history(symbol, since_ms, until_ms)
            if not df.empty:
                histories[symbol] = df
                print(f"{symbol}: {len(df)} Kerzen")
        except Exception as exc:
            print(f"Historienfehler {symbol}: {exc}")

    if not histories:
        raise RuntimeError("Es konnten keine historischen Kerzen geladen werden.")

    # Vereinheitlichte Zeitachse: Signale auf Kerze t, Ausführung am Open von t+1.
    all_times = sorted(
        set(
            ts
            for df in histories.values()
            for ts in df["timestamp"].iloc[1:-1]
        )
    )

    cash = BACKTEST_START_EUR
    positions = {}
    realized_today = 0.0
    current_day = None
    wins_in_row = 0
    pause_until = None
    last_entry_candle = None
    closed_trades = []

    for ts in all_times:
        day = ts.date()
        if current_day != day:
            current_day = day
            realized_today = 0.0

        if pause_until is not None and ts >= pause_until:
            pause_until = None

        # Kerzen dieses Zeitpunkts je Symbol.
        current_rows = {}
        for symbol, df in histories.items():
            match = df.index[df["timestamp"] == ts]
            if len(match):
                current_rows[symbol] = df.iloc[match[0]]

        # Exit-Prüfungen anhand der abgeschlossenen Kerze.
        for symbol in list(positions):
            row = current_rows.get(symbol)
            if row is None:
                continue

            pos = positions[symbol]
            close = float(row["close"])
            pos["high"] = max(pos["high"], float(row["high"]))

            if close >= pos["entry"] * (1 + TRAIL_ACTIVATION_PCT):
                pos["trailing"] = True

            stop = pos["entry"] * (1 - STOP_LOSS_PCT)
            trail = pos["high"] * (1 - TRAIL_DROP_PCT) if pos["trailing"] else None

            reason = None
            if close <= stop:
                reason = "stop"
            elif trail is not None and close <= trail:
                reason = "trailing"
            elif close < row["ema50"]:
                reason = "EMA50"

            if reason:
                sell_price = close * (1 - SLIPPAGE_RATE)
                gross = pos["qty"] * sell_price
                proceeds = gross * (1 - FEE_RATE)
                pnl = proceeds - pos["cost"]
                cash += proceeds
                realized_today += pnl
                closed_trades.append(pnl)

                if pnl > 0:
                    wins_in_row += 1
                else:
                    wins_in_row = 0

                del positions[symbol]

                if wins_in_row >= PAUSE_AFTER_WINS:
                    pause_until = ts + pd.Timedelta(hours=PAUSE_HOURS)
                    wins_in_row = 0

        unrealized = 0.0
        for symbol, pos in positions.items():
            row = current_rows.get(symbol)
            if row is not None:
                unrealized += (
                    pos["qty"] * float(row["close"]) * (1 - FEE_RATE)
                    - pos["cost"]
                )

        if realized_today + min(0.0, unrealized) <= -DAILY_LOSS_LIMIT_EUR:
            continue
        if pause_until is not None and ts < pause_until:
            continue
        if len(positions) >= MAX_OPEN_TRADES:
            continue

        # Signale auf abgeschlossener Kerze t; Ausführung am Open der nächsten.
        candidates = []
        for symbol, row in current_rows.items():
            if symbol in positions or not has_entry_signal(row):
                continue

            df = histories[symbol]
            next_rows = df[df["timestamp"] > ts]
            if next_rows.empty:
                continue

            next_row = next_rows.iloc[0]
            candidates.append((symbol, row, next_row))

        if not candidates:
            continue

        # Proxy für die Auswahl, wenn historische 24h-Ticker-Snapshots fehlen:
        # Kerzenvolumen × Schlusskurs. Dies ist kein exaktes 24h-Quotevolumen.
        candidates.sort(
            key=lambda item: float(item[1]["volume"] * item[1]["close"]),
            reverse=True,
        )

        slots = MAX_OPEN_TRADES - len(positions)
        opened_this_candle = 0

        for symbol, signal_row, next_row in candidates:
            if opened_this_candle >= min(MAX_TRADES_PER_CANDLE, slots):
                break
            if cash < TRADE_EUR:
                break

            entry = float(next_row["open"]) * (1 + SLIPPAGE_RATE)
            stake = TRADE_EUR
            buy_fee = stake * FEE_RATE
            qty = (stake - buy_fee) / entry

            cash -= stake
            positions[symbol] = {
                "entry": entry,
                "qty": qty,
                "cost": stake,
                "high": entry,
                "trailing": False,
            }
            opened_this_candle += 1
            last_entry_candle = ts

    net_liquidation = cash
    for symbol, pos in positions.items():
        df = histories[symbol]
        last_row = df.iloc[-1]
        net_liquidation += (
            pos["qty"] * float(last_row["close"]) * (1 - FEE_RATE)
        )

    total_return = net_liquidation - BACKTEST_START_EUR
    win_rate = (
        sum(1 for pnl in closed_trades if pnl > 0) / len(closed_trades)
        if closed_trades
        else 0.0
    )

    print("\n--- Backtest-Ergebnis ---")
    print(f"Startkapital:       {BACKTEST_START_EUR:.2f} EUR")
    print(f"Endwert:            {net_liquidation:.2f} EUR")
    print(f"Nettogewinn/-verlust:{total_return:+.2f} EUR")
    print(f"Geschlossene Trades:{len(closed_trades)}")
    print(f"Gewinnrate:         {win_rate:.1%}")
    print(f"Offene Positionen:  {len(positions)}")
    print("Achtung: Dieser Backtest nutzt heutige Top-20-Paare als Universum,")
    print("nicht historische tägliche 24h-Ranglisten; Ergebnisse sind daher")
    print("kein belastbarer Nachweis einer profitablen Strategie.")

# ----------------------------- Programmstart -----------------------------

if __name__ == "__main__":
    print("1 = Paper-Trading-Scanner")
    print("2 = Historischer Backtest")
    choice = input("Auswahl: ").strip()

    if choice == "1":
        run_paper_trading()
    elif choice == "2":
        backtest()
    else:
        print("Ungültige Auswahl.")






