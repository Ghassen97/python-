from binance import Client
import logging
from binance.exceptions import BinanceAPIException

import pandas as pd
import numpy as np
import talib
import time
# from telegram import Bot

class Trader:
    def __init__(self, api_key, api_secret):
        self.binance_client = Client(api_key, api_secret)
        self.set_leverage(10)

        self.max_trade_pnl   = 0
        self.entered_long    = False
        self.entered_short   = False
        self.entry_price     = 0
        self.current_pnl     = 0
        self.exit_threshold  = 0
        self.pnl_threshold   = 10
        self.stop_loss       = 32

        try:
            self.TOKEN       = ""
            self.CHANNEL_ID  = ""
            #self.bot         = Bot(token=self.TOKEN)
        except Exception as e:
            logging.error(f"Error while initializing the telegram bot: {e}")
            self.bot = None  


    def send_message(self, text: str):
        try:
            if self.bot:
                self.bot.send_message(chat_id=self.CHANNEL_ID, text=text)
            else:
                logging.error("Bot not initialized. Can't send message.")
        except Exception as e:
            logging.error(f"Error while sending message: {e}")


    def set_leverage(self, leverage):
        try:
            self.leverage = self.binance_client.futures_change_leverage(
                symbol='1000000BOBUSDT', leverage=leverage)
        except BinanceAPIException:
            logging.error("Binance API Exception occurred")


    def fetch_data(self,
                   interval=Client.KLINE_INTERVAL_15MINUTE,         
                   lookback="1 day ago UTC"):                       
        try:
            klines = self.binance_client.futures_historical_klines(
                "1000000BOBUSDT",
                interval,                                        
                lookback)                                         
            df = pd.DataFrame(klines,
                columns=['opentime', 'open', 'high', 'low', 'close',
                         'volume', 'close time', 'Quote_asset_volume',
                         'Number of trades', 'Taker buy base asset volume',
                         'Taker buy quote asset volume', 'Ignore'])
            df = df.astype({'close': float, 'open': float, 'high': float,
                            'low': float, 'volume': float})
        except BinanceAPIException:
            logging.error("Binance API Exception occurred")
            df = pd.DataFrame()
        return df


    def calculate_indicators(self, df):
        smaclose       = talib.SMA(df.close, 5)
        obv            = talib.OBV(smaclose, df['volume'])
        df['obv']      = obv
        df['obvsma']   = talib.EMA(df['obv'], 15)
        df['obvs']     = talib.EMA(df['obv'], 6)
        df['ema21']    = talib.EMA(df.close, 17)

        
        return df


    def get_live_price(self):
        df = self.fetch_data()
        return df['close'].iloc[-1] if not df.empty else 0.0

    def display_live_price(self, refresh_interval=1):
        while True:
            live_price = self.get_live_price()
            print("\rCurrent live price: {:.6f}".format(live_price), end="")
            time.sleep(refresh_interval)

    def get_live_slope(self):
        df = self.fetch_data()
        if df.empty:
            return 0.0
        df = self.calculate_indicators(df)
        return df['slope'].iloc[-1]

    def display_live_slope(self, refresh_interval=1):
        while True:
            live_slope = self.get_live_slope()
            print("\rCurrent live slope: {:.2f}".format(live_slope), end="")
            time.sleep(refresh_interval)


    def long_condition(self, df):
        return (df.obvs.iloc[-1] > df.obvsma.iloc[-1] and
                df.close.iloc[-1] > df.ema21.iloc[-1] )

    def short_condition(self, df):
        return (df.obvs.iloc[-1] < df.obvsma.iloc[-1] and
                df.close.iloc[-1] < df.ema21.iloc[-1] )

    def execute_trade(self, side, quantity=720):
        
        try:
            self.binance_client.futures_create_order(
                symbol='1000000BOBUSDT', type='MARKET', side=side, quantity=quantity)
        except BinanceAPIException:
            logging.error("Binance API Exception occurred")
        # latest fill price
        return float(self.binance_client.futures_account_trades()[-1]['price'])

    def get_current_pnl(self):
        try:
            all_positions = self.binance_client.futures_position_information()
        except BinanceAPIException:
            logging.error("Binance API Exception occurred")
            all_positions = []

        pos = [p for p in all_positions if p['symbol'] == '1000000BOBUSDT']
        if not pos:
            return 0.0

        p               = pos[0]
        direction       = 1 if float(p['positionAmt']) > 0 else -1
        entry_price     = float(p['entryPrice'])
        mark_price      = float(p['markPrice'])
        size            = float(p['positionAmt'])
        leverage        = int(self.leverage['leverage'])
        IMR             = 1 / leverage if leverage else 0

        unrealized_pnl  = size * direction * (mark_price - entry_price)

        if size and mark_price and IMR:
            return (unrealized_pnl /
                    (size * mark_price * IMR)) * 100
        return 0.0


    def trade(self):
        while True:
            
            df15 = self.fetch_data()                              
            df15 = self.calculate_indicators(df15)                

            df1  = self.fetch_data(interval=Client.KLINE_INTERVAL_1MINUTE,
                                   lookback="1 hour ago UTC")      
            df1  = self.calculate_indicators(df1)                  

            if df15.empty or df1.empty:                           
                time.sleep(1)                                      
                continue                                          

            live_price = df15.close.iloc[-1] 
            live_price1 = df1.close.iloc[-1]                        
                                  

            print(f"\rPrice (15 m): {live_price:.6f}", end="")
            
            print(f"\rSlope (1 m): {live_price1:.2f}", end="")
            

            self.current_pnl = self.get_current_pnl()

            
            if self.entered_long or self.entered_short:
                print(f"Current PnL: {self.current_pnl}")

                if (self.current_pnl > self.max_trade_pnl
                        and self.current_pnl >= self.pnl_threshold):
                    self.max_trade_pnl = self.current_pnl
                    if self.max_trade_pnl > self.pnl_threshold:
                        self.exit_threshold = (self.max_trade_pnl -
                                               self.pnl_threshold)

                if ((self.max_trade_pnl > self.pnl_threshold and
                     self.current_pnl <= self.exit_threshold)
                        or self.current_pnl < -self.stop_loss):
                    if self.entered_long:
                        self.entry_price = self.execute_trade('SELL')
                        self.send_message(
                            f"FUN/USDT – Exit Long @ {self.entry_price}\n"
                            f"PnL: {self.current_pnl:.2f}%")
                        self.entered_long = False
                    elif self.entered_short:
                        self.entry_price = self.execute_trade('BUY')
                        self.send_message(
                            f"FUN/USDT – Exit Short @ {self.entry_price}\n"
                            f"PnL: {self.current_pnl:.2f}%")
                        self.entered_short = False

                    self.entry_price    = 0
                    self.current_pnl    = 0
                    self.max_trade_pnl  = 0
                    self.exit_threshold = 0

            
            else:
                long15   = self.long_condition(df15)               
                long1    = self.long_condition(df1)                
                short15  = self.short_condition(df15)              
                short1   = self.short_condition(df1)               

                if long15 and long1 and not self.entered_long:     
                    self.entered_long = True
                    self.entry_price  = self.execute_trade('BUY')
                    self.send_message(
                        f"FUN/USDT – Enter LONG @ {self.entry_price}")
                    continue

                if short15 and short1 and not self.entered_short:  
                    self.entered_short = True
                    self.entry_price   = self.execute_trade('SELL')
                    self.send_message(
                        f"FUN/USDT – Enter SHORT @ {self.entry_price}")


if __name__ == "__main__":
    api_key    = ""
    api_secret = ""

    trader = Trader(api_key, api_secret)
    trader.trade()