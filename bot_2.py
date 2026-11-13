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
    return "KuCoin Trading Bot is running 24/7!"

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# KONFIGURATION DES TRADING-BOTS
# ==========================================
CHECK_INTERVAL = 60  # Zeitabstand in Sekunden
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

# Sauber initialisiert ohne fehlerhafte Platzhalter-Schlüssel
exchange = ccxt.kucoin({
    'enableRateLimit': True,
    'apiKey': '',
    'secret': '',
    'password': ''
})
exchange.set_sandbox_mode(True)
print("--- KUCOIN BOT GESTARTET (SANDBOX-MODUS) ---")

def bot_loop():
    while True:
        try:
            print(f"\n--- Bot-Scan gestartet um {datetime.now()} ---")
            
            try:
                exchange.load_markets()
            except Exception as e:
                print(f"Märkte konnten nicht geladen werden: {e}")
                time.sleep(10)
                continue

            for symbol in SYMBOLS:
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
                    
                    if not ohlcv or not isinstance(ohlcv, list) or len(ohlcv) < 10:
                        print(f"Keine gültigen Daten für {symbol} erhalten.")
                        continue
                    
                    closes = [x[4] for x in ohlcv]
                    current_price = closes[-1]
                    print(f"{symbol} Aktueller Preis: {current_price}")
                    
                except Exception as ex:
                    print(f"Fehler bei Abruf von {symbol}: {ex}")
                
                time.sleep(2)
                
        except Exception as e:
            print(f"Fehler im Hauptloop: {e}")
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    # Webserver im Hintergrund starten
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    # Trading-Bot starten
    bot_loop()


