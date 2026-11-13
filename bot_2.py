import ccxt
import time
import sys
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
# KONFIGURATION DEINES TRADING-BOTS
# ==========================================
TEST_MODE = True  # True = Test-Modus (Sandbox), False = Echtgeld
CHECK_INTERVAL = 60  # Zeitabstand in Sekunden

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

# KuCoin API-Schlüssel
exchange = ccxt.kucoin({
    'enableRateLimit': True,
    'apiKey': '6af7...',
    'secret': 'c0b5...',
    'password': 'Wladislaw203312'
})

if TEST_MODE:
    exchange.set_sandbox_mode(True)
    print("--- KUCOIN BOT GESTARTET IM SANDBOX (TEST) MODUS ---")
else:
    print("--- ACHTUNG: KUCOIN BOT IM LIVE-HANDEL MODUS ---")

def bot_loop():
    while True:
        try:
            print(f"\n--- Bot-Scan gestartet um {datetime.now()} ---")
            
            # Märkte sicher laden mit Fehlerbehandlung
            try:
                exchange.load_markets()
            except Exception as e:
                print(f"Konnte Märkte nicht laden: {e}")
                time.sleep(10)
                continue

            for symbol in SYMBOLS:
                try:
                    # Kursdaten sicher abrufen und auf NoneType prüfen
                    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
                    
                    if ohlcv is None or not isinstance(ohlcv, list) or len(ohlcv) < 30:
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
    # Webserver im Hintergrund starten (für Render Port-Binding)
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    # Trading-Bot starten
    bot_loop()

