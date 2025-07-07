import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from binance.client import Client
import talib

from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

# setup binance
client = Client()

# get ETHUSDT 15min candles
def get_data(symbol, interval, limit):
    data = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time',
        'qav', 'num_trades', 'tbbav', 'tbqav', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['close'] = pd.to_numeric(df['close'])
    df['high'] = pd.to_numeric(df['high'])
    df['low'] = pd.to_numeric(df['low'])
    df['volume'] = pd.to_numeric(df['volume'])
    return df[['timestamp', 'close', 'high', 'low', 'volume']]

df = get_data('ETHUSDT', Client.KLINE_INTERVAL_15MINUTE, 2000)

# calculate indicators
df['obv'] = talib.OBV(df['close'], df['volume'])
df['obv_fast'] = talib.EMA(df['obv'], 6)
df['obv_slow'] = talib.EMA(df['obv'], 15)
df['ema21'] = talib.EMA(df['close'], 9)
df.dropna(inplace=True)

# pick features and target
features = df[['close', 'obv', 'obv_fast', 'obv_slow', 'ema21']].copy()
target = df['close'].shift(-1)  # predict next candle close

# scale data
scaler_x = MinMaxScaler()
scaler_y = MinMaxScaler()

X_scaled = scaler_x.fit_transform(features)
y_scaled = scaler_y.fit_transform(target.values.reshape(-1, 1))

# make sequences
X = []
y = []
window = 30

for i in range(window, len(X_scaled) - 1):
    X.append(X_scaled[i-window:i])
    y.append(y_scaled[i])

X = np.array(X)
y = np.array(y)

# split train / test
split_index = int(len(X) * 0.8)
X_train = X[:split_index]
X_test = X[split_index:]
y_train = y[:split_index]
y_test = y[split_index:]

# build model
model = Sequential()
model.add(LSTM(64, return_sequences=True, input_shape=(X.shape[1], X.shape[2])))
model.add(Dropout(0.2))
model.add(LSTM(32))
model.add(Dense(1))

model.compile(optimizer='adam', loss='mse')
model.fit(X_train, y_train, epochs=10, batch_size=32, validation_data=(X_test, y_test))

# predict and unscale
predicted = model.predict(X_test)
predicted_unscaled = scaler_y.inverse_transform(predicted)
actual_unscaled = scaler_y.inverse_transform(y_test)

#steping predict line ahead of actual price line 
aligned_preds = np.empty_like(actual_unscaled)
aligned_preds[:] = np.nan
aligned_preds[1:] = predicted_unscaled[:-1]

plt.figure(figsize=(14, 6))
plt.plot(actual_unscaled, label='Actual')
plt.plot(aligned_preds, label='Predicted (Next Step)')
plt.title('LSTM: Next Candle Close Prediction (Shifted)')
plt.xlabel('Time Step')
plt.ylabel('Price')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()
