from curses import window
import time
from datetime import datetime
from more_itertools import last
import pandas as pd
import talib as ta
import numpy as np
from scipy.stats import linregress

import CoinbaseAuth as CA
import product

def get_prod(id,secs):
    rslt = product.candles(id,secs)
    return pd.read_json(rslt)

def get_sloppy(array):
    y = np.array(array)
    x = np.arange(len(y))
    slope, interc, r_val, p_val, std_err = linregress(x,y)
    return slope

def main():
    capital_gains_tax = 0.27
    prod_id = 'ADA-USD'
    secs = '60'
    portfolio = 100.00
    order = ''
    wins = 0
    losses = 0

    while portfolio > 75:
        buying = True
        while buying: #iterate until slope positive and buy order filled
            dataf = get_prod(prod_id,secs)
            last_close = round(dataf[4][0],6)
            dataf = dataf.iloc[::-1]
            dataf['kama'] = ta.KAMA(dataf[4],timeperiod=20)
            dataf['slope'] = dataf['kama'].rolling(window=20,min_periods=20).apply(get_sloppy, raw=True)
            dataf['diff'] = dataf.apply(lambda x : x[2] - x[1], axis=1)
            dataf['HL2'] = dataf.apply(lambda x : (x[2]+x[1])/2, axis=1)
            dataf['fib-0.5'] = dataf.apply(lambda x : x['HL2'] + (-0.5 * x['diff']), axis=1)
            dataf = dataf.dropna()

            S3 = ((dataf['slope'][0] + dataf['slope'][1] + dataf['slope'][2]) / 3) * 10000
            #pos slp 
            if S3 > 3:
                print(f'{datetime.now()}  Slope: {S3} == BUY')
                if S3 > 6:
                    bet_sz = 0.04
                else:
                    bet_sz = 0.02

                purchase_power = portfolio * bet_sz
                buy_shares = round(purchase_power / last_close,0)
                response = CA.submit_order('buy',prod_id,last_close,buy_shares)
                order = response["id"]

                while True:
                    sumbitted_order = CA.get_single_order(order)
                    if 'settled' in sumbitted_order:
                        filled = sumbitted_order['settled']
                        exec_val = float(sumbitted_order['executed_value'])
                        fill_fees = float(sumbitted_order['fill_fees'])
                        fill_sz = float(sumbitted_order['filled_size'])
                        if filled == True:
                            desired_gain = exec_val * 0.005 # % gain
                            portfolio -= exec_val
                            portfolio -= fill_fees
                            buying = False
                            stop_loss = exec_val - (exec_val * -0.02) # dataf['fib-0.5'][1] #temp trying 2% SL until volatility checker implemented
                            break
                        time.sleep(30)
            else:
                print(f'{datetime.now()}  Slope: {S3} ...waiting')
                print(f'Trades: {wins+losses}  Wins: {wins}  Losses: {losses}')
                time.sleep(int(secs)+1)


        selling = True
        while selling:
            dataf = get_prod(prod_id,secs)
            last_close = round(dataf[4][0],6)
            
            #minimum price to submit sell
            min_sell_price = (((desired_gain + fill_fees + exec_val 
                                - (exec_val * capital_gains_tax)
                                - (fill_fees * capital_gains_tax)) 
                                / (buy_shares * (1 - capital_gains_tax))))

            if last_close > min_sell_price:
                print(f'Target price triggered: {last_close}')
                response = CA.submit_order('sell',prod_id,last_close,fill_sz)
                order = response["id"]
            
                while True:
                    sumbitted_order = CA.get_single_order(order)
                    if 'settled' in sumbitted_order:
                        filled = sumbitted_order['settled']
                        exec_val = float(sumbitted_order['executed_value'])
                        fill_fees = float(sumbitted_order['fill_fees'])
                        fill_sz = float(sumbitted_order['filled_size'])
                        if filled == True:
                            selling = False
                            portfolio += exec_val
                            portfolio -= fill_fees
                            wins +=1
                            break
                        time.sleep(30)

            elif last_close < stop_loss:
                print(f'Stop loss triggered: {last_close}')
                response = CA.submit_order('sell',prod_id,last_close,fill_sz)
                order = response["id"]
            
                while True:
                    sumbitted_order = CA.get_single_order(order)
                    if 'settled' in sumbitted_order:
                        filled = sumbitted_order['settled']
                        exec_val = float(sumbitted_order['executed_value'])
                        fill_fees = float(sumbitted_order['fill_fees'])
                        fill_sz = float(sumbitted_order['filled_size'])
                        if filled == True:
                            selling = False
                            portfolio += exec_val
                            portfolio -= fill_fees
                            losses += 1
                            break
                        time.sleep(30)
            else:
                print(f'{datetime.now()}  Last: {last_close}  <  Min Sell Price: {min_sell_price}')
                print(f'Trades: {wins+losses}  Wins: {wins}  Losses: {losses}')
                time.sleep(int(secs)+1)

        print(f'Time: {datetime.now()}\tPortfolio: {portfolio}')


if __name__ == '__main__':
    main()