#!/usr/bin/env python

import os, json, hmac, base64, hashlib, time, requests
from requests.auth import AuthBase

API_KEY = os.environ.get("API_KEY")
API_SECRET = os.environ.get("API_SECRET")
API_PHRASE = os.environ.get("API_PHRASE")

class CoinbaseAuth(AuthBase):
    def __init__(self, api_key, secret_key, api_phrase):
        self.api_key = api_key
        self.secret_key = secret_key
        self.api_phrase = api_phrase

    def __call__(self, request):
        timestamp = int(time.time())
        message = str(timestamp) + request.method + request.path_url
        signature = hmac.new(base64.b64decode(self.secret_key), message.encode(), hashlib.sha256).digest()
        signature = base64.b64encode(signature)
        request.headers.update({
            "Accept": "application/json",
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-PASSPHRASE": self.api_phrase,
        })
        
        return request

def pp_json(args):
    response = json.loads(args.text)
    pp = json.dumps(response, indent=4, sort_keys=True)
    print(pp)

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
    response = json.loads(response.text)
    # response = json.dumps(response)
    return(response)

def submit_order(side, product_id, recent_close, num_shares):
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
    response = json.loads(response.text)
    return(response)

    


# # type str
# resp_txt = json.loads(r.text)
# pp_json = json.dumps(resp_txt, indent=4, sort_keys=True)
# print(pp_json)
# # with open('all_accounts', 'w') as fd:
#     # fd.write(pp_json)

# # type list of json?
# # resp_json = r.json()
# # print(resp_json)
