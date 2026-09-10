import ccxt
import time
import sys
from datetime import datetime

# ==========================================
# KONFIGURATION
# ==========================================
DRY_RUN = False  # False = Live-Handel mit echtem Guthaben
CHECK_INTERVAL = 60  # Zeitabstand in Sekunden zwischen den Durchläufen

# Liste der Top-Kryptowährungen in Euro, die der Bot überwacht
SYMBOLS = ["BTC/EUR", "ETH/EUR", "SOL/EUR"]

# Initialisierung der Kraken-Börse über CCXT mit deinen echten Schlüsseln
exchange = ccxt.kraken({
    'enableRateLimit': True,
    'apiKey': 'WO451YasnHiAMSX+FfmIx3oQxEcvg2Ze3pAvYNfoQBQQNjdP+hu6bkfM',
    'secret': 'udtXeBUhfDU7ED3pU1bVAd2b4sXggO5up1qzH7c0YdHhxvDSlJuM4t1fDzwawd+dxRDVk4Okz2kukiWtuMdzzw=='
})

def log_message(nachricht):
    """Gibt eine Nachricht mit Zeitstempel im Terminal aus und erzwingt die sofortige Anzeige."""
    zeitstempel = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{zeitstempel}] {nachricht}", flush=True)

def startup_abgleich():
    """Führt beim Start den Abgleich mit dem Wallet/Status durch."""
    log_message("[STARTUP] Führe Startup-Reconciliation durch...")
    
    if DRY_RUN:
        log_message("[DRY-RUN] [Simulation] Startup-Reconciliation erfolgreich abgeschlossen.")
    else:
        try:
            # Echte Kontostände bei Kraken abfragen
            balance = exchange.fetch_balance()
            log_message(f"[LIVE] Kontostände erfolgreich abgerufen. Verfügbares EUR-Guthaben: {balance['free'].get('EUR', 0)} €")
        except Exception as e:
            log_message(f"[KRITISCHER FEHLER] Konnte Kontostand nicht abrufen: {e}")

# Hauptschleife starten
startup_abgleich()

while True:
    for symbol in SYMBOLS:
        try:
            log_message(f"[{symbol}] Analysiere Markt...")
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            log_message(f"[{symbol}] Aktueller Kurs: {current_price} €")
        except Exception as e:
            log_message(f"[FEHLER] Konnte Daten für {symbol} nicht abrufen: {e}")
            
    if DRY_RUN:
        log_message("[DRY-RUN] Aktuelles simuliertes Guthaben: 100.00 EUR")
    else:
        log_message("[LIVE] Bot läuft im Live-Modus und überwacht die Märkte.")
        
    time.sleep(CHECK_INTERVAL)
