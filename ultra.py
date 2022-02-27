import time
import gspread
import threading
from datetime import datetime
import pandas as pd
import numpy as np
import talib as ta
from scipy import ndimage, signal
from pytz import timezone
from scipy.stats import linregress
from google.oauth2.service_account import Credentials

import CoinbaseAuth as CA
import product

# logging to google sheets
scope = ['https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file("fintechpass.json", scopes=scope)
client = gspread.authorize(creds)
google_sh = client.open("Trade Indicators")
sheet1 = google_sh.get_worksheet(10)
tz = timezone('EST')

#####################
### Data Handling ###
#####################

def init_data(prod_name,seconds,file_name):
    raw_data = product.candles(prod_name,seconds)
    df = pd.read_json(raw_data)
    df.to_csv(file_name,index=False)

def new_data(prod_name,seconds,file_name):
    while True:
        time.sleep(int(seconds))
        if len(pd.read_csv(file_name)) < 30000:
            raw_data = product.candles(prod_name,seconds)
            df = pd.read_json(raw_data)
            df.tail(1).to_csv(file_name,index=False,header=False,mode='a')

def get_data(file_name):
    df = pd.read_csv(file_name)
    return df


############################
### Technical Indicators ###
############################

def ta_crunch(df):
    mapping = {df.columns[0]: 'Timestamp', df.columns[1]: 'low', df.columns[2]: 'high', df.columns[3]: 'open', df.columns[4]: 'close', df.columns[5]: 'volume'}
    df = df.rename(columns=mapping)
    df = df.iloc[::-1]

    #Smoothed moving average
    df["SMA_20"] = ta.SMA(df["close"],timeperiod=20)
    df['SMA_50'] = ta.SMA(df["close"],timeperiod=50)

    #/\/\/\/\/\/\/\/\/\/\#
    #  Trend Indicators
    #/\/\/\/\/\/\/\/\/\/\#

    #SAR below close indicates upward trend
    df["SAR"] = ta.SAR(df["high"],df["low"])

    #AROON, indicates trend changes and strength of change. If high/low then max/min occured within previous 12.5 periods
    df["AROON_DOWN"],df["AROON_UP"] = ta.AROON(df["high"],df["low"])

    #ADX, used to quantify trend strength.
    #PLUS_DI greater than MINUS_DI indicates uptrend
    df["ADX"] = ta.ADX(df["high"], df["low"], df["close"],timeperiod=14)
    df["MINUS_DI"] = ta.MINUS_DI(df["high"], df["low"], df["close"])
    df["PLUS_DI"] = ta.PLUS_DI(df["high"], df["low"], df["close"])

    #/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\//\/\/\/\/\/\/\#
    #  Momentum oscillatros, indicate oversold or overbought
    #/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\//\/\/\/\/\/\/\#

    #RSI tracks speed of price change.
    df["RSI"] = ta.RSI(df["close"])

    #CCI tracks normal deviations from moving average.
    df['cciNT'] = ta.CCI(df['high'],df['low'],df['close'],timeperiod=35)
    df['XTL'] = df.apply(lambda x : 'bear' if x['cciNT'] < -37
                                                else( 'neutral' 
                                                    if -37 <= x['cciNT'] and x['cciNT'] <= 37
                                                    else 'bull'),axis=1)

    df = df.dropna()

    ### fear zone ###
    df["sma_fear"] = df['SMA_20'].lt(df['SMA_50'])
    df["ar_fear"]= df["AROON_UP"].lt(df["AROON_DOWN"])
    df["di_fear"]= df["PLUS_DI"].lt(df["MINUS_DI"])
    df["adx_fear"] = df["ADX"].gt(25)
    df["rsi_fear"] = df["RSI"].lt(40)
    df["sar_fear"] = df["SAR"].gt(df["close"]) & \
                      df["SMA_50"].gt(df["close"])

    # FIBONACCI EXTENSION at 1.5, used as threshold to enter trade during bullish swing
    df['diff'] = df.apply(lambda x : x['high'] - x['low'], axis=1)
    df['HL2'] = df.apply(lambda x : (x['high']+x['low'])/2, axis=1)
    df['fib1.5'] = df.apply(lambda x : x['HL2'] + (1.5 * x['diff']), axis=1)

    # Initial stop = (low/min of the previous n candles) - ATR
    df['ATR'] = ta.ATR(df['high'],df['low'],df['close'],timeperiod=20)

    return df

def get_fear_count(df,period):
    fear_count = df.filter(regex='fear')
    return fear_count.tail(period).sum()

def get_greed_count(df,period):
    return df.tail(period).sum()

#########################
### Additional Tools ####
#########################

def get_sloppy(array): # only called from slope()
    y = np.array(array)
    x = np.arange(len(y))
    slope, _interc, _r_val, _p_val, _std_err = linregress(x,y)
    return slope

def slope(df_column,timeperiod=6,vfactor=0.7,window_size=20):
    t3 = ta.T3(df_column,timeperiod,vfactor)
    slopes = t3.rolling(window=window_size,min_periods=20).apply(get_sloppy, raw=True)
    return slopes.dropna()

def mins_maxes(df):
    '''
    pass in single dataframe column
    '''
    #gaussian filter
    sigma = 4
    y_g1d = ndimage.gaussian_filter1d(df, sigma)
    #rel min, max . Returned as array of index of dataset
    mins = signal.argrelextrema(y_g1d, np.less)[0]
    maxes = signal.argrelextrema(y_g1d, np.greater)[0]
    return mins, maxes #arrays of index locations for df

##############
### Orders ###
##############

def buy(fn_smll_tmfrm,product_name,fib_target,shares,seconds):
    buying = True
    waiting_count = 0
    times_up = int(seconds)
    while buying:
        # monitoring 60 second candles waiting for buy threshold to be met.
        quicker_timeframe = get_data(fn_smll_tmfrm)
        if quicker_timeframe[4][0] >= fib_target:
            order_response = CA.submit_order('buy',product_name,fib_target,shares)
            time.sleep(1)
            
            while True:
                if 'id' in order_response:
                    submitted_order = CA.get_single_order(order_response['id'])
                    if 'settled' in submitted_order:
                        filled = submitted_order['settled']
                        if filled == True:
                            buying = False
                            cost = -submitted_order['executed_value']-submitted_order['filled_fees']
                            sheet1.append_row(values=[['','Buy',str(datetime.now(tz)),cost]])

                            # call sell from here so that sell is only called if a trade has been made
                            t4 = threading.Thread(target=sell,args=(fn_smll_tmfrm,product_name,fib_target,order_response['id']))
                            break

                    waiting_count += 1
                    time.sleep(1)
                    if waiting_count > 59:
                        CA.cancel_order(order_response['id'])
                        break
        else:
            times_up -= 1
            if times_up == 0:
                buying = False
        time.sleep(61) # quicker_timeframe + 1

def sell(fn_smll_tmfrm,product_name,fib_target,order_id):
    selling = True
    waiting_count = 0
    while selling:
        quicker_timeframe = get_data(fn_smll_tmfrm)

    '''
    Now that we have a position
        initial stop = (low/min of the previous n candles) - ATR
        OR
        initial stop = -0.5 Fib Ext of previous candle
        WHICHEVER is less
        THEN as price (hopefully) rises:
        trailing stop takes over after price exceeds minimum sell value.
        trailing stop = tight smoothed MA
    '''

def cancel():
    pass

def check():
    pass

def main():
    product_name = 'BTC-USD'
    seconds = '300' #string for get requests
    file_name = f'./history/{product_name}'
    fn_smll_tmfrm = f'{file_name}_60s'

    init_data(product_name,seconds,file_name)
    init_data(product_name,'60',fn_smll_tmfrm)

    # appending new candles to dataset every 'seconds'
    t1 = threading.Thread(target=new_data,args=(product_name,seconds,file_name))
    t2 = threading.Thread(target=new_data,args=(product_name,'60',fn_smll_tmfrm))
    t1.start()
    t2.start()
    
    while True:
        allotted = sheet1.cell('A1').value
        bet_size = 0.1 #%
        largest_bet = allotted * bet_size
        #TODO: Research implementing a modified kelly criterion model for gauging bet size.

        raw_data = get_data(file_name)
        td = ta_crunch(raw_data)
        
        fear = get_fear_count(td,5).sum() # Max = 30

        col_slope = slope(td['SMA_50'],timeperiod=8,vfactor=0.1,window_size=20)
        most_recent_slope = col_slope[0]

        xtl_outcome = td['XTL'][0]

        # currently fear threshold is 30%
        if fear < 9 and most_recent_slope > 4 and xtl_outcome == 'bull':
            fib_target = td['fib1.5'][0]
            shares = round(largest_bet / fib_target,0)
            t3 = threading.Thread(target=buy,args=(fn_smll_tmfrm,product_name,fib_target,shares,seconds))
            t3.start()
            t3.join()

            '''
            Summary of what I have done so far
            -thread that continuously retrieves market data for one long and one short timeframe on the same product

            -while loop
                -get long timeframe data from local file

                -if fear, slope, xtl all meet condition then move to buy phase

                    -thread that continuosly reads short term market data waiting for FIB1.5 target
                    this thread will run for the duration of the long term candle period and then exit if Fib target not met

            '''


if __name__ == '__main__':
    main()