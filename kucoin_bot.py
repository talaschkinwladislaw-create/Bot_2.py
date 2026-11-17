import json
import os
import time
from datetime import datetime
from pathlib import Path

import ccxt

BOT_MODE = os.getenv("BOT_MODE", "paper").strip().lower()
CHECK_INTERVAL = 60
SYMBOLS = ["BTC/EUR", "ETH/EUR", "SOL/EUR"]

STARTING_BALANCE_EUR = 100.00
TRADE_AMOUNT_EUR = 10.00
BUY_THRESHOLD_PCT = 0.005    # 0,5 % Anstieg seit dem letzten Check
SELL_THRESHOLD_PCT = 0.005   # 0,5 % Rückgang seit dem Einstieg
PAPER_STATE_FILE = Path(os.getenv("PAPER_STATE_FILE", "paper_state.json"))

if BOT_MODE not in {"paper", "live"}:
    raise ValueError("BOT_MODE muss 'paper' oder 'live' sein.")

# Für diesen Beispielbot ist nur Paper-Trading implementiert.
if BOT_MODE == "live":
    raise RuntimeError("Live-Handel ist in diesem Beispiel nicht implementiert.")

exchange = ccxt.kraken({"enableRateLimit": True})

def log_message(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

def load_state():
    if PAPER_STATE_FILE.exists():
        try:
            return json.loads(PAPER_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Paper-Statusdatei kann nicht gelesen werden: {exc}") from exc

    return {
        "cash_eur": STARTING_BALANCE_EUR,
        "positions": {},
        "last_prices": {},
    }

def save_state(state):
    PAPER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = PAPER_STATE_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temp_file.replace(PAPER_STATE_FILE)

def paper_buy(state, symbol, price):
    if symbol in state["positions"]:
        return

    amount_eur = min(TRADE_AMOUNT_EUR, state["cash_eur"])
    if amount_eur <= 0:
        log_message("[PAPER] Kein verfügbares Simulationsguthaben für einen Kauf.")
        return

    quantity = amount_eur / price
    state["cash_eur"] -= amount_eur
    state["positions"][symbol] = {
        "quantity": quantity,
        "entry_price": price,
        "cost_eur": amount_eur,
    }

    log_message(
        f"[PAPER-KAUF] {symbol}: {quantity:.8f} Stück zu {price:.2f} EUR "
        f"(Einsatz {amount_eur:.2f} EUR)"
    )

def paper_sell(state, symbol, price):
    position = state["positions"].get(symbol)
    if not position:
        return

    proceeds = position["quantity"] * price
    profit_loss = proceeds - position["cost_eur"]
    state["cash_eur"] += proceeds
    del state["positions"][symbol]

    log_message(
        f"[PAPER-VERKAUF] {symbol}: Erlös {proceeds:.2f} EUR, "
        f"PnL {profit_loss:+.2f} EUR"
    )

def run_bot():
    state = load_state()
    log_message(
        f"Paper-Trading gestartet. Simulationsguthaben: "
        f"{state['cash_eur']:.2f} EUR"
    )

    while True:
        try:
            for symbol in SYMBOLS:
                ticker = exchange.fetch_ticker(symbol)
                price = ticker.get("last")

                if price is None or price <= 0:
                    log_message(f"[{symbol}] Kein gültiger Kurs verfügbar.")
                    continue

                log_message(f"[{symbol}] Kurs: {price:.2f} EUR")
                position = state["positions"].get(symbol)

                if position:
                    entry_price = position["entry_price"]
                    if price <= entry_price * (1 - SELL_THRESHOLD_PCT):
                        paper_sell(state, symbol, price)
                else:
                    previous_price = state["last_prices"].get(symbol)
                    if previous_price and price >= previous_price * (1 + BUY_THRESHOLD_PCT):
                        paper_buy(state, symbol, price)

                state["last_prices"][symbol] = price
                save_state(state)

            position_value = sum(
                pos["quantity"] * state["last_prices"].get(symbol, pos["entry_price"])
                for symbol, pos in state["positions"].items()
            )
            total_value = state["cash_eur"] + position_value

            log_message(
                f"[PAPER] Bargeld: {state['cash_eur']:.2f} EUR | "
                f"Positionen: {position_value:.2f} EUR | "
                f"Gesamtwert: {total_value:.2f} EUR"
            )
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log_message("Bot wurde gestoppt.")
            break
        except Exception as exc:
            log_message(f"[FEHLER] {exc}")
            time.sleep(15)

if __name__ == "__main__":
    run_bot()
