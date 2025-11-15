"""Kraken exchange API implementation"""

import os
import requests
import hashlib
import base64
import hmac
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode
import config

logger = logging.getLogger(__name__)

API_URL = "https://api.kraken.com"
API_VERSION = "0"


def get_kraken_signature(urlpath, data, secret):
    """Generate Kraken API signature"""
    postdata = urlencode(data)
    encoded = (str(data["nonce"]) + postdata).encode()
    message = urlpath.encode() + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
    asig = base64.b64encode(mac.digest())
    return asig.decode()


def kraken_request(url_path, data, api_key, api_secret):
    """Make a request to Kraken API"""
    headers = {"API-Key": api_key}
    data["nonce"] = int(1000 * time.time())
    headers["API-Sign"] = get_kraken_signature(url_path, data, api_secret)
    
    try:
        response = requests.post(
            API_URL + url_path,
            headers=headers,
            data=data,
            timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None


def get_account_balance_kraken(api_key, api_secret):
    """Get account balance from Kraken"""
    url_path = f"/{API_VERSION}/private/Balance"
    response = kraken_request(url_path, {}, api_key, api_secret)
    if response and response["error"]:
        print("Error getting account balance: " + str(response["error"]))
        return None
    return response["result"]


def get_tradable_asset_pairs_kraken(api_key, api_secret):
    """Get tradable asset pairs from Kraken"""
    url_path = f"/{API_VERSION}/public/AssetPairs"
    print("[DEBUG] Sending request to Kraken for asset pairs...")
    response = kraken_request(url_path, {}, api_key, api_secret)
    print(f"[DEBUG] Tradable asset pairs count: {len(response['result'])}")
    if response and response["error"]:
        print("Error getting tradable asset pairs: " + str(response["error"]))
        return None
    return response["result"]


def get_ticker_information_kraken(pair, api_key, api_secret):
    """Get ticker information for a pair from Kraken"""
    url_path = f"/{API_VERSION}/public/Ticker"
    data = {"pair": pair}
    response = kraken_request(url_path, data, api_key, api_secret)
    if response and response["error"]:
        print("Error getting ticker information for " +
              pair + ": " + str(response["error"]))
        return None
    return response["result"]


def add_order_kraken(pair, type, ordertype, price, volume, api_key, api_secret, leverage=None, oflags=None):
    """Add an order to Kraken with optional margin support"""
    url_path = f"/{API_VERSION}/private/AddOrder"
    data = {
        "pair": pair,
        "type": type,
        "ordertype": ordertype,
        "price": price,
        "volume": volume
    }

    # Add margin trading parameters if leverage is specified
    if leverage is not None and leverage > 1:
        data["leverage"] = f"{leverage}:1"
        # Add order flags for margin trading
        if oflags:
            data["oflags"] = oflags
        else:
            # Default margin order flags
            data["oflags"] = "fciq"  # fcib (prefer fee in base currency), nompp (no market price protection)

    response = kraken_request(url_path, data, api_key, api_secret)
    if response and response["error"]:
        print("Error adding order: " + str(response["error"]))
        return None
    return response["result"]


def get_trade_balance_kraken(api_key, api_secret):
    """Get trade balance from Kraken (includes margin information)"""
    url_path = f"/{API_VERSION}/private/TradeBalance"
    response = kraken_request(url_path, {}, api_key, api_secret)
    if response and response["error"]:
        print("Error getting trade balance: " + str(response["error"]))
        return None
    return response["result"]


def get_open_orders_kraken(api_key, api_secret):
    """Get all open orders from Kraken"""
    url_path = f"/{API_VERSION}/private/OpenOrders"
    response = kraken_request(url_path, {}, api_key, api_secret)
    if response and response["error"]:
        print("Error getting open orders: " + str(response["error"]))
        return None
    return response["result"]


def cancel_order_kraken(txid, api_key, api_secret):
    """Cancel a specific order by txid"""
    url_path = f"/{API_VERSION}/private/CancelOrder"
    data = {"txid": txid}
    response = kraken_request(url_path, data, api_key, api_secret)
    if response and response["error"]:
        print(f"Error canceling order {txid}: " + str(response["error"]))
        return None
    return response["result"]


def get_closed_orders_kraken(since=None, api_key=None, api_secret=None):
    """Get recently closed orders from Kraken"""
    url_path = f"/{API_VERSION}/private/ClosedOrders"
    data = {}
    if since:
        data["start"] = since

    response = kraken_request(url_path, data, api_key, api_secret)
    if response and response["error"]:
        print("Error getting closed orders: " + str(response["error"]))
        return None
    return response["result"]


def get_order_book_kraken(pair, count=10, api_key=None, api_secret=None):
    """Get order book depth for a pair"""
    url_path = f"/{API_VERSION}/public/Depth"
    data = {"pair": pair, "count": count}
    response = kraken_request(url_path, data, api_key, api_secret)
    if response and response["error"]:
        print(
            f"Error getting order book for {pair}: " + str(response["error"]))
        return None
    return response["result"]


def get_recent_trades_kraken(pair, since=None, api_key=None, api_secret=None):
    """Get recent trades for price movement analysis"""
    url_path = f"/{API_VERSION}/public/Trades"
    data = {"pair": pair}
    if since:
        data["since"] = since
    response = kraken_request(url_path, data, api_key, api_secret)
    if response and response["error"]:
        print(
            f"Error getting recent trades for {pair}: " + str(response["error"]))
        return None
    return response["result"]


def get_sub_cent_tokens(api_key, api_secret):
    """Get sub-cent tokens from Kraken"""
    print("Fetching tradable asset pairs...")
    asset_pairs = get_tradable_asset_pairs_kraken(api_key, api_secret)
    if not asset_pairs:
        return {}

    # Filter for USDT pairs only immediately
    usdt_pairs = {name: info for name, info in asset_pairs.items() 
                  if info.get("quote") == "USDT" and ".d" not in name}
    
    print(f"[DEBUG] Found {len(usdt_pairs)} USDT pairs to check")
    
    sub_cent_tokens = {}
    lock = threading.Lock()  # Thread-safe dictionary updates
    
    def check_pair(pair_name, pair_info):
        """Check a single pair for sub-cent pricing"""
        try:
            ticker_info = get_ticker_information_kraken(pair_name, api_key, api_secret)
            if ticker_info and pair_name in ticker_info:
                last_price = float(ticker_info[pair_name]["c"][0])
                if last_price <= config.MAX_TOKEN_PRICE:
                    with lock:
                        sub_cent_tokens[pair_name] = pair_info
                    print(f"[DEBUG] ADDED: {pair_name} - Price: {last_price}")
                    return pair_name, pair_info, last_price
                else:
                    print(
                        f"[DEBUG] SKIPPED (price too high): {pair_name} - Price: {last_price} > {config.MAX_TOKEN_PRICE}")
            else:
                print(f"[DEBUG] No ticker info found for {pair_name}")
        except Exception as e:
            print(f"[DEBUG] Error processing {pair_name}: {e}")
        return None
    
    # Use ThreadPoolExecutor to process pairs concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all tasks
        future_to_pair = {
            executor.submit(check_pair, pair_name, pair_info): pair_name 
            for pair_name, pair_info in usdt_pairs.items()
        }
        
        # Process completed tasks
        for future in as_completed(future_to_pair):
            pair_name = future_to_pair[future]
            try:
                result = future.result()
                if result:
                    print(f"[DEBUG] Completed processing: {result[0]}")
            except Exception as e:
                print(f"[DEBUG] Exception for {pair_name}: {e}")
    
    print(f"[DEBUG] Final sub-cent tokens found: {len(sub_cent_tokens)}")
    return sub_cent_tokens


class ExchangeKraken:
    """Wrapper class for Kraken exchange API functions"""
    
    def __init__(self, api_key, api_secret):
        self.name = 'kraken'
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_url = "https://api.kraken.com"
        self.api_version = "0"
    
    def get_balance(self):
        """Get account balance"""
        return get_account_balance_kraken(self.api_key, self.api_secret)

    def get_trade_balance(self):
        """Get trade balance (includes margin information)"""
        return get_trade_balance_kraken(self.api_key, self.api_secret)
    
    def get_tradable_pairs(self):
        """Get available trading pairs"""
        return get_tradable_asset_pairs_kraken(self.api_key, self.api_secret)
    
    def get_ticker(self, pair):
        """Get current price/ticker"""
        return get_ticker_information_kraken(pair, self.api_key, self.api_secret)
    
    def get_order_book(self, pair, count=10):
        """Get order book depth"""
        return get_order_book_kraken(pair, count, self.api_key, self.api_secret)
    
    def place_buy_order(self, pair, volume, price, leverage=None):
        """Place buy order with optional margin support"""
        return add_order_kraken(pair=pair, type='buy', ordertype='limit', price=str(price), volume=str(volume), api_key=self.api_key, api_secret=self.api_secret, leverage=leverage)

    def place_sell_order(self, pair, volume, price, leverage=None):
        """Place sell order with optional margin support"""
        return add_order_kraken(pair=pair, type='sell', ordertype='limit', price=str(price), volume=str(volume), api_key=self.api_key, api_secret=self.api_secret, leverage=leverage)
    
    def get_open_orders(self):
        """Get open orders"""
        return get_open_orders_kraken(self.api_key, self.api_secret)
    
    def get_closed_orders(self, since=None):
        """Get filled orders"""
        return get_closed_orders_kraken(since=since, api_key=self.api_key, api_secret=self.api_secret)
    
    def cancel_order(self, order_id):
        """Cancel order"""
        return cancel_order_kraken(order_id, self.api_key, self.api_secret)
    
    def get_currency_code(self, pair):
        """Map pair to exchange currency code"""
        # Extract base currency
        if '/' in pair:
            base_currency = pair.split('/')[0]
        elif pair.endswith('USDT'):
            base_currency = pair[:-4]
        elif pair.endswith(('USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD')):
            base_currency = pair[:-3]
        elif pair.endswith(('BTC', 'ETH', 'ADA', 'DOT', 'SOL')):
            base_currency = pair[:-3]
        else:
            base_currency = pair.split('_')[0] if '_' in pair else pair
        
        # Get Kraken currency code from asset pairs API
        asset_pairs = self.get_tradable_pairs()
        if asset_pairs and pair in asset_pairs:
            return asset_pairs[pair].get('base')
        
        # Fallback mapping
        kraken_currency_map = {
            'BTC': 'XXBT', 'ETH': 'XETH', 'LTC': 'XLTC', 'XRP': 'XXRP',
            'ADA': 'ADA', 'DOT': 'DOT', 'SOL': 'SOL', 'XDG': 'XXDG',
            'ALGO': 'ALGO', 'KAS': 'KAS', 'PENGU': 'PENGU', 'MELANIA': 'MELANIA',
            'UST': 'UST', 'SHIB': 'SHIB', 'CC': 'CC',
        }
        return kraken_currency_map.get(base_currency, 'X' + base_currency)
    
    def normalize_pair(self, pair):
        """Normalize pair format for this exchange (Kraken uses BTCUSDT)"""
        # Kraken uses no separator, so convert BTC_USDT -> BTCUSDT
        return pair.replace('_', '')
    
    def get_pair_format(self, normalized_pair):
        """Get exchange-specific pair format"""
        return self.normalize_pair(normalized_pair)

