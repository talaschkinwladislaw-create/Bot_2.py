import os
import time
from datetime import datetime

import ccxt

# ==========================================
# KONFIGURATION
# ==========================================
BOT_MODE = os.getenv("BOT_MODE", "paper").strip().lower()
DRY_RUN = BOT_MODE == "paper"
CHECK_INTERVAL = 60

SYMBOLS = ["BTC/EUR", "ETH/EUR", "SOL/EUR"]

if BOT_MODE not in {"paper", "live"}:
    raise ValueError(
        f"Unbekannter BOT_MODE={BOT_MODE!r}. Erlaubt sind: 'paper' oder 'live'."
    )

exchange = ccxt.kraken({
    "enableRateLimit": True,
})

def log_message(message):
    """Gibt eine Nachricht mit Zeitstempel im Terminal aus."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

def startup_reconciliation():
    """Führt beim Start den Abgleich mit dem Wallet/Status durch."""
    log_message("[STARTUP] Führe Startup-Reconciliation durch...")

    if DRY_RUN:
        log_message("[PAPER] Simulationsmodus aktiv; es werden keine Echtgeld-Orders ausgeführt.")
        return

    try:
        balance = exchange.fetch_balance()
        log_message("[LIVE] Kontostände erfolgreich von Kraken geladen.")
    except Exception as e:
        raise RuntimeError(f"Kontostand konnte nicht von Kraken abgerufen werden: {e}") from e

def run_bot():
    """Hauptschleife des Bots."""
    log_message(f"Bot gestartet. Modus: {BOT_MODE}. Überwache: {', '.join(SYMBOLS)}")

    startup_reconciliation()
    simulated_balance_eur = 100.00

    while True:
        try:
            log_message("--------------------------------------------------")

            for symbol in SYMBOLS:
                log_message(f"[{symbol}] Analysiere Markt...")

                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker.get("last")

                if current_price is None:
                    log_message(f"[{symbol}] Kein letzter Kurs verfügbar.")
                    continue

                log_message(f"[{symbol}] Aktueller Kurs: {current_price} EUR")

                # Hier kann später die Handelsstrategie ergänzt werden.
                # Dieser Code erteilt derzeit keine Kauf- oder Verkaufsorders.

            if DRY_RUN:
                log_message(
                    f"[PAPER] Simuliertes Guthaben: {simulated_balance_eur:.2f} EUR"
                )

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log_message("Bot wurde gestoppt.")
            break
        except Exception as e:
            log_message(f"[FEHLER im Hauptlauf]: {e}")
            time.sleep(15)

if __name__ == "__main__":
    run_bot()







