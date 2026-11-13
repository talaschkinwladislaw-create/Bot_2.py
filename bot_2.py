import ccxt
import time
import os
import threading
from datetime import datetime
from flask import Flask

# ==========================================
# MINIMALER WEB-SERVER FÜR RENDER PORT-BINDING
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "KuCoin Live Trading Bot is running 24/7!"

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# ECHTGELD-KONFIGURATION (LIVE MODUS)
# ==========================================
CHECK_INTERVAL = 300  # Alle 5 Minuten prüfen
SYMBOLS = ["BTC/USDT", "ETH/USDT"]

# Der Code holt sich deine Schlüssel sicher aus den Render-Einstellungen
exchange = ccxt.kucoin({
    'enableRateLimit': True,
    'apiKey': os.environ.get('KUCOIN_API_KEY'),
    'secret': os.environ.get('KUCOIN_SECRET'),
    'password': os.environ.get('KUCOIN_PASSWORD')
})

# LIVE-MODUS AKTIVIEREN
exchange.set_sandbox_mode(False)
print("--- 🚨 KUCOIN BOT IM ECHTGELD (LIVE) MODUS AKTIVIERT 🚨 ---")

def bot_loop():
    while True:
        try:
            print(f"\n--- Live-Handels-Scan gestartet um {datetime.now()} ---")
            
            # 1. Kontostand abrufen
            try:
                balance = exchange.fetch_balance()
                usdt_free = balance['free'].get('USDT', 0)
                print(f"Verfügbares USDT-Guthaben: {usdt_free} USDT")
            except Exception as e:
                print(f"Fehler beim Abrufen des Kontostands (Schlüssel in Render prüfen!): {e}")
                time.sleep(30)
                continue

            # 2. Märkte und Preise prüfen
            for symbol in SYMBOLS:
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                    print(f"{symbol} Live-Preis: {current_price} USDT")
                    
                    # --- HIER DEINE KAUF-/VERKAUFSLOGIK EINFÜGEN ---
                    
                except Exception as ex:
                    print(f"Fehler bei Preisabfrage für {symbol}: {ex}")
                
                time.sleep(3)
                
        except Exception as e:
            print(f"Fehler im Live-Hauptloop: {e}")
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    bot_loop()





