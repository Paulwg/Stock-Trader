#!/usr/bin/env python
import os, json, hmac, base64, time, hashlib, requests
from requests.auth import AuthBase

API_KEY = os.environ.get("API_KEY")
API_SECRET = os.environ.get("API_SECRET")
API_PHRASE = os.environ.get("API_PHRASE")

class CoinbaseAuth(AuthBase):
    def __init__(self, api_key, api_secret, api_phrase):
        self.api_key = str(api_key)
        self.api_secret = api_secret
        self.api_phrase = str(api_phrase)

    def __call__(self, request):
        timestamp = str(time.time())
        message = f"{timestamp}{request.method}{request.path_url}{request.body.decode('UTF-8') if request.body else ''}"

        key = base64.b64decode(self.api_secret)
        signature = hmac.new(key,bytes(message, encoding="utf-8"),hashlib.sha256)
        cb_access_sign = base64.b64encode(signature.digest())

        request.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "CB-ACCESS-SIGN": cb_access_sign,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-PASSPHRASE": self.api_phrase,
        })
        
        return request

def pp_json(args):
    response = json.loads(args.text)
    pp = json.dumps(response, indent=4)
    print(pp)
    return(pp)

def get_acct():
    api_url = "https://api.exchange.coinbase.com/accounts"
    auth = CoinbaseAuth(API_KEY, API_SECRET, API_PHRASE)
    response = requests.get(api_url, auth=auth)
    pp_json(response)

def get_all_orders():
    api_url = "https://api.exchange.coinbase.com/orders?sortedBy=created_at&sorting=desc&limit=100&status=all" #status=open
    auth = CoinbaseAuth(API_KEY, API_SECRET, API_PHRASE)
    response = requests.get(api_url, auth=auth)
    pp_json(response)

def get_single_order(order_id):
    api_url = f"https://api.exchange.coinbase.com/orders/{order_id}"
    auth = CoinbaseAuth(API_KEY, API_SECRET, API_PHRASE)
    response = requests.get(api_url, auth=auth)
    response = response.json()
    return(response)

def submit_order(side, product_id, recent_close, num_shares):
    print(f'Submitting {side} order: {num_shares} X {product_id} at {recent_close}')
    api_url = "https://api.exchange.coinbase.com/orders"
    
    payload = {
        "type": "limit",
        "side": side,
        "product_id": product_id,
        "price": recent_close,
        "size": num_shares
    }

    auth = CoinbaseAuth(API_KEY, API_SECRET, API_PHRASE)
    response = requests.post(api_url, json=payload, auth=auth)
    response = response.json()
    return(response)