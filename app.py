import time
import pandas as pd
import numpy as np
import talib as ta
import matplotlib.pyplot as plt
import matplotlib.dates as mdate
from scipy import interpolate, ndimage, signal

import CoinbaseAuth as CA
import product

def main():

    pd.set_option('display.max_rows', 301)

    holding = False #placeholder, need to add ability to check 

    name = 'DOT-USD'
    # 300sec seems to be the most reliable while also being smaller timeframe
    seconds = '300'

    portfolio = 10000.00
    order_id = "" #placeholder

    purchase_price = 30
    num_shares = 100 # tbd if bought or sold
    capital_gains_tax = 0.27

    entrance_fee = 0
    exit_fee = 0

    desired_gain = purchase_price * 0.02 # 2% gain expected each trade? we'll see
    # based on desired_gain and accounting for taxes
    min_sell_price = (((desired_gain + exit_fee + purchase_price 
                        - (purchase_price * capital_gains_tax)
                        - (exit_fee * capital_gains_tax)) 
                        / (num_shares * (1 - capital_gains_tax))))

    buy_cost = purchase_price * num_shares + entrance_fee
    
    sold_price = 0
    pre_tax_gain = sold_price * num_shares - exit_fee
    actual_gain = (pre_tax_gain) - (pre_tax_gain * capital_gains_tax)

    repurchase_price = (actual_gain + buy_cost) / num_shares 
    max_buy_price = 0.01 #TBD based on pivots
    
    ready_sell = False
    ready_buy = False
    existing_submitted_order = False

    while True:
        current_price = product.ticker(name)
        data = product.candles(name, seconds)
        df = pd.read_json(data)

        df = df.rename({0: 'Timestamp', 1: 'low', 2: 'high', 3: 'open', 
                        4: 'close', 5: 'volume'}, axis='columns')
        # convert epoch to matplotlib readable
        df['Timestamp'] = mdate.epoch2num(df['Timestamp'])

        df["SMA_20"] = ta.SMA(df["close"],timeperiod=20)
        df["SMA_50"] = ta.SMA(df["close"],timeperiod=50)
        df["SAR"] = ta.SAR(df["high"],df["low"])
        df["RSI"] = ta.RSI(df["close"])
        df["AROON_DOWN"],df["AROON_UP"] = ta.AROON(df["high"],df["low"])
        df["BOP"] = ta.BOP(df["open"], df["high"], df["low"], df["close"])
        df["ADX"] = ta.ADX(df["high"], df["low"], df["close"])
        df["MINUS_DI"] = ta.MINUS_DI(df["high"], df["low"], df["close"])
        df["PLUS_DI"] = ta.PLUS_DI(df["high"], df["low"], df["close"])

        # placeholder
        df["buy_signal"] = False
        df["sell_signal"] = False
        
        date = df["Timestamp"]
        cdate = df["Timestamp"]
        close = df["close"]
        prev_close = close[0]
        SMA_20 = df["SMA_20"]
        SMA_50 = df["SMA_50"]
        vol = df["volume"]
        rsi = df["RSI"]
        sar = df["SAR"]
        ar_up = df["AROON_UP"]
        ar_dn = df["AROON_DOWN"]
        plus_di = df["PLUS_DI"]
        minus_di = df["MINUS_DI"]
        adx = df["ADX"]
        bop = df["BOP"]

        '''

        logic v1

        '''
        # volume checker, arbitrary 3/4 increasing volume followed by 2 consecutive decreasing
        # my current thought process is the 3 candle play and then a decrease in activity
        # not currently looking at harami or any OHLC comparisons between candles
        df.loc[0, 'vol_valid'] = df.loc[0,'volume']
        for i in range(0, len(df)-5):
            v5 = df.loc[i+5, 'volume']
            v4 = df.loc[i+4, 'volume']
            v3 = df.loc[i+3, 'volume']
            v2 = df.loc[i+2, 'volume'] 
            v1 = df.loc[i+1, 'volume']
            v0 = df.loc[i, 'volume']
            occurances = 0
            mandatory = 0
            four_bar_increase = False
            volume_validation = False

            if v3 >= v2:
                occurances += 1
            if v4 >= v3:
                occurances += 1
            if v4 >= v2:
                occurances += 1
            if v5 >= v4:
                occurances += 1
            if v5 >= v3:
                occurances += 1
            if v5 >= v2:
                occurances += 1
            if v5 > v4 and v5 > v3 and v5 > v2:
                mandatory = 4
            if mandatory == 4 and occurances > 3:
                four_bar_increase = True
            if mandatory != 4 and occurances > 2:
                four_bar_increase = True
            if four_bar_increase and v1 < v2 and v0 < v1:
                df.loc[i, 'vol_valid'] = True
            else:
                df.loc[i, 'vol_valid'] = False
        df = df.fillna(value={"vol_valid": False})
        
        if not holding and ready_buy:
            '''
            BUY
            '''
            # TODO: incorporate g1d slope to time buy? 
            # also backtest
            # if ['buy_signal'] true and order submitted make buy_trigger True
            buy_flags = 5

            df["sma_check"] = SMA_20.lt(SMA_50)
            df["ar_check"]= ar_up.lt(ar_dn)
            df["di_check"]= plus_di.lt(minus_di)
            df["adx_check"] = adx.gt(25)
            df["rsi_check"] = rsi.lt(40)
            df["bop_check"] = bop.lt(-0.4)
            df["sar_check"] = sar.gt(close) & SMA_50.gt(close)
            df["buyflag"] = df.apply(lambda x : True if sum(
                [x['sma_check'],
                x['ar_check'],
                x['di_check'],
                x['adx_check'],
                x['rsi_check'],
                x['bop_check'],
                x['sar_check']]) >= buy_flags
                else False, axis=1)

            # buy signal set to true when both indicator threshold and volume checks met
            df['buy_signal'] = df.apply(lambda x : True if x['buyflag'] & x['vol_valid'] 
                                                        else False, axis=1)
            # end buy logic
        
        if holding and ready_sell:
            '''
            SELL
            '''
            sell_flags = 5

            df["sma_check"] = SMA_20.gt(SMA_50)
            df["ar_check"]= ar_up.gt(ar_dn)
            df["di_check"]= plus_di.gt(minus_di)
            df["adx_check"] = adx.gt(25)
            df["rsi_check"] = rsi.gt(60)
            df["bop_check"] = bop.gt(0.4)
            df["sar_check"] = sar.lt(close) & SMA_50.lt(close)
            df["sellflag"] = df.apply(lambda x : True if sum(
                [x['sma_check'],
                x['ar_check'],
                x['di_check'],
                x['adx_check'],
                x['rsi_check'],
                x['bop_check'],
                x['sar_check']]) >= sell_flags
                else False, axis=1)

            # sell signal set to true when both indicator threshold and volume checks met
            df['sell_signal'] = df.apply(lambda x : True if 
                                                    x['sellflag'] & x['vol_valid'] 
                                                    else False, axis=1)
            
            if df['sell_signal'][0] == True:
                if product_price > min_sell_price:
                    print("SELL")
                    # need to submit order now
                    # save order_id and any subsequent vars

            # end sell logic

                    

        else:
            print("checking submitted order")
            order_id = 'b55c7be8-211e-4419-abbc-c606be36fef4' # test order_id

            submitted_order = CA.get_single_order(order_id)
            if submitted_order["status"] == "done" and submitted_order["settled"] == True:
                print("order is complete")

                if submitted_order["side"] == "buy":
                    ready_sell = True
                if submitted_order["side"] == "sell":
                    ready_buy = True
            #     #price
            #     #size
            #     #executed_value
            #     #filled_size
            #     #fill_fees


        #================#
        # BEGIN PLOTTING #
        #================#
        colors = {'red': '#ff207c', 'grey': '#42535b', 'blue': '#207cff', 'orange': '#ffa320', 'green': '#00ec8b'}
        config_ticks = {'size': 14, 'color': colors['grey'], 'labelcolor': colors['grey']}
        config_title = {'size': 18, 'color': colors['grey'], 'ha': 'left', 'va': 'baseline'}

        plt.rc('figure', figsize=(15,10))
        fig, axes = plt.subplots(3, 1, sharex=True, gridspec_kw={'height_ratios': [3,1,1]})
        fig.tight_layout(pad=3)
            
        plot_price = axes[0]
        plot_price.plot(date, close, color='darkgrey', label='Price', marker='$BL$', ms=10, markevery=df.index[df['buy_signal']].tolist())

        plot_price.plot(cdate, SMA_20, '--', color=colors['orange'], label='SMA20')
        plot_price.plot(cdate, SMA_50, '--', color=colors['red'], label='SMA50')

        # Spline
        x_smooth = np.linspace(date.min(), date.max(), 600)
        spl = interpolate.UnivariateSpline(date.iloc[::-1], close)
        plot_price.plot(date, spl(date.iloc[::-1]), color='yellow', ls=':')
        
        #gaussian filter
        sigma = 4
        x_g1d = ndimage.gaussian_filter1d(date, sigma)
        y_g1d = ndimage.gaussian_filter1d(close, sigma)
        #rel min, max . Returned as array of index of dataset
        mins = signal.argrelextrema(y_g1d, np.less)[0]
        maxes = signal.argrelextrema(y_g1d, np.greater)[0]

        plot_price.plot(x_g1d[mins], y_g1d[mins], 'r^')
        plot_price.plot(x_g1d[maxes], y_g1d[maxes], 'gv')
        plot_price.plot(x_g1d, y_g1d, color='black', label='g1d')

        plot_price.yaxis.tick_right()
        plot_price.tick_params(axis='both', **config_ticks)
        plot_price.yaxis.set_label_position("right")
        plot_price.yaxis.label.set_color(colors['grey'])
        plot_price.grid(axis='y', color='gainsboro', linestyle='-', linewidth=0.5)
        plot_price.set_axisbelow(True)

        plot_vol = axes[1]
        plot_vol.plot(date, vol, color='grey', label='Vol')

        plot_rsi = axes[2]
        plot_rsi.plot(cdate, rsi, color='purple', label='RSI')

        date_form = mdate.DateFormatter("%D-%H:%M:%S")

        for ax in axes:
            ax.xaxis.set_major_formatter(date_form)

        plt.setp(plot_vol.get_xticklabels(), rotation=15)
        plot_legend = fig.legend(loc='upper left', bbox_to_anchor= (-0.005, 0.95), fontsize=16)
        for text in plot_legend.get_texts():
            text.set_color(colors['grey'])

        plt.show()
        #END PLOTTING

        print(f"\nSleeping for {seconds}sec")
        time.sleep(int(seconds))

if __name__ == '__main__':
    main()