import ccxt
import pandas as pd
import time
import requests
from datetime import datetime

# ==========================================
# KONFIGURATION
# ==========================================
TEST_MODE = True  # True = Simulation (sicher), False = Echter Handel mit echtem Geld!

# 1. Deine KuCoin API Zugangsdaten (eingefügt)
API_KEY = "6af742dfbd1a8f000177d214"
API_SECRET = "c0b5a3b4-8356-4fb0-a523-331531722805"
API_PASSWORD = "Wladislaw203312"

# 2. Telegram Benachrichtigungen (Optional - kannst du leer lassen)
TELEGRAM_TOKEN = "" 
TELEGRAM_CHAT_ID = ""

# 3. Trading Parameter
TRADE_AMOUNT_USDT = 15.0   # Investition pro Trade in USDT
MAX_OPEN_TRADES = 3        # Maximal gleichzeitig gehaltene Coins
TOP_N_COINS = 10           # Die 10 volumenstärksten Coins analysieren
TAKE_PROFIT_PCT = 0.03     # +3.0% Gewinnziel
STOP_LOSS_PCT = -0.02      # -2.0% Verlustbegrenzung
TIMEFRAME = '15m'          # Kerzen-Intervall ('5m', '15m', '1h')

# ==========================================
# INITIALISIERUNG
# ==========================================
exchange = ccxt.kucoin({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'password': API_PASSWORD,
    'enableRateLimit': True,
})

active_positions = {}

def send_telegram(message):
    """Sendet eine Nachricht an deinen Telegram-Chat."""
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"Telegram-Fehler: {e}")

# ==========================================
# TECHNISCHE ANALYSE (RSI, EMA, Bollinger, MACD)
# ==========================================
def calculate_indicators(symbol):
    """Lädt Kerzendaten und berechnet alle Indikatoren."""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # 1. EMA 50 (Trendfilter)
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # 2. RSI 14 (Momentum)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 3. Bollinger-Bänder (20, 2)
    df['sma20'] = df['close'].rolling(window=20).mean()
    df['std20'] = df['close'].rolling(window=20).std()
    df['lower_band'] = df['sma20'] - (df['std20'] * 2)
    df['upper_band'] = df['sma20'] + (df['std20'] * 2)
    
    # 4. MACD (12, 26, 9)
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp12 - exp26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    return {
        'close': latest['close'],
        'rsi': latest['rsi'],
        'ema50': latest['ema50'],
        'lower_band': latest['lower_band'],
        'upper_band': latest['upper_band'],
        'macd_hist': latest['macd_hist'],
        'prev_macd_hist': prev['macd_hist']
    }

def get_most_popular_coins(limit=10):
    """Findet die beliebtesten USDT-Coins nach 24h-Handelsvolumen."""
    tickers = exchange.fetch_tickers()
    usdt_pairs = []
    excluded = ['USDC/USDT', 'FDUSD/USDT', 'TUSD/USDT', 'DAI/USDT', 'EUR/USDT']
    
    for symbol, data in tickers.items():
        if symbol.endswith('/USDT') and symbol not in excluded:
            if '3L/' not in symbol and '3S/' not in symbol:
                quote_vol = data.get('quoteVolume')
                if quote_vol is not None:
                    usdt_pairs.append((symbol, float(quote_vol)))
                    
    usdt_pairs.sort(key=lambda x: x[1], reverse=True)
    return [pair[0] for pair in usdt_pairs[:limit]]

# ==========================================
# ORDER-AUSFÜHRUNG
# ==========================================
def execute_buy(symbol, current_price):
    amount = round(TRADE_AMOUNT_USDT / current_price, 6)
    msg = f"🟢 **KAUFSIGNAL**\nCoin: `{symbol}`\nPreis: `{current_price} USDT`\nModus: `{'TEST' if TEST_MODE else 'LIVE'}`"
    print(f"[{datetime.now()}] {msg}")
    send_telegram(msg)
    
    if not TEST_MODE:
        try:
            order = exchange.create_market_buy_order(symbol, amount)
            print(f" -> Echte Order platziert: {order['id']}")
        except Exception as e:
            err_msg = f"❌ **Fehler beim Kauf von {symbol}**: {e}"
            print(err_msg)
            send_telegram(err_msg)
            return
            
    active_positions[symbol] = {
        'buy_price': current_price,
        'amount': amount
    }

def execute_sell(symbol, current_price, reason):
    pos = active_positions[symbol]
    profit_pct = ((current_price - pos['buy_price']) / pos['buy_price']) * 100
    msg = f"🔴 **VERKAUF** ({reason})\nCoin: `{symbol}`\nPreis: `{current_price} USDT`\nGewinn/Verlust: `{profit_pct:+.2f}%`"
    print(f"[{datetime.now()}] {msg}")
    send_telegram(msg)
    
    if not TEST_MODE:
        try:
            order = exchange.create_market_sell_order(symbol, pos['amount'])
            print(f" -> Echte Verkaufs-Order platziert: {order['id']}")
        except Exception as e:
            err_msg = f"❌ **Fehler beim Verkauf von {symbol}**: {e}"
            print(err_msg)
            send_telegram(err_msg)
            return
            
    del active_positions[symbol]

# ==========================================
# HAUPTSCHLEIFE
# ==========================================
def run_bot():
    start_msg = f"🚀 KuCoin Bot gestartet!\nTest-Modus: `{TEST_MODE}`\nZeitrahmen: `{TIMEFRAME}`"
    print(start_msg)
    send_telegram(start_msg)
    
    while True:
        try:
            # 1. Aktive Positionen überwachen
            for symbol in list(active_positions.keys()):
                ind = calculate_indicators(symbol)
                buy_price = active_positions[symbol]['buy_price']
                change = (ind['close'] - buy_price) / buy_price
                
                if change >= TAKE_PROFIT_PCT:
                    execute_sell(symbol, ind['close'], "Take-Profit (+3%)")
                elif change <= STOP_LOSS_PCT:
                    execute_sell(symbol, ind['close'], "Stop-Loss (-2%)")
                elif ind['rsi'] > 75:
                    execute_sell(symbol, ind['close'], f"RSI überkauft ({ind['rsi']:.1f})")
                elif ind['close'] >= ind['upper_band']:
                    execute_sell(symbol, ind['close'], "Oberes Bollinger-Band")
                elif ind['macd_hist'] < 0 and ind['prev_macd_hist'] >= 0:
                    execute_sell(symbol, ind['close'], "MACD Momentum gedreht")
                
                time.sleep(0.5)

            # 2. Nach neuen Kaufsignalen suchen
            if len(active_positions) < MAX_OPEN_TRADES:
                popular_coins = get_most_popular_coins(TOP_N_COINS)
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Analysiere Top-{TOP_N_COINS} Coins...")
                
                for symbol in popular_coins:
                    if symbol in active_positions or len(active_positions) >= MAX_OPEN_TRADES:
                        continue
                        
                    ind = calculate_indicators(symbol)
                    print(f"  {symbol:10s} | Preis: {ind['close']:8.4f} | RSI: {ind['rsi']:4.1f} | MACD Hist: {ind['macd_hist']:6.4f}")
                    
                    # Kauf-Bedingungen
                    is_rsi_low = ind['rsi'] < 35
                    is_above_ema = ind['close'] > ind['ema50']
                    is_at_lower_band = ind['close'] <= (ind['lower_band'] * 1.01)
                    macd_bullish_cross = ind['macd_hist'] > 0 and ind['prev_macd_hist'] <= 0
                    
                    if is_rsi_low and is_above_ema and (is_at_lower_band or mac_bullish_cross):
                        execute_buy(symbol, ind['close'])
                        
                    time.sleep(0.5)

            time.sleep(60)

        except Exception as e:
            print(f"Fehler in Hauptschleife: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run_bot()

