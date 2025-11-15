"""BitMart exchange API implementation"""

import time
import hmac
import hashlib
import json
import requests
import logging

logger = logging.getLogger(__name__)


class ExchangeBitMart:
    """Wrapper class for BitMart exchange API functions"""
    
    def __init__(self, api_key, secret_key, memo):
        self.name = 'bitmart'
        self.api_key = api_key
        self.secret_key = secret_key
        self.memo = memo
        self.client = None
        if api_key and secret_key and memo:
            try:
                from bitmart.api_spot import APISpot
                self.client = APISpot(api_key=api_key, secret_key=secret_key, memo=memo, timeout=(2, 10))
            except ImportError:
                logger.error("BitMart SDK not installed. Install with: pip install bitmart-python-sdk-api")
            except Exception as e:
                logger.error(f"Error initializing BitMart client: {e}")
    
    def get_balance(self):
        """Get account balance"""
        if not self.client:
            return None
        try:
            response = self.client.get_wallet()
            if response and len(response) > 0:
                result = response[0]
                if result.get('code') == 1000:
                    # Convert BitMart balance format to dict
                    balance_dict = {}
                    for wallet in result.get('data', {}).get('wallet', []):
                        currency = wallet.get('id')
                        available = float(wallet.get('available', 0))
                        balance_dict[currency] = str(available)
                    return balance_dict
            return None
        except Exception as e:
            logger.error(f"Error getting BitMart balance: {e}")
            return None
    
    def get_tradable_pairs(self):
        """Get available trading pairs"""
        if not self.client:
            return None
        try:
            response = self.client.get_symbols_details()
            if response and len(response) > 0:
                result = response[0]
                if result.get('code') == 1000:
                    pairs_dict = {}
                    for symbol in result.get('data', {}).get('symbols', []):
                        symbol_id = symbol.get('symbol')
                        pairs_dict[symbol_id] = {
                            'base': symbol.get('base_currency'),
                            'quote': symbol.get('quote_currency'),
                            'ordermin': symbol.get('min_amount', '0'),
                            'pair_decimals': symbol.get('price_precision', 8),
                            'lot_decimals': symbol.get('size_precision', 8),
                        }
                    return pairs_dict
            return None
        except Exception as e:
            logger.error(f"Error getting BitMart trading pairs: {e}")
            return None
    
    def get_ticker(self, pair):
        """Get current price/ticker"""
        if not self.client:
            return None
        try:
            bitmart_pair = self.get_pair_format(pair)
            response = self.client.get_v3_ticker(symbol=bitmart_pair)
            if response and len(response) > 0:
                result = response[0]
                if result.get('code') == 1000:
                    ticker_data = result.get('data', {}).get('ticker', {})
                    # Convert to Kraken-like format
                    return {
                        bitmart_pair: {
                            'c': [ticker_data.get('last_price', '0'), '0', '0'],
                            'v': [ticker_data.get('base_vol_24h', '0'), '0'],
                        }
                    }
            return None
        except Exception as e:
            logger.error(f"Error getting BitMart ticker for {pair}: {e}")
            return None
    
    def get_order_book(self, pair, count=10):
        """Get order book depth"""
        if not self.client:
            return None
        try:
            bitmart_pair = self.get_pair_format(pair)
            response = self.client.get_v3_depth(symbol=bitmart_pair)
            if response and len(response) > 0:
                result = response[0]
                if result.get('code') == 1000:
                    depth_data = result.get('data', {})
                    return {
                        bitmart_pair: {
                            'bids': [[bid[0], bid[1]] for bid in depth_data.get('bids', [])[:count]],
                            'asks': [[ask[0], ask[1]] for ask in depth_data.get('asks', [])[:count]],
                        }
                    }
            return None
        except Exception as e:
            logger.error(f"Error getting BitMart order book for {pair}: {e}")
            return None
    
    def place_buy_order(self, pair, volume, price):
        """Place buy order"""
        if not self.client:
            return None
        try:
            bitmart_pair = self.get_pair_format(pair)
            response = self.client.post_submit_order(
                symbol=bitmart_pair,
                side='buy',
                type='limit',
                size=str(volume),
                price=str(price)
            )
            if response and len(response) > 0:
                result = response[0]
                if result.get('code') == 1000:
                    order_data = result.get('data', {})
                    return {'txid': [order_data.get('order_id')]}
            return None
        except Exception as e:
            logger.error(f"Error placing BitMart buy order: {e}")
            return None
    
    def place_sell_order(self, pair, volume, price):
        """Place sell order"""
        if not self.client:
            return None
        try:
            bitmart_pair = self.get_pair_format(pair)
            response = self.client.post_submit_order(
                symbol=bitmart_pair,
                side='sell',
                type='limit',
                size=str(volume),
                price=str(price)
            )
            if response and len(response) > 0:
                result = response[0]
                if result.get('code') == 1000:
                    order_data = result.get('data', {})
                    return {'txid': [order_data.get('order_id')]}
            return None
        except Exception as e:
            logger.error(f"Error placing BitMart sell order: {e}")
            return None
    
    def get_open_orders(self):
        """Get open orders"""
        if not self.client:
            return None
        try:
            # Try different method names that might exist in the SDK
            response = None
            if hasattr(self.client, 'get_v3_open_orders'):
                response = self.client.get_v3_open_orders()
            elif hasattr(self.client, 'get_open_orders'):
                response = self.client.get_open_orders()
            elif hasattr(self.client, 'get_v3_orders'):
                response = self.client.get_v3_orders(status='open')
            elif hasattr(self.client, 'get_v4_query_open_orders'):
                response = self.client.get_v4_query_open_orders()
            else:
                # Fallback: use direct API call
                logger.warning("BitMart SDK method not found, using direct API call")
                return self._get_open_orders_direct()
            
            if response and len(response) > 0:
                result = response[0]
                if result.get('code') == 1000:
                    orders_dict = {}
                    orders_list = result.get('data', {}).get('orders', [])
                    if not orders_list and 'data' in result.get('data', {}):
                        # Try alternative data structure
                        orders_list = result.get('data', {}).get('data', {}).get('orders', [])
                    for order in orders_list:
                        order_id = order.get('order_id') or order.get('id')
                        if order_id:
                            orders_dict[order_id] = {
                                'opentm': order.get('create_time', order.get('timestamp', time.time())),
                                'descr': {
                                    'pair': order.get('symbol'),
                                    'type': order.get('side', order.get('type')),
                                },
                                'price': order.get('price'),
                                'vol': order.get('size', order.get('amount')),
                                'vol_exec': order.get('filled_size', order.get('filled_amount', '0')),
                            }
                    return {'open': orders_dict}
            return {'open': {}}
        except Exception as e:
            logger.error(f"Error getting BitMart open orders: {e}")
            # Try direct API call as fallback
            try:
                return self._get_open_orders_direct()
            except Exception as e2:
                logger.error(f"Error in fallback BitMart open orders: {e2}")
                return None
    
    def _get_open_orders_direct(self):
        """Direct API call to BitMart v4 endpoint for open orders"""
        timestamp = str(int(time.time() * 1000))
        path = '/spot/v4/query/open-orders'
        body = {
            'orderMode': 'spot',
            'limit': 100
        }
        body_str = json.dumps(body)
        message = f'{timestamp}#{self.memo}#{body_str}'
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            'Content-Type': 'application/json',
            'X-BM-KEY': self.api_key,
            'X-BM-TIMESTAMP': timestamp,
            'X-BM-SIGN': signature
        }
        
        url = f'https://api-cloud.bitmart.com{path}'
        response = requests.post(url, headers=headers, json=body, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('code') == 1000:
                orders_dict = {}
                for order in result.get('data', {}).get('orders', []):
                    order_id = order.get('order_id')
                    if order_id:
                        orders_dict[order_id] = {
                            'opentm': order.get('create_time', time.time()),
                            'descr': {
                                'pair': order.get('symbol'),
                                'type': order.get('side'),
                            },
                            'price': order.get('price'),
                            'vol': order.get('size'),
                            'vol_exec': order.get('filled_size', '0'),
                        }
                return {'open': orders_dict}
        return {'open': {}}
    
    def get_closed_orders(self, since=None):
        """Get filled orders"""
        if not self.client:
            return None
        try:
            # Try different method names that might exist in the SDK
            response = None
            if hasattr(self.client, 'get_v3_order_history'):
                response = self.client.get_v3_order_history()
            elif hasattr(self.client, 'get_order_history'):
                response = self.client.get_order_history()
            elif hasattr(self.client, 'get_v3_orders'):
                response = self.client.get_v3_orders(status='filled')
            elif hasattr(self.client, 'get_v4_query_order_history'):
                response = self.client.get_v4_query_order_history()
            else:
                # Fallback: use direct API call
                logger.warning("BitMart SDK method not found, using direct API call")
                return self._get_closed_orders_direct(since)
            
            if response and len(response) > 0:
                result = response[0]
                if result.get('code') == 1000:
                    closed_dict = {}
                    orders_list = result.get('data', {}).get('orders', [])
                    if not orders_list and 'data' in result.get('data', {}):
                        orders_list = result.get('data', {}).get('data', {}).get('orders', [])
                    for order in orders_list:
                        order_id = order.get('order_id') or order.get('id')
                        create_time = order.get('create_time', order.get('timestamp', time.time()))
                        # Filter by since if provided
                        if since and create_time < since:
                            continue
                        if order.get('status') in ['FILLED', 'filled', 'FULLY_FILLED']:
                            if order_id:
                                closed_dict[order_id] = {
                                    'closetm': order.get('update_time', create_time),
                                    'status': 'closed',
                                    'descr': {
                                        'pair': order.get('symbol'),
                                        'type': order.get('side', order.get('type')),
                                    },
                                    'price': order.get('price'),
                                    'vol': order.get('size', order.get('amount')),
                                    'vol_exec': order.get('filled_size', order.get('filled_amount', '0')),
                                    'cost': str(float(order.get('price', 0)) * float(order.get('filled_size', order.get('filled_amount', 0)))),
                                    'fee': order.get('fee', '0'),
                                }
                    return {'closed': closed_dict}
            return {'closed': {}}
        except Exception as e:
            logger.error(f"Error getting BitMart closed orders: {e}")
            # Try direct API call as fallback
            try:
                return self._get_closed_orders_direct(since)
            except Exception as e2:
                logger.error(f"Error in fallback BitMart closed orders: {e2}")
                return None
    
    def _get_closed_orders_direct(self, since=None):
        """Direct API call to BitMart v4 endpoint for order history"""
        timestamp = str(int(time.time() * 1000))
        path = '/spot/v4/query/order-history'
        body = {
            'orderMode': 'spot',
            'limit': 100
        }
        if since:
            body['startTime'] = int(since * 1000)
        body_str = json.dumps(body)
        message = f'{timestamp}#{self.memo}#{body_str}'
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            'Content-Type': 'application/json',
            'X-BM-KEY': self.api_key,
            'X-BM-TIMESTAMP': timestamp,
            'X-BM-SIGN': signature
        }
        
        url = f'https://api-cloud.bitmart.com{path}'
        response = requests.post(url, headers=headers, json=body, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('code') == 1000:
                closed_dict = {}
                for order in result.get('data', {}).get('orders', []):
                    order_id = order.get('order_id')
                    create_time = order.get('create_time', time.time()) / 1000  # Convert from milliseconds
                    if since and create_time < since:
                        continue
                    if order.get('status') in ['FILLED', 'filled', 'FULLY_FILLED']:
                        if order_id:
                            closed_dict[order_id] = {
                                'closetm': order.get('update_time', create_time) / 1000 if order.get('update_time') else create_time,
                                'status': 'closed',
                                'descr': {
                                    'pair': order.get('symbol'),
                                    'type': order.get('side'),
                                },
                                'price': order.get('price'),
                                'vol': order.get('size'),
                                'vol_exec': order.get('filled_size', '0'),
                                'cost': str(float(order.get('price', 0)) * float(order.get('filled_size', 0))),
                                'fee': order.get('fee', '0'),
                            }
                return {'closed': closed_dict}
        return {'closed': {}}
    
    def cancel_order(self, order_id):
        """Cancel order"""
        if not self.client:
            return None
        try:
            response = self.client.post_cancel_order(order_id=order_id)
            if response and len(response) > 0:
                result = response[0]
                if result.get('code') == 1000:
                    return {'count': 1}
            return None
        except Exception as e:
            logger.error(f"Error canceling BitMart order: {e}")
            return None
    
    def get_currency_code(self, pair):
        """Map pair to exchange currency code (BitMart uses standard codes)"""
        # Extract base currency
        if '_' in pair:
            base_currency = pair.split('_')[0]
        elif pair.endswith('USDT'):
            base_currency = pair[:-4]
        else:
            base_currency = pair[:-4] if len(pair) > 4 else pair
        return base_currency
    
    def normalize_pair(self, pair):
        """Normalize pair format for this exchange (BitMart uses BTC_USDT)"""
        # BitMart uses underscore separator, so convert BTCUSDT -> BTC_USDT
        if '_' not in pair and len(pair) > 4:
            # Assume format like BTCUSDT
            if pair.endswith('USDT'):
                return pair[:-4] + '_USDT'
            elif pair.endswith('USD'):
                return pair[:-3] + '_USD'
            elif pair.endswith('BTC'):
                return pair[:-3] + '_BTC'
            elif pair.endswith('ETH'):
                return pair[:-3] + '_ETH'
        return pair
    
    def get_pair_format(self, normalized_pair):
        """Get exchange-specific pair format"""
        return self.normalize_pair(normalized_pair)

