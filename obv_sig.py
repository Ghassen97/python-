import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from binance.client import Client
import talib

client = Client()



def get_data(symbol, interval, limit=100):
    raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(raw, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time',
        'quote_asset_volume', 'number_of_trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['close'] = pd.to_numeric(df['close'])
    df['high'] = pd.to_numeric(df['high'])
    df['low'] = pd.to_numeric(df['low'])
    df['volume'] = pd.to_numeric(df['volume'])
    return df[['timestamp', 'close', 'high', 'low', 'volume']]



df = get_data('ETHUSDT', Client.KLINE_INTERVAL_15MINUTE, limit=2000)





# indicators
df['obv'] = talib.OBV(df['close'], df['volume'])
df['obv_fast'] = talib.EMA(df['obv'], timeperiod=6)
df['obv_slow'] = talib.EMA(df['obv'], timeperiod=15)
df['ema21'] = talib.EMA(df['close'], timeperiod=9)

# signal logic
longs, shorts, neutral = [], [], []

for i in range(len(df)):
    obv_fast = df['obv_fast'].iloc[i]
    obv_slow = df['obv_slow'].iloc[i]
    close = df['close'].iloc[i]
    ema = df['ema21'].iloc[i]

    if obv_fast > obv_slow and close > ema:
        longs.append(1)
        shorts.append(0)
        neutral.append(0)
    elif obv_fast < obv_slow and close < ema:
        longs.append(0)
        shorts.append(1)
        neutral.append(0)
    else:
        longs.append(0)
        shorts.append(0)
        neutral.append(1)

df['long_sig'] = longs
df['short_sig'] = shorts
df['neutral_sig'] = neutral

# plot results
plt.figure(figsize=(14, 6))
plt.plot(df['timestamp'], df['close'], label='Close Price', linewidth=1.5, color='black')
plt.scatter(df['timestamp'][df['long_sig'] == 1], df['close'][df['long_sig'] == 1], marker='.', color='green', label='Long', s=80)
plt.scatter(df['timestamp'][df['short_sig'] == 1], df['close'][df['short_sig'] == 1], marker='.', color='red', label='Short', s=80)
plt.title('OBV Strategy Signals')
plt.xlabel('Time')
plt.ylabel('Price')
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
