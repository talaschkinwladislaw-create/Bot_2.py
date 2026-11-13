import ccxt
import time
import sys
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
    # Render weist automatisch einen Port über die Umgebungsvariable 'PORT' zu
    app.run(host='0.0.0.0', port=10000)

# ==========================================
# KONFIGURATION DEINES TRADING-BOTS
# ==========================================
TEST_MODE = True  # True = Test-Modus (Sandbox), False = Echtgeld
CHECK_INTERVAL = 60  # Zeitabstand in Sekunden zwischen den Scans

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

# KuCoin API-Schlüssel
exchange = ccxt.kucoin({
    'enableRateLimit': True,
    'apiKey': '6af7...',          # Deine echten KuCoin Keys
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
            for symbol in SYMBOLS:
                try:
                    # Kursdaten holen
                    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
                    if not ohlcv or len(ohlcv) < 30:
                        continue
                    
                    closes = [x[4] for x in ohlcv]
                    current_price = closes[-1]
                    print(symbol, "Aktueller Preis:", current_price)
                    
                except Exception as ex:
                    print(f"Fehler bei {symbol}: {ex}")
                
                time.sleep(0.5)
                
        except Exception as e:
            print(f"Fehler im Hauptloop: {e}")
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    # Starte den Webserver in einem separaten Hintergrund-Thread, damit Render glücklich ist
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    # Starte den eigentlichen Trading-Bot
    bot_loop()
