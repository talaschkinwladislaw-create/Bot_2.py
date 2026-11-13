import time
import os
import threading
from datetime import datetime
import requests
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
SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]  # KuCoin Public API nutzt Bindestrich

def get_kucoin_price(symbol):
    try:
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("code") == "200000" and data.get("data"):
            price = float(data["data"]["price"])
            return price
    except Exception as e:
        print(f"Fehler beim Abrufen von {symbol}: {e}")
    return None

def bot_loop():
    while True:
        try:
            print(f"\n--- Bot-Scan gestartet um {datetime.now()} ---")
            
            for symbol in SYMBOLS:
                price = get_kucoin_price(symbol)
                if price:
                    print(f"{symbol} Aktueller Preis: {price} USDT")
                else:
                    print(f"Keine Daten für {symbol} erhalten.")
                
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



