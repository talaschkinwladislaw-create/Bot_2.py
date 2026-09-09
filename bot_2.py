import ccxt
import time
from datetime import datetime

# ==========================================
# KONFIGURATION
# ==========================================
DRY_RUN = True  # True = Simulation mit Spielgeld, False = Echtgeld auf Kraken
CHECK_INTERVAL = 60  # Zeitabstand in Sekunden zwischen den Durchläufen

# Liste der Top-Kryptowährungen in Euro, die der Bot überwachen soll
SYMBOLS = ["BTC/EUR", "ETH/EUR", "SOL/EUR"]

# Initialisierung der Kraken-Börse über CCXT
exchange = ccxt.kraken({
    'enableRateLimit': True,
})

def log_message(message):
    """Gibt eine Nachricht mit Zeitstempel im Terminal aus."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def startup_reconciliation():
    """Führt beim Start den Abgleich mit dem Wallet/Status durch."""
    log_message("[STARTUP] Führe Startup-Reconciliation durch...")
    
    if DRY_RUN:
        log_message("[DRY-RUN] [Simulation] Startup-Reconciliation erfolgreich abgeschlossen.")
    else:
        try:
            # Echte Kontostände bei Kraken abfragen
            balance = exchange.fetch_balance()
            log_message("[LIVE] Kontostände erfolgreich von Kraken geladen.")
        except Exception as e:
            log_message(f"[KRITISCHER FEHLER] Konnte Kontostand nicht abrufen: {e}")

def run_bot():
    """Hauptschleife des Bots"""
    log_message("Bot initialisiert. Starte Multi-Asset-Überwachung...")
    
    startup_reconciliation()
    
    # Simuliertes Guthaben für den Start im Dry-Run
    simulated_balance_eur = 100.00

    while True:
        try:
            log_message("--------------------------------------------------")
            for symbol in SYMBOLS:
                log_message(f"[{symbol}] Analysiere Markt...")
                
                # Aktuellen Ticker (Preis) von Kraken abrufen
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                
                log_message(f"[{symbol}] Aktueller Kurs: {current_price} €")
                
                # HIER WIRD SPÄTER DEINE STRATEGIE EINGEFÜGT
                # Beispiel: Prüfen ob gekauft werden soll
                
            if DRY_RUN:
                log_message(f"[DRY-RUN] Aktuelles simuliertes Guthaben: {simulated_balance_eur:.2f} €")
            
            # Warten bis zum nächsten Intervall
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            log_message("Bot wurde vom Benutzer manuell gestoppt.")
            break
        except Exception as e:
            log_message(f"[FEHLER im Hauptlauf]: {e}")
            time.sleep(15)  # Bei Fehler kurz warten und dann fortfahren

if __name__ == "__main__":
    run_bot()
