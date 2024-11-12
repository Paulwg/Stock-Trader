from coinbase.rest import RESTClient
import json
import datetime
import pandas as pd
import numpy as np
import talib as ta
import matplotlib.pyplot as plt
from sklearn import mixture as mix

def main():
    api_key = "REPLACE ME"
    api_secret = "REPLACE ME"
    
    client = RESTClient(api_key=api_key, api_secret=api_secret)
    
    # retrieves default exchange portfolio
    portfolio = client.get_portfolios()
    
    # portfolio is a list of of dicts, this grabs the dict out of the list
    portfolio = portfolio['portfolios'].pop()
    
    # uuid required from dict to get portfolio balance
    uuid = portfolio['uuid']
    breakdown = client.get_portfolio_breakdown(uuid)
    
    cash_balance = breakdown['breakdown']['portfolio_balances']['total_cash_equivalent_balance']
    
    crypto_balance = breakdown['breakdown']['portfolio_balances']['total_crypto_balance']
    
    product = client.get_product('ETH-USD')
    
    two_hour_market_history = client.get_candles('ETH-USD','0','0','TWO_HOUR')
    for dic in two_hour_market_history['candles']:
        # convert unix epoch time to human readable time format
        dic['start'] = str(datetime.datetime.fromtimestamp(int(dic['start'])))
    
    # convert into pandas dataframe
    df = pd.DataFrame.from_dict(two_hour_market_history['candles'])

    df = df.dropna()

    df['HLC3'] = ta.TYPPRICE(df.high,df.low,df.close)
    
    df["SMA_20"] = ta.SMA(df.HLC3, timeperiod=20)
    df.SMA_20 = df.SMA_20.shift(-19)
    
    df['SMA_50'] = ta.SMA(df.HLC3, timeperiod=50)
    df.SMA_50 = df.SMA_50.shift(-49)
    
    # RSI tracks speed of price change.
    df["RSI"] = ta.RSI(df["close"])
    df.RSI = df.RSI.shift(-14)

    df['stdDev'] = ta.STDDEV(df.close, timeperiod=20,nbdev=1)
    df.stdDev = df.stdDev.shift(-19)

    # CCI tracks normal deviations from moving average.
    # Not using ta.CCI because it was wrong somehow
    # CCI = (Typical Price  -  20-period SMA of TP) / (.015 x Mean Deviation)
    # Typical Price (TP) = (High + Low + Close)/3
    df['CCI'] = (df.HLC3 - df.SMA_20) / (0.015 * df.stdDev)
    
    df['XTL'] = df.apply(lambda x: 'bear' if x['CCI'] < -37
    else ('neutral'
          if -37 <= x['CCI'] and x['CCI'] <= 37
          else 'bull'), axis=1)
    
    df['LR_slope'] = ta.LINEARREG_SLOPE(df['SMA_20'],timeperiod=14)
    df.LR_slope = df.LR_slope.shift(-13)

    df = df.dropna()

    # with pd.option_context('display.max_rows', None,
    #                    'display.max_columns', None,
    #                    'display.precision', 3,
    #                    ):
    #     display(df)
    #     #print(dumps(two_hour_market_history, indent=2))

    unsup_df = df[['low', 'high', 'open', 'close', 'volume', 'SMA_20']]

    unsup = mix.GaussianMixture(n_components=4, 
                                covariance_type="spherical", 
                                n_init=100, 
                                random_state=42)

    unsup.fit(np.reshape(df,(-1,df.shape[1])))
    regime = unsup.predict(np.reshape(df,(-1,df.shape[1])))
    # Now let us calculate the returns of the day.
    df['Return']= np.log(df['close']/df['close'].shift(1))

    regime = regime[:-1]
    Regimes=pd.DataFrame(regime,columns=['Regime'],index=df.index)\
            .join(df, how='inner')\
            .assign(market_cu_return=df.Return.cumsum())\
            .reset_index(drop=False)\
            .rename(columns={'index':'Date'})

    # Convert 'Date' column to datetime format
    Regimes['Date'] = pd.to_datetime(Regimes['Date'])
    
    # Set the desired range of dates on the x-axis
    plt.xlim(pd.Timestamp('2024-01-01'), pd.Timestamp('2024-12-31'))
    
    # Set the x-axis tick format to display only the years
    plt.gca().xaxis.set_major_locator(mdates.YearLocator(base=1))
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    
    order = [0, 1, 2, 3]
    fig = sns.FacetGrid(data=Regimes, hue='Regime', hue_order=order, aspect=2, height=4)
    fig.map(plt.scatter, 'Date', 'market_cu_return', s=4).add_legend()
    
    plt.show()
    
main()
