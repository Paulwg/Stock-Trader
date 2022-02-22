import time
import gspread
import pandas as pd
import talib as ta
import numpy as np
from datetime import datetime
from pytz import timezone
from playsound import playsound
from scipy.stats import linregress
from google.oauth2.service_account import Credentials

import CoinbaseAuth as CA
import product

'''
    Auto trade based purely on the slope of moving average as indicator
'''

# logging to google sheets
scope = ['https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file("fintechpass.json", scopes=scope)
client = gspread.authorize(creds)
google_sh = client.open("Trade Indicators")
sheet1 = google_sh.get_worksheet(10)

def get_prod(id,secs):
    rslt = product.candles(id,secs)
    return pd.read_json(rslt)

def get_sloppy(array):
    y = np.array(array)
    x = np.arange(len(y))
    slope, interc, r_val, p_val, std_err = linregress(x,y)
    return slope

def main():
    tz = timezone('EST')
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
            # dataf['kama'] = ta.KAMA(dataf[4],timeperiod=20) #Not reactive enough
            dataf['T3'] = ta.T3(dataf[4],timeperiod=6,vfactor=0.7)
            dataf['slope'] = dataf['T3'].rolling(window=20,min_periods=20).apply(get_sloppy, raw=True)
            dataf['diff'] = dataf.apply(lambda x : x[2] - x[1], axis=1)
            dataf['HL2'] = dataf.apply(lambda x : (x[2]+x[1])/2, axis=1)
            dataf['fib-1.0'] = dataf.apply(lambda x : x['HL2'] + (-1.5 * x['diff']), axis=1) #was -0.5, but with smaller prices it was not reliable
            dataf = dataf.dropna()

            #pos slp 
            slope = dataf['slope'][0] * 10000
            if slope > 3:
                print(f'{datetime.now()}  Slope: {slope} == BUY')
                if slope > 6:
                    bet_sz = 0.04
                else:
                    bet_sz = 0.02

                purchase_power = portfolio * bet_sz
                buy_shares = round(purchase_power / last_close,0)
                response = CA.submit_order('buy',prod_id,last_close,buy_shares)
                time.sleep(1)
                order = response["id"]
                time_wait = 0

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
                            stop_loss = dataf['fib-1.0'][1] 
                            sheet1.append_rows(values=[[str(datetime.now(tz)),
                                                        'Buy',
                                                        fill_sz,
                                                        last_close,
                                                        exec_val,
                                                        fill_fees,
                                                        stop_loss]])
                            playsound("./sounds/Mario lets go.m4a")
                            break
                    time_wait += 1
                    time.sleep(1)
                    if time_wait > 59:
                        CA.cancel_order(order)
                        break
            else:
                print(f'{datetime.now()}  Slope: {round(slope,4)}  Portfolio: {round(portfolio,4)}  Wins: {wins}  Losses: {losses}')
                time.sleep(int(secs))


        selling = True
        while selling:
            dataf = get_prod(prod_id,secs)
            last_close = round(dataf[4][0],6)
            min_sell_price = (desired_gain + (fill_fees * 2) + exec_val) / fill_sz
            time_wait = 0

            if last_close > min_sell_price:
                print(f'Target price triggered: {last_close}')
                response = CA.submit_order('sell',prod_id,last_close,fill_sz)
                time.sleep(1)
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
                            sheet1.append_rows(values=[[str(datetime.now(tz)),
                                                        '+Sell',
                                                        fill_sz,
                                                        last_close,
                                                        exec_val,
                                                        fill_fees,
                                                        stop_loss,
                                                        min_sell_price,
                                                        wins]])
                            playsound('./sounds/funny_yay.m4a')
                            break
                    time_wait += 1
                    time.sleep(1)
                    if time_wait > 59:
                        CA.cancel_order(order)
                        selling = False
                        break

            elif last_close < stop_loss:
                print(f'Stop loss triggered: {last_close}')
                response = CA.submit_order('sell',prod_id,last_close,fill_sz)
                time.sleep(1)
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
                            sheet1.append_rows(values=[[str(datetime.now(tz)),
                                                        '-Sell',
                                                        fill_sz,
                                                        last_close,
                                                        exec_val,
                                                        fill_fees,
                                                        stop_loss,
                                                        min_sell_price,
                                                        '',
                                                        losses]])
                            playsound("./sounds/funny_no.mp3")
                            break
                    time_wait += 1
                    time.sleep(1)
                    if time_wait > 59:
                        CA.cancel_order(order)
                        selling = False
                        break
            else:
                print(f'{datetime.now()}  Last: {last_close} < Min Sell: {min_sell_price}')
                print(f'Portfolio: {round(portfolio,4)}  Wins: {wins}  Losses: {losses}')
                time.sleep(int(secs))


if __name__ == '__main__':
    main()