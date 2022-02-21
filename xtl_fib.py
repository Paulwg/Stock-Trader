import time
from datetime import datetime
import pandas as pd
import talib as ta
import gspread
from google.oauth2.service_account import Credentials

import CoinbaseAuth as CA
import product

#note: may need to begin execution closer to close of the most recent candle

scope = ['https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file("fintechpass.json", scopes=scope)
client = gspread.authorize(creds)
google_sh = client.open("Trade Indicators")
sheet1 = google_sh.get_worksheet(11)

def main():

    # pd.set_option('display.max_rows', 301)
    #presets
    product_id = 'MATIC-USD'
    seconds = '300'
    portfolio = 100.00
    bet_size = 0.06 #%

    #placeholders
    holding = False 
    ready_sell = False
    ready_buy = True
    order_id = "" 
    sell_shares = 0

    wins = 0
    losses = 0

    while True:
        #mmmdata
        data = product.candles(product_id, seconds)
        df = pd.read_json(data)

        df = df.rename({0: 'Timestamp', 1: 'low', 2: 'high', 3: 'open', 
                        4: 'close', 5: 'volume'}, axis='columns')

        df['Timestamp'] = pd.to_datetime(df['Timestamp'],unit='s')

        df = df.iloc[::-1]

        ###XTL
        #lookback period
        prd = 35
        #cci measures the current price level relative to an average price level over a given period of time
        df['cciNT'] = ta.CCI(df['high'],df['low'],df['close'],timeperiod=prd)

        #preset value from tradingview, not sure why 37 specifically
        fixed_value = 37

        df['mark'] = df.apply(lambda x : 'bear' if x['cciNT'] < -fixed_value
                                            else( 'neutral' if -fixed_value <= x['cciNT'] and x['cciNT'] <= fixed_value
                                                    else 'bull'),axis=1)

        #FIB
        df['diff'] = df.apply(lambda x : x['high'] - x['low'], axis=1)
        df['HL2'] = df.apply(lambda x : (x['high']+x['low'])/2, axis=1)
        df['fib1.5'] = df.apply(lambda x : x['HL2'] + (1.5 * x['diff']), axis=1)
        df['fib-0.5'] = df.apply(lambda x : x['HL2'] + (-0.5 * x['diff']), axis=1)
        df['T3'] = ta.T3(df['close'],timeperiod=6,vfactor=0.7)
        # df = df.iloc[::-1]
        df = df.dropna()

        print(f'Fib 1.5 target: {df["fib1.5"][1]}')
        print(f'Current price: {df["close"][0]}')

        #don't like the way this is implemented
        # df.loc[0, 'fib_buy'] = df.loc[0,'low']
        # for i in range (0,len(df)-1):
        #     trgt = df.loc[i+1,'fib1.5']
        #     print(f'Fib 1.5 target: {trgt}')
        #     rslt = df.loc[i,'high'] 
        #     print(f'Current high: {rslt}') 
        #     if rslt >= trgt:
        #         df.loc[i, 'fib_buy'] = True
        #     else:
        #         df.loc[i, 'fib_buy'] = False

        #done this way for backtesting purposes
        # df['buy_signal'] = df.apply(lambda x : True if x['mark'] == 'bull'
        #                                             and x['fib_buy'] == True
        #                                             else False, axis=1)

        last_close = round(df['close'][0],6) # use most recent
        trailing_stop = df['T3'][0]
        purchase_power = portfolio * bet_size
        buy_shares = round(purchase_power / last_close,0)

        if not holding and ready_buy:
            #if df['buy_signal'][0] == True: OLD
            if df['close'][0] >= df['fib1.5'][1] and df['mark'][0] == 'bull' :
                print(f'{datetime.now()} : BUY')
                side = 'buy'
                response = CA.submit_order(side,product_id,last_close,buy_shares)
                order_id = response["id"]
                initial_stop = df['fib-0.5'][1] # use previous
                print(f'Initial Stop: {initial_stop}')
                holding = True
                ready_buy = False
                iterations = 0

        elif holding and ready_sell:
            if (last_close < initial_stop and iterations == 0) or (last_close < trailing_stop and iterations > 0):
                print(f'{datetime.now()} : SELL')
                print(f'Last Close: {last_close}')
                print(f'Initial Stop: {initial_stop}  Trailing Stop: {trailing_stop}')
                side = "sell"
                response = CA.submit_order(side,product_id,last_close,sell_shares)
                order_id = response['id']
                holding = False
                ready_sell = False
            else:
                iterations += 1
        
        else:
            if order_id:
                submitted_order = CA.get_single_order(order_id)
                if submitted_order["settled"] == True:
                    exe_val = submitted_order['executed_value']
                    fill_fees = submitted_order['fill_fees']
                    fill_sz = submitted_order['filled_size']
                    print(f'Executed Value: {exe_val}\nFill size: {fill_sz}\nFees: {fill_fees}')
                    sheet1.append_rows(values=[[submitted_order["side"],fill_sz,exe_val,fill_fees,initial_stop,trailing_stop]])


                    if submitted_order["side"] == "buy":
                        print("Buy order Finished")
                        ready_sell = True
                        portfolio -= float(fill_fees)
                        portfolio -= float(exe_val)
                        bought_val = float(exe_val)
                        sell_shares = float(fill_sz)
                        
                    if submitted_order["side"] == "sell":
                        print("Sell order Finished")
                        ready_buy = True
                        portfolio -= float(fill_fees)
                        portfolio += float(exe_val)
                        sold_val = float(exe_val)
                        if sold_val > bought_val:
                            wins += 1
                        else:
                            losses += 1

        print(f'Time: {datetime.now()}\tPortfolio: {portfolio}')
        print(f'Trades: {wins+losses}  Wins: {wins}  Losses: {losses}')
        time.sleep(int(seconds)+1)

if __name__ == '__main__':
    main()