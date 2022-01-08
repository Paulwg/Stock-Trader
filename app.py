import time
import datetime
import pandas as pd
import numpy as np
import talib as ta
import matplotlib.pyplot as plt
import matplotlib.dates as mdate
from scipy import interpolate, ndimage, signal

import CoinbaseAuth as CA
import product

#TODO:
#   most recent candle will never have a sell or buy signal because of the time delay, unless I am mistaken

def main():

    pd.set_option('display.max_rows', 301)

    ready_sell = False
    ready_buy = True
    holding = False #placeholder, need to add ability to check 
    order_id = "" #placeholder

    product_id = 'DOT-USD'
    # 300sec seems to be the most reliable while also being smaller timeframe
    seconds = '300'

    portfolio = 100.00

    purchase_price = 24
    num_shares = 50 # tbd if bought or sold
    capital_gains_tax = 0.27

    entrance_fee = 0.2
    exit_fee = 0.2

    desired_gain = purchase_price * 0.02 # 2% gain expected each trade? we'll see
    # based on desired_gain and accounting for taxes
    min_sell_price = (((desired_gain + exit_fee + purchase_price 
                        - (purchase_price * capital_gains_tax)
                        - (exit_fee * capital_gains_tax)) 
                        / (num_shares * (1 - capital_gains_tax))))


    buy_cost = purchase_price * num_shares + entrance_fee
    
    sold_price = 27
    pre_tax_gain = sold_price * num_shares - exit_fee
    actual_gain = (pre_tax_gain) - (pre_tax_gain * capital_gains_tax)

    repurchase_price = (actual_gain + buy_cost) / num_shares 
    
    max_loss = purchase_price * 0.05 #UNUSED, 5% max loss??
    max_buy_price = 0.01 #UNUSED, TBD based on pivots
    
    while True:
        #UNUSED, current_price = product.ticker(product_id)
        data = product.candles(product_id, seconds)
        df = pd.read_json(data)

        df = df.rename({0: 'Timestamp', 1: 'low', 2: 'high', 3: 'open', 
                        4: 'close', 5: 'volume'}, axis='columns')
        # convert epoch to matplotlib readable
        df['Timestamp'] = mdate.epoch2num(df['Timestamp'])

        df["SMA_20"] = ta.SMA(df["close"],timeperiod=20)
        # estimate SMA of now
        df.loc[0, "SMA_20"] = df.loc[:19,"close"].astype(float).sum(axis=0) / 20
        df["SMA_50"] = ta.SMA(df["close"],timeperiod=50)
        df.loc[0, "SMA_50"] = df.loc[:49,"close"].astype(float).sum(axis=0) / 50

        df["SAR"] = ta.SAR(df["high"],df["low"])
        # use sar[1] as most recent, save time and effort

        df["RSI"] = ta.RSI(df["close"])
        # estimate rsi of now
        _ = df["close"].copy()
        df["_dif"] = _.diff(1)
        df['_gn'] = df['_dif'].clip(lower=0).round(2)
        df['_ls'] = df['_dif'].clip(upper=0).abs().round(2)
        avg_gain = df.loc[:13,'_gn'].astype(float).sum(axis=0) /14
        avg_loss = df.loc[:13,'_ls'].astype(float).sum(axis=0) / 14
        rs = round(avg_gain / avg_loss, 2)
        rsi = round(100 - (100 / (1 + rs)), 2)
        df.loc[0, "RSI"] = rsi

        df["AROON_DOWN"],df["AROON_UP"] = ta.AROON(df["high"],df["low"])
        _max = df.loc[:13,'close'].max()
        _max = df.loc[:13,'close'].index[df.loc[:13,'close']==_max].tolist()
        aroon_up = ( 14 - _max[0] ) / 14 * 100
        _min = df.loc[:13,'close'].min()
        _min = df.loc[:13,'close'].index[df.loc[:13,'close']==_min].tolist()
        aroon_down = ( 14 - _min[0] ) / 14 * 100
        df.loc[0,"AROON_UP"] = aroon_up
        df.loc[0,"AROON_DOWN"] = aroon_down

        df["BOP"] = ta.BOP(df["open"], df["high"], df["low"], df["close"])

        df["ADX"] = ta.ADX(df["high"], df["low"], df["close"],timeperiod=14)
        df["MINUS_DI"] = ta.MINUS_DI(df["high"], df["low"], df["close"])
        df["PLUS_DI"] = ta.PLUS_DI(df["high"], df["low"], df["close"])

        high_low = df.loc[:13,'high'] - df.loc[:13,'low']
        high_close = np.abs(df.loc[:13,'high'] - df.loc[:13,'close'].shift())
        low_close = np.abs(df.loc[:13,'low'] - df.loc[:13,'close'].shift())


        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(14).mean()

        plus_dm = df['high'].diff() 
        plus_dm[plus_dm < 0 ] = 0

        minus_dm = df['low'].diff() 
        minus_dm[minus_dm > 0 ] = 0

        plus_di = 100 * (plus_dm.ewm(alpha = 1/14).mean() / atr) 
        df.loc[0,'PLUS_DI'] = plus_di[13]

        minus_di = abs(100 * (minus_dm.ewm(alpha = 1/14).mean() / atr)) 
        df.loc[0,'MINUS_DI'] = minus_di[13]

        dx = (abs(plus_di - minus_di) / abs(plus_di + minus_di)) * 100
        #arbitrary avg??
        df.loc[0,'ADX'] = (df.loc[27,'ADX'] + dx[13]) / 2

        # instantiate for plotting purposes on first run
        df["buy_signal"] = False
        df["sell_signal"] = False
        
        date = df["Timestamp"]
        cdate = df["Timestamp"]
        close = df["close"]
        recent_close = close[0]
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



        #================#
        # Volume Checker #
        #================#
        '''
        # volume checker, arbitrary 3/4 increasing volume followed by 2 consecutive decreasing
        # my current thought process is the 3 candle play and then a decrease in activity
        # not currently looking at harami or any OHLC comparisons between candles
        '''
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
        #===============#
        # End Vol Check #
        #===============#

        #=====#
        # BUY #
        #=====#
        '''
        # TODO: incorporate g1d slope to time buy? 
        # also backtest
        '''
        if not holding and ready_buy:
            buy_flags = 5

            df["sma_check"] = SMA_20.lt(SMA_50)
            df["ar_check"]= ar_up.lt(ar_dn)
            df["di_check"]= plus_di.lt(minus_di)
            df["adx_check"] = adx.gt(25)
            df["rsi_check"] = rsi.lt(40)
            df["bop_check"] = bop.lt(-0.4)
            df["sar_check"] = sar.gt(close) & SMA_50.gt(close)
            df.loc[0,"sar_check"] = df.loc[1,"sar_check"]
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

            # print("Buy loop:")
            # print(df)

            if df['buy_signal'][0] == True:
                if recent_close < repurchase_price:
                    print(f'{datetime.datetime.now()} : BUY')
                    print(recent_close,"\n")
            #         ## need to submit buy order now
            #         num_shares = portfolio / recent_close
            #         side = "buy"
            #         response = CA.submit_order(side, 
            #                                    product_id, 
            #                                    str(recent_close), 
            #                                    str(num_shares)
            #                                    )

            #         ## save order_id and any subsequent vars
            #         order_id = response["id"]

                    # flip flag
                    holding = True
                    ready_buy = False

        #===============#
        # end buy logic #
        #===============#

        #======#
        # SELL #
        #======#
        '''
        '''
        if holding and ready_sell:
            sell_flags = 5

            df["sma_check"] = SMA_20.gt(SMA_50)
            df["ar_check"]= ar_up.gt(ar_dn)
            df["di_check"]= plus_di.gt(minus_di)
            df["adx_check"] = adx.gt(25)
            df["rsi_check"] = rsi.gt(60)
            df["bop_check"] = bop.gt(0.4)
            df["sar_check"] = sar.lt(close) & SMA_50.lt(close)
            df.loc[0,"sar_check"] = df.loc[1,"sar_check"]
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
                                                    x['sellflag'] #& x['vol_valid'] 
                                                    else False, axis=1)
            
            # print("Sell loop:")
            # print(df)

            if df['sell_signal'][0] == True:
                if recent_close > min_sell_price:
                    print(f'{datetime.datetime.now()} : SELL')
                    print(recent_close, "\n")
            #         # need to submit order now
            #         side = "sell"
            #         response = CA.submit_order(side, 
            #                                    product_id,
            #                                    str(recent_close),
            #                                    str(num_shares)
            #                                    )
            #         # save order_id and any subsequent vars
            #         order_id = response["id"]

                    # flip flag
                    #was indented to here
                    holding = False
                    ready_sell = False

        #================#
        # end sell logic #
        #================#

        # else: # checking submitted order
        #     #order_id = 'b55c7be8-211e-4419-abbc-c606be36fef4' # test order_id
        #     if order_id:
        #         submitted_order = CA.get_single_order(order_id)
        #         if submitted_order["status"] == "done" and submitted_order["settled"] == True:
        #             print("order is complete")

        #             if submitted_order["side"] == "buy":
        #                 print("Buy order Finished")
        #                 ready_sell = True
        #                 order_id = response["id"]
        #                 purchase_price = response["price"]
        #                 num_shares = response["filled_size"]
        #                 entrance_fee = response["fill_fees"]
        #                 executed_value = response["executed_value"]

        #             if submitted_order["side"] == "sell":
        #                 print("Sell order Finished")
        #                 ready_buy = True
        #                 sold_price = response["price"]
        #                 num_shares = response["filled_size"]
        #                 exit_fee = response["fill_fees"]
        #                 portfolio = response["executed_value"]


        #================#
        # BEGIN PLOTTING #
        #================#
        # colors = {'red': '#ff207c', 'grey': '#42535b', 'blue': '#207cff', 'orange': '#ffa320', 'green': '#00ec8b'}
        # config_ticks = {'size': 14, 'color': colors['grey'], 'labelcolor': colors['grey']}
        # config_title = {'size': 18, 'color': colors['grey'], 'ha': 'left', 'va': 'baseline'}

        # plt.rc('figure', figsize=(15,10))
        # fig, axes = plt.subplots(3, 1, sharex=True, gridspec_kw={'height_ratios': [3,1,1]})
        # fig.tight_layout(pad=3)
            
        # plot_price = axes[0]
        # plot_price.plot(date, close, color='darkgrey', label='Price', marker='$B$', ms=25, markevery=df.index[df['buy_signal']].tolist())
        # plot_price.plot(date, close, color='darkgrey', label='Price', marker='$S$', ms=25, markevery=df.index[df['sell_signal']].tolist())

        # plot_price.plot(cdate, SMA_20, '--', color=colors['orange'], label='SMA20')
        # plot_price.plot(cdate, SMA_50, '--', color=colors['red'], label='SMA50')

        # # Spline
        # x_smooth = np.linspace(date.min(), date.max(), 600)
        # spl = interpolate.UnivariateSpline(date.iloc[::-1], close)
        # plot_price.plot(date, spl(date.iloc[::-1]), color='yellow', ls=':')
        
        # #gaussian filter
        # sigma = 4
        # x_g1d = ndimage.gaussian_filter1d(date, sigma)
        # y_g1d = ndimage.gaussian_filter1d(close, sigma)
        # #rel min, max . Returned as array of index of dataset
        # mins = signal.argrelextrema(y_g1d, np.less)[0]
        # maxes = signal.argrelextrema(y_g1d, np.greater)[0]

        # plot_price.plot(x_g1d[mins], y_g1d[mins], 'r^')
        # plot_price.plot(x_g1d[maxes], y_g1d[maxes], 'gv')
        # plot_price.plot(x_g1d, y_g1d, color='black', label='g1d')

        # plot_price.yaxis.tick_right()
        # plot_price.tick_params(axis='both', **config_ticks)
        # plot_price.yaxis.set_label_position("right")
        # plot_price.yaxis.label.set_color(colors['grey'])
        # plot_price.grid(axis='y', color='gainsboro', linestyle='-', linewidth=0.5)
        # plot_price.set_axisbelow(True)

        # plot_vol = axes[1]
        # plot_vol.plot(date, vol, color='grey', label='Vol')

        # plot_rsi = axes[2]
        # plot_rsi.plot(cdate, rsi, color='purple', label='RSI')

        # date_form = mdate.DateFormatter("%D-%H:%M:%S")

        # for ax in axes:
        #     ax.xaxis.set_major_formatter(date_form)

        # plt.setp(plot_vol.get_xticklabels(), rotation=15)
        # plot_legend = fig.legend(loc='upper left', bbox_to_anchor= (-0.005, 0.95), fontsize=16)
        # for text in plot_legend.get_texts():
        #     text.set_color(colors['grey'])

        # plt.show()

        #==============#
        # End Plotting #
        #==============#

        print(f"\nSleeping for {seconds}sec")
        time.sleep(int(seconds))

if __name__ == '__main__':
    main()