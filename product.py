import requests, json

def unwrap(arg):
    response = json.loads(arg.text)
    pp = json.dumps(response, indent=4)
    return (pp)

def order_book(product_id, size):
    #unused
    url = f'https://api.exchange.coinbase.com/products/{product_id}/book?level=2'
    headers = {"Accept": "application/json"}
    response = requests.request("GET", url, headers=headers)
    response = json.loads(response.text)
    print('### Buys ###')
    for bid in response['bids']:
        if float(bid[1]) >= size:
            print(f'BID:: {bid[0]}: {bid[1]}')
    print('### End Buys ###')
    print('### Sells ###')
    for ask in response['asks']:
        if float(ask[1]) >= size:
            print(f'ASK:: {ask[0]}: {ask[1]}')
    print('### End Sells ###')

def trades(product_id):
    #unused
    url = f'https://api.exchange.coinbase.com/products/{product_id}/trades?limit=32'
    headers = {"Accept": "application/json"}
    response = requests.request("GET", url, headers=headers)
    response = unwrap(response)
    return (response)

def candles(product_id, seconds, start=0, end=0):
    # seconds must be from {60, 300, 900, 3600, 21600, 86400}
    # start and end are ISO8601 format
    if (start and end != 0):
        url = f"https://api.exchange.coinbase.com/products/{product_id}/candles?granularity={seconds}&start={start}&end={end}"
    else:
        url = f"https://api.exchange.coinbase.com/products/{product_id}/candles?granularity={seconds}"
    headers = {"Accept": "application/json"}
    response = requests.request("GET", url, headers=headers)
    # [time, low, high, open, close, volume]
    response = unwrap(response)
    return (response)

def ticker(product_id):
    url = f"https://api.exchange.coinbase.com/products/{product_id}/ticker"
    headers = {"Accept": "application/json"}
    response = requests.request("GET", url, headers=headers)
    respones = unwrap(response)
    return (response)
