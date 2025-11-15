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
from dotenv import load_dotenv
import config
import trade_analyzer_ml

# Load environment variables
load_dotenv()

API_KEY = os.getenv("KRAKEN_API_KEY")
API_SECRET = os.getenv("KRAKEN_API_SECRET")

# Validate API credentials
if not API_KEY or not API_SECRET:
    raise ValueError("Missing Kraken API credentials. Please check your .env file.")

# Set up logging
log_handlers = []
if config.LOG_TO_FILE:
    log_handlers.append(logging.FileHandler(config.LOG_FILE))
if config.LOG_TO_CONSOLE:
    log_handlers.append(logging.StreamHandler())

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper()),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)
logger = logging.getLogger(__name__)

API_URL = "https://api.kraken.com"
API_VERSION = "0"

# Global variable to track total value of open orders
total_open_order_value = 0.0
# Global variable to track open orders
open_orders = {}
# Global ML analyzer instance
ml_analyzer = None

def get_price_range_category(price):
    """Categorize token price into risk categories"""
    if price <= config.PRICE_RANGE_MED:
        return 'low'
    elif price <= config.PRICE_RANGE_HIGH:
        return 'medium'
    else:
        return 'high'

def get_risk_multiplier(price):
    """Get risk multiplier based on token price"""
    category = get_price_range_category(price)
    if category == 'low':
        return config.RISK_MULTIPLIER_LOW
    elif category == 'medium':
        return config.RISK_MULTIPLIER_MED
    else:
        return config.RISK_MULTIPLIER_HIGH

def get_profit_margin(price):
    """Get appropriate profit margin based on token price"""
    category = get_price_range_category(price)
    if category == 'low':
        return config.PROFIT_MARGIN_LOW
    elif category == 'medium':
        return config.PROFIT_MARGIN_MED
    else:
        return config.PROFIT_MARGIN_HIGH

def get_kraken_signature(urlpath, data, secret):
    postdata = urlencode(data)
    encoded = (str(data["nonce"]) + postdata).encode()
    message = urlpath.encode() + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
    asig = base64.b64encode(mac.digest())
    return asig.decode()

def kraken_request(url_path, data, api_key, api_secret):
    headers = {"API-Key": api_key}
    data["nonce"] = int(1000 * time.time())
    headers["API-Sign"] = get_kraken_signature(url_path, data, api_secret)
    
    try:
        response = requests.post(API_URL + url_path, headers=headers, data=data, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None

def record_trade(trade_data):
    # Calculate profit/loss for sell orders
    if trade_data.get('type') == 'sell':
        profit = calculate_trade_profit(trade_data)
        trade_data['actual_profit'] = profit

    with open("trade_logs/config.TRADES_FILE", "a") as f:
        f.write(str(trade_data) + "\n")
    train_bot(trade_data)

def calculate_trade_profit(sell_trade):
    """
    Calculate profit/loss for a sell trade by matching with corresponding buy trades
    """
    try:
        pair = sell_trade.get('pair')
        sell_volume = sell_trade.get('volume', 0)
        sell_price = sell_trade.get('price', 0)
        sell_fees = sell_trade.get('fees', 0)

        if not pair or sell_volume <= 0 or sell_price <= 0:
            return 0

        # Load existing trades to find matching buys
        buy_trades = []
        if os.path.exists("config.TRADES_FILE"):
            with open("config.TRADES_FILE", "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            trade = eval(line.strip())
                            if (trade.get('type') == 'buy' and
                                trade.get('pair') == pair and
                                not trade.get('fully_matched', False)):  # Only unmatched buys
                                buy_trades.append(trade)
                        except:
                            continue

        # Sort buys by timestamp (FIFO - first in, first out)
        buy_trades.sort(key=lambda x: x.get('timestamp', 0))

        total_cost = 0
        remaining_sell_volume = sell_volume
        matched_volume = 0

        matched_buy_trades = []

        # Match sell volume with buy trades (FIFO)
        for buy_trade in buy_trades:
            if remaining_sell_volume <= 0:
                break

            buy_volume = buy_trade.get('volume', 0)
            matched_volume_already = buy_trade.get('matched_volume', 0)
            available_buy_volume = buy_volume - matched_volume_already

            buy_price = buy_trade.get('price', 0)
            buy_fees = buy_trade.get('fees', 0)

            if available_buy_volume <= 0 or buy_price <= 0:
                continue

            # Calculate how much of this buy to match
            match_volume = min(remaining_sell_volume, available_buy_volume)
            if match_volume <= 0:
                continue

            # Add to total cost
            match_cost = match_volume * buy_price
            match_buy_fees = (match_volume / buy_volume) * buy_fees if buy_volume > 0 else 0
            total_cost += match_cost + match_buy_fees

            # Track matched buy trades for marking as used
            matched_buy_trades.append({
                'trade': buy_trade,
                'matched_volume': match_volume
            })

            remaining_sell_volume -= match_volume
            matched_volume += match_volume

        if matched_volume <= 0:
            logger.warning(f"No matching buy trades found for sell order {sell_trade.get('order_id')} of {pair}")
            return 0

        # Calculate revenue and profit
        revenue = matched_volume * sell_price
        total_sell_fees = (matched_volume / sell_volume) * sell_fees if sell_volume > 0 else 0

        profit = revenue - total_sell_fees - total_cost

        logger.info(".6f")

        # Mark matched buy trades to prevent future double-counting
        update_matched_buy_trades(matched_buy_trades, pair)

        return profit

    except Exception as e:
        logger.error(f"Error calculating trade profit: {e}")
        return 0

def update_matched_buy_trades(matched_buy_trades, pair):
    """
    Update buy trades that were matched in profit calculations to prevent double-counting
    """
    try:
        if not matched_buy_trades:
            return

        # Read all current trades
        all_trades = []
        if os.path.exists("config.TRADES_FILE"):
            with open("config.TRADES_FILE", "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            trade = eval(line.strip())
                            all_trades.append(trade)
                        except:
                            continue

        # Update matched buy trades
        updated_count = 0
        for match_info in matched_buy_trades:
            buy_trade = match_info['trade']
            matched_volume = match_info['matched_volume']

            # Find and update the corresponding trade
            for i, trade in enumerate(all_trades):
                if (trade.get('order_id') == buy_trade.get('order_id') and
                    trade.get('type') == 'buy' and
                    trade.get('pair') == pair):

                    # Mark as matched (could add a flag or reduce remaining volume)
                    trade['matched_volume'] = trade.get('matched_volume', 0) + matched_volume
                    if trade['matched_volume'] >= trade.get('volume', 0):
                        trade['fully_matched'] = True

                    updated_count += 1
                    break

        if updated_count > 0:
            # Write back updated trades
            with open("config.TRADES_FILE", "w") as f:
                for trade in all_trades:
                    f.write(str(trade) + "\n")

            logger.info(f"Updated {updated_count} matched buy trades for {pair}")

    except Exception as e:
        logger.error(f"Error updating matched buy trades: {e}")

def train_bot(trade_data):
    # This function implements learning logic including ML model training
    logger.info(f"Training bot with trade data: {trade_data}")

    # Basic learning: analyze profitability and adjust strategy
    try:
        # Load existing trades for analysis
        trades = []
        if os.path.exists("config.TRADES_FILE"):
            with open("config.TRADES_FILE", "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            trades.append(eval(line.strip()))
                        except:
                            pass

        if trades:
            # Calculate basic statistics
            total_trades = len(trades)
            profitable_trades = sum(1 for t in trades if t.get('profit', 0) > 0)
            total_profit = sum(t.get('profit', 0) for t in trades)

            win_rate = profitable_trades / total_trades if total_trades > 0 else 0

            logger.info(f"Training analysis - Total trades: {total_trades}, Win rate: {win_rate:.2%}, Total profit: {total_profit:.6f}")

            # Try to train/update ML model if ML is enabled and we have enough data
            if config.ML_ENABLED and total_trades >= 20:  # Need minimum data for meaningful ML training
                logger.info("Attempting to train ML model with historical data...")
                ml_success = trade_analyzer_ml.train_ml_model()
                if ml_success:
                    logger.info("ML model training completed successfully")
                else:
                    logger.warning("ML model training failed")
            elif config.ML_ENABLED:
                logger.info(f"Need {20 - total_trades} more trades before ML training")
            else:
                logger.debug("ML training skipped - ML system disabled")

            # Simple learning: adjust position sizes based on recent performance
            if win_rate < 0.3:  # Less than 30% win rate
                logger.warning("Low win rate detected. Consider adjusting strategy parameters.")
            elif win_rate > 0.7:  # More than 70% win rate
                logger.info("High win rate detected. Strategy performing well.")

    except Exception as e:
        logger.error(f"Error in training: {e}")

def get_account_balance_kraken():
    url_path = f"/{API_VERSION}/private/Balance"
    response = kraken_request(url_path, {}, API_KEY, API_SECRET)
    if response and response["error"]:
        print("Error getting account balance: " + str(response["error"]))
        return None
    return response["result"]

def get_tradable_asset_pairs_kraken():
    url_path = f"/{API_VERSION}/public/AssetPairs"
    print("[DEBUG] Sending request to Kraken for asset pairs...")
    response = kraken_request(url_path, {}, API_KEY, API_SECRET)
    print(f"[DEBUG] Response received: {response}")
    if response and response["error"]:
        print("Error getting tradable asset pairs: " + str(response["error"]))
        return None
    return response["result"]

def get_ticker_information_kraken(pair):
    url_path = f"/{API_VERSION}/public/Ticker"
    data = {"pair": pair}
    response = kraken_request(url_path, data, API_KEY, API_SECRET)
    if response and response["error"]:
        print("Error getting ticker information for " + pair + ": " + str(response["error"]))
        return None
    return response["result"]

def add_order_kraken(pair, type, ordertype, price, volume):
    url_path = f"/{API_VERSION}/private/AddOrder"
    data = {
        "pair": pair,
        "type": type,
        "ordertype": ordertype,
        "price": price,
        "volume": volume
    }
    response = kraken_request(url_path, data, API_KEY, API_SECRET)
    if response and response["error"]:
        print("Error adding order: " + str(response["error"]))
        return None
    return response["result"]

def get_sub_cent_tokens():
    print("Fetching tradable asset pairs...")
    asset_pairs = get_tradable_asset_pairs_kraken()
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
            ticker_info = get_ticker_information_kraken(pair_name)
            if ticker_info and pair_name in ticker_info:
                last_price = float(ticker_info[pair_name]["c"][0])
                if last_price <= config.MAX_TOKEN_PRICE:  # Use config value instead of hardcoded 0.1
                    with lock:
                        sub_cent_tokens[pair_name] = pair_info
                    print(f"[DEBUG] ADDED: {pair_name} - Price: {last_price}")
                    return pair_name, pair_info, last_price
                else:
                    print(f"[DEBUG] SKIPPED (price too high): {pair_name} - Price: {last_price} > {config.MAX_TOKEN_PRICE}")
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

def simple_trading_strategy(pair, current_price, fees, account_balance, ordermin, pair_decimals):
    global total_open_order_value
    
    print(f"Applying price-adjusted strategy for {pair} at price {current_price}")

    # Get price-based risk adjustments
    risk_multiplier = get_risk_multiplier(current_price)
    price_category = get_price_range_category(current_price)

    # Get pair information for decimal precision
    asset_pairs = get_tradable_asset_pairs_kraken()
    if asset_pairs and pair in asset_pairs:
        pair_info = asset_pairs[pair]
        lot_decimals = pair_info.get("lot_decimals", 8)
        price_decimals = pair_info.get("pair_decimals", pair_decimals)  # Use passed value or API value
    else:
        lot_decimals = 8
        price_decimals = pair_decimals

    print(f"[DEBUG] Using {price_decimals} price decimals and {lot_decimals} lot decimals for {pair}")

    print(f"[DEBUG] Price category: {price_category}, Risk multiplier: {risk_multiplier}")

    # Calculate maximum trading amount with price-based adjustments
    base_max_trade_amount = account_balance * config.MAX_ACCOUNT_USAGE_PERCENT
    max_total_trade_amount = base_max_trade_amount * risk_multiplier
    max_trade_as_percentage = (max_total_trade_amount / account_balance) * 100

    print(f"[DEBUG] Account balance: {account_balance}")
    print(f"[DEBUG] Base max trade amount ({config.MAX_ACCOUNT_USAGE_PERCENT*100}%): {base_max_trade_amount}")
    print(f"[DEBUG] Adjusted max trade amount ({max_trade_as_percentage:.1f}%): {max_total_trade_amount}")
    print(f"[DEBUG] Current total open order value: {total_open_order_value}")
    
    # Check if we can place another order without exceeding limit
    remaining_budget = max_total_trade_amount - total_open_order_value
    if remaining_budget <= 0:
        print(f"[DEBUG] Cannot place order for {pair}: Already at {max_trade_as_percentage:.1f}% limit")
        return
    
    # Calculate how much of the token we can buy with remaining budget
    fee_multiplier = 1 + fees
    max_volume = remaining_budget / (current_price * fee_multiplier)
    
    # Apply price-based trade size limit
    trade_size_limit = config.MAX_TRADE_SIZE_PERCENT * risk_multiplier
    max_volume = max_volume * trade_size_limit

    print(f"[DEBUG] Trade size limit: {trade_size_limit:.2f} ({trade_size_limit*100:.1f}% of remaining budget)")
    
    # Ensure ordermin is a float
    ordermin = float(ordermin)

    print(f"[DEBUG] Order minimum: {ordermin}, calculated max volume: {max_volume}")

    # Ensure we trade at least the minimum volume, rounded to lot decimals
    volume_to_trade = max(round(max_volume, lot_decimals), ordermin)
    
    if volume_to_trade <= 0:
        print(f"[DEBUG] Insufficient remaining budget to trade {pair}")
        return

    # Additional check: ensure the volume meets ordermin after rounding
    if volume_to_trade < ordermin:
        print(f"[DEBUG] Calculated volume {volume_to_trade} below ordermin {ordermin} for {pair}")
        return

    print(f"[DEBUG] Final volume to trade: {volume_to_trade} (ordermin: {ordermin})")
    
    # Calculate the actual cost of this order
    order_cost = volume_to_trade * current_price * fee_multiplier
    
    # Double-check we're not exceeding the 5% limit
    if total_open_order_value + order_cost > max_total_trade_amount:
        print(f"[DEBUG] Order would exceed {max_trade_as_percentage}% limit. Skipping {pair}")
        return
    
    print(f"[DEBUG] Attempting to buy {volume_to_trade} {pair} at {current_price}")
    
    try:
        # Use dynamic pricing instead of fixed 99% of current price
        price_decimals_int = int(price_decimals)
        buy_price = calculate_dynamic_buy_price(pair, current_price, price_decimals_int)
        print(f"Attempting to place buy order for {volume_to_trade} {pair} at {buy_price}")
        order = add_order_kraken(pair=pair, type='buy', ordertype='limit', price=str(buy_price), volume=str(volume_to_trade))
        if order:
            print(f"Placed buy order for {pair}: {order}")
            # Update total open order value
            total_open_order_value += order_cost
            print(f"[DEBUG] Updated total open order value: {total_open_order_value}")
            # Note: Trade will be recorded when order is actually filled
        else:
            print(f"Failed to place buy order for {pair}.")
    except Exception as e:
        print(f"Error placing buy order: {e}")

def get_open_orders_kraken():
    """Get all open orders from Kraken"""
    url_path = f"/{API_VERSION}/private/OpenOrders"
    response = kraken_request(url_path, {}, API_KEY, API_SECRET)
    if response and response["error"]:
        print("Error getting open orders: " + str(response["error"]))
        return None
    return response["result"]

def cancel_order_kraken(txid):
    """Cancel a specific order by txid"""
    url_path = f"/{API_VERSION}/private/CancelOrder"
    data = {"txid": txid}
    response = kraken_request(url_path, data, API_KEY, API_SECRET)
    if response and response["error"]:
        print(f"Error canceling order {txid}: " + str(response["error"]))
        return None
    return response["result"]

def manage_open_orders():
    """Manage existing open orders - cancel old ones and adjust prices"""
    global total_open_order_value, open_orders
    
    print("[DEBUG] Managing open orders...")
    open_orders_response = get_open_orders_kraken()
    
    if not open_orders_response:
        print("[DEBUG] No open orders found or error getting orders")
        return False
    
    current_time = time.time()
    orders_to_cancel = []
    total_open_order_value = 0.0  # Reset and recalculate
    
    try:
        for txid, order_info in open_orders_response["open"].items():
            try:
                # Check if required fields exist
                if not all(key in order_info for key in ["opentm", "descr"]):
                    print(f"[DEBUG] Skipping order {txid}: Missing required fields")
                    continue

                # Debug: Log the full order_info if price is 0 or missing
                price_raw = order_info.get("descr", {}).get("price", 0)
                try:
                    price_float = float(price_raw)
                    if price_float <= 0:
                        print(f"[DEBUG] Order {txid} has invalid price {price_raw}. Full order_info: {order_info}")
                        continue
                except (ValueError, TypeError):
                    print(f"[DEBUG] Order {txid} has non-numeric price {price_raw}. Full order_info: {order_info}")
                    continue
                
                order_time = float(order_info["opentm"])
                time_open = current_time - order_time
                descr = order_info["descr"]
                pair = descr.get("pair", "UNKNOWN")
                price = price_float  # Already validated above
                volume = float(order_info.get("vol", 0))
                order_type = descr.get("type", "unknown")

                # Validate volume is reasonable
                if volume <= 0:
                    print(f"[DEBUG] Skipping order {txid}: Invalid volume {volume}")
                    continue

                print(f"[DEBUG] Processing order {txid}: {order_type} {pair} {volume} @ {price}")
                
                # Calculate order value
                order_value = price * volume
                total_open_order_value += order_value
                
                # Cancel orders older than 30 minutes (1800 seconds)
                if time_open > 1800:
                    print(f"[DEBUG] Order {txid} is {time_open/60:.1f} minutes old, canceling...")
                    orders_to_cancel.append(txid)
                    continue
                
                # Adjust price for orders older than 10 minutes
                if time_open > 600:
                    print(f"[DEBUG] Order {txid} is {time_open/60:.1f} minutes old, checking for price adjustment...")
                    
                    # Get current market price
                    ticker_info = get_ticker_information_kraken(pair)
                    if ticker_info and pair in ticker_info:
                        current_price = float(ticker_info[pair]["c"][0])
                        
                        # If order is buy and current price is much lower, cancel and re-place
                        if order_type == "buy" and current_price < price * 0.95:
                            print(f"[DEBUG] Current price {current_price} is much lower than order price {price}, canceling...")
                            orders_to_cancel.append(txid)
                            continue
                        
                        # If order is buy and current price is higher, adjust order price
                        elif order_type == "buy" and current_price > price * 1.02:
                            print(f"[DEBUG] Current price {current_price} is higher than order price {price}, adjusting...")
                            orders_to_cancel.append(txid)
                            # Re-place order at better price (will be done in main loop)
                            continue
                            
            except (KeyError, ValueError, TypeError) as e:
                print(f"[DEBUG] Error processing order {txid}: {e}")
                continue
        
        # Cancel orders that need to be canceled
        for txid in orders_to_cancel:
            try:
                cancel_result = cancel_order_kraken(txid)
                if cancel_result:
                    print(f"[DEBUG] Successfully canceled order {txid}")
                else:
                    print(f"[DEBUG] Failed to cancel order {txid}")
            except Exception as e:
                print(f"[DEBUG] Error canceling order {txid}: {e}")
        
        print(f"[DEBUG] Updated total open order value: {total_open_order_value}")
        return len(orders_to_cancel) > 0  # Return True if orders were canceled
        
    except Exception as e:
        print(f"[DEBUG] Error in manage_open_orders: {e}")
        return False

def get_order_book_kraken(pair, count=10):
    """Get order book depth for a pair"""
    url_path = f"/{API_VERSION}/public/Depth"
    data = {"pair": pair, "count": count}
    response = kraken_request(url_path, data, API_KEY, API_SECRET)
    if response and response["error"]:
        print(f"Error getting order book for {pair}: " + str(response["error"]))
        return None
    return response["result"]

def get_recent_trades_kraken(pair, since=None):
    """Get recent trades for price movement analysis"""
    url_path = f"/{API_VERSION}/public/Trades"
    data = {"pair": pair}
    if since:
        data["since"] = since
    response = kraken_request(url_path, data, API_KEY, API_SECRET)
    if response and response["error"]:
        print(f"Error getting recent trades for {pair}: " + str(response["error"]))
        return None
    return response["result"]

def analyze_price_movement(pair):
    """Analyze recent price movement to determine trend"""
    trades = get_recent_trades_kraken(pair)
    if not trades or pair not in trades:
        return "neutral"
    
    recent_trades = trades[pair][-20:]  # Last 20 trades
    if len(recent_trades) < 10:
        return "neutral"
    
    # Calculate price changes
    price_changes = []
    for i in range(1, len(recent_trades)):
        prev_price = float(recent_trades[i-1][0])
        curr_price = float(recent_trades[i][0])
        change = (curr_price - prev_price) / prev_price
        price_changes.append(change)
    
    # Determine trend
    avg_change = sum(price_changes) / len(price_changes)
    if avg_change > 0.001:  # 0.1% average increase
        return "rising"
    elif avg_change < -0.001:  # 0.1% average decrease
        return "falling"
    else:
        return "neutral"

def calculate_dynamic_buy_price(pair, current_price, lot_decimals):
    """Calculate aggressive buy price for quick fills and fast trading"""

    # Get order book for best bid price
    order_book = get_order_book_kraken(pair, count=10)
    if order_book and pair in order_book:
        bids = order_book[pair].get("bids", [])
        if bids:
            best_bid = float(bids[0][0])
            # For aggressive quick fills: place order just above the best bid
            # This ensures immediate fill in most cases
            buy_price = best_bid * 1.0001  # 0.01% above best bid
            print(f"[DEBUG] Aggressive buy: best_bid={best_bid:.6f}, buy_price={buy_price:.6f}")
        else:
            # Fallback: very close to current price
            buy_price = current_price * 1.0002  # 0.02% above current
            print(f"[DEBUG] No bids found, using current price: {buy_price:.6f}")
    else:
        # Ultimate fallback: very close to current price for guaranteed fills
        buy_price = current_price * 1.0001  # 0.01% above current
        print(f"[DEBUG] No order book, using current price: {buy_price:.6f}")

    # Ensure we don't set price too high (sanity check)
    max_reasonable_price = current_price * 1.01  # Max 1% above current
    buy_price = min(buy_price, max_reasonable_price)
    
    # Round to appropriate decimal places
    buy_price = round(buy_price, lot_decimals)
    
    print(f"[DEBUG] Final aggressive buy price for {pair}: {buy_price:.6f} (current: {current_price:.6f})")
    
    return buy_price

def get_closed_orders_kraken(since=None):
    """Get recently closed orders from Kraken"""
    url_path = f"/{API_VERSION}/private/ClosedOrders"
    data = {}
    if since:
        data["start"] = since  # Use 'start' parameter to filter by timestamp

    response = kraken_request(url_path, data, API_KEY, API_SECRET)
    if response and response["error"]:
        print("Error getting closed orders: " + str(response["error"]))
        return None
    return response["result"]

def check_and_record_completed_trades():
    """Check for recently completed trades and record them for training"""
    try:
        # Only check orders from the last 30 minutes to focus on recent fills
        # This prevents processing old orders that may have already been handled
        since = int(time.time() - 1800)  # Last 30 minutes
        closed_orders = get_closed_orders_kraken(since=since)

        if not closed_orders:
            return
        
        # Track which orders we've already recorded to avoid duplicates
        recorded_orders = {}  # dict: order_id -> {'time': timestamp, 'exchange': exchange_name, 'status': 'closed'/'open'}

        # Try to load previously recorded orders
        try:
            with open(config.RECORDED_ORDERS_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        parts = line.strip().split('|')
                        if len(parts) >= 4:
                            order_id, timestamp, exchange, status = parts[:4]
                            recorded_orders[order_id] = {
                                'time': float(timestamp),
                                'exchange': exchange,
                                'status': status
                            }
        except FileNotFoundError:
            pass
        
        for txid, order_info in closed_orders["closed"].items():
            if txid in recorded_orders:
                continue  # Already recorded this order
            
            # Only record filled orders
            if order_info["status"] != "closed":
                continue
            
            # Check if order was closed recently (within our time window)
            closetm = order_info.get("closetm", 0)
            if closetm and (time.time() - closetm) > 1800:  # Older than 30 minutes
                continue  # Skip old orders

            # Extract data from descr field (where pair and type are located)
            descr = order_info.get("descr", {})
            if not descr:
                continue

            pair = descr.get("pair")
            type = descr.get("type")  # buy or sell

            if not pair or not type:
                continue

            price = float(order_info["price"])
            volume = float(order_info["vol"])
            fee = float(order_info["fee"])
            
            # Record the trade data
            trade_data = {
                "type": type,
                "pair": pair,
                "price": price,
                "volume": volume,
                "fees": fee,
                "order_id": txid,
                "timestamp": closetm,
                "actual_profit": None  # Will be calculated when we have both buy and sell
            }
            
            # For now, just record the trade
            record_trade(trade_data)
            
            # Mark this order as recorded with additional info
            closetm = order_info.get("closetm", time.time())
            recorded_orders[txid] = {
                'time': closetm,
                'exchange': 'kraken',  # legacy.py is Kraken-specific
                'status': 'closed'
            }
            
            closed_time = time.strftime("%H:%M:%S", time.localtime(closetm)) if closetm else "unknown"
            print(f"[DEBUG] Recorded completed trade: {type} {volume} {pair} @ {price} (closed: {closed_time})")
        
        # Save updated recorded orders list
        with open(config.RECORDED_ORDERS_FILE, "w") as f:
            for order_id, order_info in recorded_orders.items():
                f.write(f"{order_id}|{order_info['time']}|{order_info['exchange']}|{order_info['status']}\n")
                
    except KeyError as e:
        logger.error(f"Missing expected key in closed orders response: {e}")
        logger.debug(f"Closed orders response structure: {closed_orders}")
    except Exception as e:
        logger.error(f"Error checking completed trades: {e}")

def place_sell_order_kraken(pair, volume, buy_price, price_decimals, estimated_fees):
    """Place a sell order with price-adjusted profit target considering fees"""

    # Get price-based profit margin
    profit_margin = get_profit_margin(buy_price)
    price_category = get_price_range_category(buy_price)
    
    # Calculate minimum profit needed to cover fees
    # Buy fee + Sell fee = total fees
    total_fees = estimated_fees * 2  # Assuming same fee for buy and sell
    
    # Calculate minimum profitable sell price using price-adjusted profit margin
    # sell_price = buy_price * (1 + total_fees + profit_margin)
    min_sell_price = buy_price * (1 + total_fees + profit_margin)
    
    # Round to appropriate decimal places for prices
    min_sell_price = round(min_sell_price, price_decimals)
    
    print(f"[DEBUG] Placing sell order for {pair} (category: {price_category}):")
    print(f"  Buy price: {buy_price}")
    print(f"  Total fees: {total_fees:.4f} ({total_fees*100:.2f}%)")
    print(f"  Profit margin: {profit_margin:.4f} ({profit_margin*100:.2f}%)")
    print(f"  Minimum sell price: {min_sell_price}")
    print(f"  Volume: {volume}")

    # Validate volume is not too small
    if volume <= 0:
        print(f"[DEBUG] Invalid volume for sell order: {volume}")
        return None

    # Validate price is reasonable
    if min_sell_price <= 0:
        print(f"[DEBUG] Invalid sell price: {min_sell_price}")
        return None

    sell_value = volume * min_sell_price
    buy_value = volume * buy_price
    expected_profit = sell_value - buy_value

    # Sanity check: sell value should be higher than buy value (accounting for fees)
    if sell_value < buy_value * 0.95:  # Allow for fees but not much more
        print(f"[DEBUG] WARNING: Sell value ${sell_value:.2f} is less than buy value ${buy_value:.2f} - possible pricing error")
        return None

    if expected_profit > buy_value * 2:  # Profit more than 200% of buy value seems suspicious
        print(f"[DEBUG] WARNING: Expected profit ${expected_profit:.2f} is >200% of buy value ${buy_value:.2f} - possible calculation error")
        return None

    print(f"[DEBUG] Placing sell order: {pair} {volume} units @ ${min_sell_price:.6f} = ${sell_value:.2f} (expected profit: ${expected_profit:.2f})")
    
    # Place the sell order
    order = add_order_kraken(
        pair=pair, 
        type='sell', 
        ordertype='limit', 
        price=str(min_sell_price), 
        volume=str(volume)
    )
    
    if order:
        print(f"[DEBUG] Successfully placed sell order: {order}")
        return order
    else:
        print(f"[DEBUG] Failed to place sell order for {pair} - check Kraken API response above")
        return None

def check_and_place_sell_orders():
    """Check for filled buy orders and place corresponding sell orders"""
    global total_open_order_value
    
    print("[DEBUG] Checking for filled buy orders...")
    
    # Add a delay to allow recent buy orders to settle and tokens to be credited
    # This helps prevent "insufficient funds" errors due to timing
    settlement_delay = 5  # 5 seconds
    print(f"[DEBUG] Waiting {settlement_delay} seconds for buy orders to settle...")
    time.sleep(settlement_delay)

    try:
        # Get closed orders from the last 30 minutes (more conservative window)
        # This ensures we're only looking at orders that have had time to settle
        since = int(time.time() - 1800)  # Last 30 minutes
        closed_orders = get_closed_orders_kraken(since=since)

        if not closed_orders:
            print("[DEBUG] No closed orders found")
            return

        filled_buy_orders = []

        for txid, order_info in closed_orders["closed"].items():
            try:
                # Check if order was closed recently (within our time window)
                closetm = order_info.get("closetm", 0)
                if closetm and (time.time() - closetm) > 1800:  # Older than 30 minutes
                        continue  # Skip old orders

                # Extract data from descr field (where pair and type are located)
                descr = order_info.get("descr", {})
                if not descr:
                    logger.debug(f"Skipping order {txid}: No descr field")
                    continue

                order_type = descr.get("type")
                pair = descr.get("pair")

                if not order_type or not pair:
                    logger.debug(f"Skipping order {txid}: Missing type or pair in descr")
                    continue

                # Check if this is a filled buy order
                if (order_type == "buy" and
                    order_info["status"] == "closed" and
                    float(order_info["vol_exec"]) > 0):  # Order was partially or fully filled

                    vol_exec = float(order_info["vol_exec"])
                    vol_orig = float(order_info.get("vol", 0))

                    # Only consider fully filled orders (or very close to fully filled)
                    fill_ratio = vol_exec / vol_orig if vol_orig > 0 else 0
                    if fill_ratio < 0.95:  # Less than 95% filled
                        logger.debug(f"Skipping order {txid}: Only {fill_ratio:.2%} filled")
                        continue

                    closed_time = time.strftime("%H:%M:%S", time.localtime(closetm)) if closetm else "unknown"
                    logger.debug(f"Found filled buy order {txid}: {pair} {vol_exec} @ {order_info['price']} (closed: {closed_time})")

                    filled_buy_orders.append({
                        "txid": txid,
                        "pair": pair,
                        "volume": vol_exec,
                        "price": float(order_info["price"]),
                        "cost": float(order_info["cost"]),
                        "fee": float(order_info["fee"])
                    })
            except KeyError as e:
                logger.error(f"Missing expected key in order info for {txid}: {e}")
                logger.debug(f"Order info structure: {order_info}")
                continue
            except ValueError as e:
                logger.error(f"Invalid value in order info for {txid}: {e}")
                continue

    # Handle any errors in the order processing loop
    except Exception as e:
        logger.error(f"Error processing closed orders: {e}")
        return

    except Exception as e:
        logger.error(f"Error in check_and_place_sell_orders: {e}")
        return
    
    if not filled_buy_orders:
        print("[DEBUG] No filled buy orders found")
        return
    
    print(f"[DEBUG] Found {len(filled_buy_orders)} filled buy orders")
    
    # Place sell orders for each filled buy order
    for buy_order in filled_buy_orders:
        pair = buy_order["pair"]
        volume = buy_order["volume"]
        buy_price = buy_order["price"]
        actual_fee = buy_order["fee"]
        
        print(f"[DEBUG] Processing filled buy order {buy_order['txid']} for {pair}: bought {volume} units @ ${buy_price:.6f} = ${volume * buy_price:.2f}")
        print(f"[DEBUG] Will attempt to sell up to {volume} units of {pair} when balance check passes")

        # First check if there's already an open sell order for this pair
        # If so, we don't need to place another sell order
        if has_open_sell_orders_for_pair(pair):
            print(f"[DEBUG] Already have open sell order for {pair}, skipping new sell order")
            continue

        # Check account balance before placing sell order
        # Try up to 3 times with delays in case of timing issues
        max_balance_checks = 3
        balance_ok = False

        for attempt in range(max_balance_checks):
            if attempt > 0:
                print(f"[DEBUG] Balance check attempt {attempt + 1}, waiting 3 seconds...")
                time.sleep(3)

            balance_response = get_account_balance_kraken()
            if balance_response:
                # Extract base currency from pair
                # For Kraken pairs, the base currency is what you receive when buying
                if '/' in pair:
                    # Format: BASE/QUOTE
                    base_currency = pair.split('/')[0]
                elif pair.endswith('USDT'):
                    # Format: BASEUSDT (e.g., BTCUSDT -> BTC)
                    base_currency = pair[:-4]
                elif pair.endswith(('USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD')):
                    # Format: BASEQUOTE (e.g., BTCUSD -> BTC, ETHGBP -> ETH)
                    base_currency = pair[:-3]
                elif pair.endswith(('BTC', 'ETH', 'ADA', 'DOT', 'SOL')):
                    # Crypto as quote (e.g., ADAETH -> ADA)
                    base_currency = pair[:-3]
                else:
                    # Fallback: assume first part before common separators
                    # This is a safety net for unusual pairs
                    base_currency = pair.split('_')[0] if '_' in pair else pair
                    logger.warning(f"Unknown pair format: {pair}, using {base_currency} as base currency")

                print(f"[DEBUG] Extracted base currency '{base_currency}' from pair '{pair}'")
            available_balance = float(balance_response.get(base_currency, 0))
            print(f"[DEBUG] Account balance for {base_currency}: {available_balance} (attempt {attempt + 1})")
            print(f"[DEBUG] Order volume to sell: {volume}")

            # Basic sanity check: if balance is zero, we definitely can't sell
            if available_balance <= 0:
                if attempt == max_balance_checks - 1:
                    print(f"[DEBUG] Zero balance for {base_currency} after {max_balance_checks} attempts - order may not have settled yet.")
                    print(f"[DEBUG] Skipping sell order for {pair} buy order {buy_order['txid']}")
                continue

            # CRITICAL FIX: Never try to sell more than we actually have
            # If the order volume exceeds available balance, adjust the sell volume
            actual_sell_volume = min(volume, available_balance * 0.99)  # Leave 1% buffer

            if actual_sell_volume < volume:
                print(f"[DEBUG] WARNING: Order volume {volume} exceeds available balance {available_balance}")
                print(f"[DEBUG] Adjusting sell volume to {actual_sell_volume} (99% of available balance)")
                print(f"[DEBUG] This suggests partial fills, fees, or price discrepancies")

                # If adjusted volume is too small, skip entirely
                if actual_sell_volume < volume * 0.1:  # Less than 10% of expected
                    print(f"[DEBUG] Adjusted volume too small ({actual_sell_volume} < {volume * 0.1}) - skipping sell order")
                    continue
            else:
                actual_sell_volume = volume

            print(f"[DEBUG] Will sell volume: {actual_sell_volume} (available: {available_balance})")
            balance_ok = True

            # Store the adjusted volume for later use
            buy_order['_adjusted_volume'] = actual_sell_volume
            break
        else:
            print(f"[DEBUG] Could not check account balance (attempt {attempt + 1})")

        if not balance_ok:
            print(f"[DEBUG] Skipping sell order for {pair} - balance checks failed")
            continue

        # Use adjusted volume if it was set during balance checking
        sell_volume = buy_order.get('_adjusted_volume', volume)

        # Get pair info for decimal precision and minimum order size
        asset_pairs = get_tradable_asset_pairs_kraken()
        if asset_pairs and pair in asset_pairs:
            pair_info = asset_pairs[pair]
            lot_decimals = pair_info.get("lot_decimals", 8)
            price_decimals = pair_info.get("pair_decimals", 5)  # Default to 5 for prices
            ordermin = float(pair_info.get("ordermin", 0.0001))  # Minimum order size
        else:
            lot_decimals = 8  # Default fallback
            price_decimals = 5  # Default fallback
            ordermin = 0.0001  # Default minimum

        # Ensure sell volume meets minimum order requirements
        if sell_volume < ordermin:
            print(f"[DEBUG] Sell volume {sell_volume} below minimum {ordermin} for {pair} - skipping")
            continue

        print(f"[DEBUG] Sell volume {sell_volume} meets minimum requirement {ordermin} for {pair}")
        
        # Calculate actual fee rate for this trade
        actual_fee_rate = actual_fee / buy_order["cost"] if buy_order["cost"] > 0 else 0.0026
        
        # Place sell order with the correct precision
        sell_order = place_sell_order_kraken(
            pair=pair,
            volume=sell_volume,
            buy_price=buy_price,
            price_decimals=price_decimals,
            estimated_fees=actual_fee_rate
        )
        
        if sell_order:
            print(f"[DEBUG] Successfully placed sell order for {pair} buy order {buy_order['txid']}")
        else:
            print(f"[DEBUG] Failed to place sell order for {pair} buy order {buy_order['txid']}")

def calculate_optimal_sell_price(pair, buy_price, price_decimals, estimated_fees):
    """Calculate optimal sell price based on market conditions and fees"""
    
    # Get current market price
    ticker_info = get_ticker_information_kraken(pair)
    if not ticker_info or pair not in ticker_info:
        return None
    
    current_price = float(ticker_info[pair]["c"][0])
    
    # Calculate minimum profitable price
    total_fees = estimated_fees * 2  # Buy + sell fees
    min_profit_margin = 0.005  # 0.5% minimum profit
    min_sell_price = buy_price * (1 + total_fees + min_profit_margin)
    
    # If current price is already above minimum profitable price, use current price
    if current_price > min_sell_price:
        sell_price = current_price
    else:
        # Use minimum profitable price
        sell_price = min_sell_price
    
    # Round to appropriate decimal places for prices
    sell_price = round(sell_price, price_decimals)
    
    return sell_price

def has_open_sell_orders_for_pair(pair):
    """Check if there are already open SELL orders for a specific pair"""
    try:
        open_orders = get_open_orders_kraken()

        if not open_orders or "open" not in open_orders:
            return False

        for txid, order_info in open_orders["open"].items():
            descr = order_info.get("descr", {})
            order_type = descr.get("type")
            order_pair = descr.get("pair")

            # Check if this is a sell order for our pair
            if order_type == "sell" and order_pair == pair:
                return True

        return False
    except Exception as e:
        print(f"[DEBUG] Error checking open sell orders for {pair}: {e}")
        return False

def has_open_orders_for_pair(pair):
    """Check if there are already open orders for a specific pair"""
    try:
        print(f"[DEBUG] Checking for existing open orders for {pair}")
        open_orders = get_open_orders_kraken()
        
        if not open_orders:
            print(f"[DEBUG] No open orders response for {pair}")
            return False
        
        print(f"[DEBUG] Open orders response keys: {list(open_orders.keys())}")
        
        if "open" not in open_orders:
            print(f"[DEBUG] No 'open' key in response for {pair}")
            return False
        
        open_orders_list = open_orders["open"]
        print(f"[DEBUG] Found {len(open_orders_list)} total open orders")
        
        for txid, order_info in open_orders_list.items():
            # Check if pair is in the descr object
            descr = order_info.get("descr", {})
            order_pair = descr.get("pair", "NO_PAIR")
            print(f"[DEBUG] Checking order {txid}: {order_pair}")
            if order_pair == pair:
                print(f"[DEBUG] Found existing open order for {pair}: {txid}")
                return True
        
        print(f"[DEBUG] No existing open orders found for {pair}")
        return False
    except Exception as e:
        print(f"[DEBUG] Error checking open orders for {pair}: {e}")
        return False

def is_profitable_opportunity(pair, current_price, estimated_fees):
    """Check if a pair represents a profitable trading opportunity using ML when available"""
    try:
        # First, try ML-based prediction if ML is enabled and model is available
        if config.ML_ENABLED and ml_analyzer and ml_analyzer.is_trained:
            # Estimate volume for prediction (use a reasonable default)
            estimated_volume = 100.0  # This could be improved with better volume estimation

            prediction, confidence = trade_analyzer_ml.predict_trade_opportunity(
                pair=pair,
                price=current_price,
                volume=estimated_volume,
                fees=estimated_fees
            )

            if prediction is not None and confidence > 0.6:  # Require 60% confidence
                logger.info(f"ML Prediction for {pair}: {'BUY' if prediction else 'SKIP'} (confidence: {confidence:.2f})")
                return prediction

        # Fallback to traditional analysis if ML is disabled or not available/confident
        # First check 24h volume - must be over 500k
        ticker_info = get_ticker_information_kraken(pair)
        if not ticker_info or pair not in ticker_info:
            print(f"[DEBUG] No ticker info for {pair}")
            return False
        
        # Get 24h volume in quote currency (USDT)
        volume_24h = float(ticker_info[pair]["v"][1])  # 24h volume in quote currency
        print(f"[DEBUG] {pair} 24h volume: {volume_24h}")
        
        # Price-adjusted volume requirements
        price_category = get_price_range_category(current_price)
        if price_category == 'low':
            min_volume = 500000  # $500k for micro tokens
        elif price_category == 'medium':
            min_volume = 200000  # $200k for medium tokens
        else:  # high
            min_volume = 100000  # $100k for higher-priced tokens

        if volume_24h < min_volume:
            print(f"[DEBUG] {pair} volume too low: {volume_24h} < {min_volume} (category: {price_category})")
            return False
        
        # Get recent price movement
        trend = analyze_price_movement(pair)
        
        # Get order book to check liquidity
        order_book = get_order_book_kraken(pair, count=5)
        if not order_book or pair not in order_book:
            return False
        
        bids = order_book[pair]["bids"]
        asks = order_book[pair]["asks"]
        
        if not bids or not asks:
            return False
        
        # Calculate bid-ask spread
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        spread = (best_ask - best_bid) / best_bid
        
        # Price-adjusted spread requirements
        if price_category == 'low':
            max_spread = 0.08  # 8% for micro tokens (more volatile)
        elif price_category == 'medium':
            max_spread = 0.05  # 5% for medium tokens
        else:  # high
            max_spread = 0.03  # 3% for higher-priced tokens (more liquid)

        if spread > max_spread:
            print(f"[DEBUG] {pair} spread too wide: {spread:.4f} > {max_spread:.2f} (category: {price_category})")
            return False
        
        # Check if there's enough volume in the order book (price-adjusted)
        total_bid_volume = sum(float(bid[1]) for bid in bids[:3])  # Top 3 bids
        total_ask_volume = sum(float(ask[1]) for ask in asks[:3])  # Top 3 asks
        
        if price_category == 'low':
            min_volume_threshold = 50   # Lower threshold for micro tokens
        elif price_category == 'medium':
            min_volume_threshold = 25   # Medium threshold
        else:  # high
            min_volume_threshold = 10   # Higher-priced tokens need less volume

        if total_bid_volume < min_volume_threshold or total_ask_volume < min_volume_threshold:
            print(f"[DEBUG] {pair} order book volume too low: bid={total_bid_volume}, ask={total_ask_volume} < {min_volume_threshold} (category: {price_category})")
            return False
        
        # Check if price movement suggests opportunity
        if trend == "falling":
            # Good opportunity to buy if price is falling
            print(f"[DEBUG] {pair} profitable: falling trend, good spread")
            return True
        elif trend == "neutral" and spread < 0.02:
            # Good opportunity if spread is tight and trend is neutral
            print(f"[DEBUG] {pair} profitable: neutral trend, tight spread")
            return True
        elif trend == "rising":
            # Be more selective with rising prices
            if spread < 0.01:  # Only if spread is very tight
                print(f"[DEBUG] {pair} profitable: rising trend, very tight spread")
                return True
            else:
                print(f"[DEBUG] {pair} not profitable: rising trend, spread too wide")
                return False
        
        print(f"[DEBUG] {pair} not profitable: no suitable conditions met")
        return False
        
    except Exception as e:
        print(f"[DEBUG] Error checking profitability for {pair}: {e}")
        return False

def cleanup_old_records():
    """Clean up old recorded orders on startup to prevent processing stale data"""
    try:
        # Keep recorded orders from previous sessions to maintain history
        global total_open_order_value
        total_open_order_value = 0.0
        logger.info("Reset open order value tracking")

    except Exception as e:
        logger.warning(f"Could not cleanup old records: {e}")

def main():
    logger.info("Kraken Trading Bot Started.")

    # Clean up old records on startup
    cleanup_old_records()

    # Initialize ML system if enabled
    global ml_analyzer
    if config.ML_ENABLED:
        ml_analyzer = trade_analyzer_ml.initialize_ml_system()
        logger.info("Machine Learning system enabled")
    else:
        ml_analyzer = None
        logger.info("Machine Learning system disabled - using traditional analysis only")

    time_to_sleep = 60
    
    # Get account balance
    balance_response = get_account_balance_kraken()
    if balance_response:
        print("Account Balance:", balance_response)
        
        # Calculate total USDT balance
        total_usdt_balance = 0
        for currency, amount in balance_response.items():
            if currency == "USDT":
                total_usdt_balance = float(amount)
                break
        
        if total_usdt_balance <= 0:
            print("No USDT balance found. Cannot trade.")
            return
            
        print(f"Total USDT Balance: {total_usdt_balance}")
    else:
        print("Could not retrieve account balance.")
        return

    print("Starting trading loop...")
    
    while True:
        try:
            # First, check for and record any completed trades
            try:
                check_and_record_completed_trades()
            except Exception as e:
                print(f"[DEBUG] Error checking completed trades: {e}")
            
            # Then, manage existing open orders
            try:
                orders_canceled = manage_open_orders()
            except Exception as e:
                print(f"[DEBUG] Error in manage_open_orders: {e}")
                orders_canceled = False
            
            # Check for filled buy orders and place sell orders
            try:
                check_and_place_sell_orders()
            except Exception as e:
                print(f"[DEBUG] Error in check_and_place_sell_orders: {e}")
            
            # If orders were canceled, wait a bit before placing new ones
            if orders_canceled:
                print(f"[DEBUG] Waiting {time_to_sleep / 2} seconds after canceling orders...")
                time.sleep(time_to_sleep / 2)
            
            print("Getting sub-1-cent tokens...")
            try:
                sub_cent_tokens = get_sub_cent_tokens()
                print(f"Sub-1-cent tokens found: {len(sub_cent_tokens)}")
            except Exception as e:
                print(f"[DEBUG] Error getting sub-cent tokens: {e}")
                sub_cent_tokens = {}
            
            if not sub_cent_tokens:
                print(f"No sub-cent tokens found. Waiting {time_to_sleep} seconds...")
                time.sleep(time_to_sleep)
                continue

            # Place new orders for available tokens
            for pair, info in sub_cent_tokens.items():
                try:
                    print(f"[DEBUG] Processing pair: {pair}")
                    ticker_info = get_ticker_information_kraken(pair)
                    if ticker_info and pair in ticker_info:
                        current_price = float(ticker_info[pair]["c"][0])

                        # Double-check that the token still meets our price criteria
                        # (price might have changed since initial scan)
                        if current_price > config.MAX_TOKEN_PRICE:
                            print(f"[DEBUG] Skipping {pair}: Price {current_price} now exceeds limit {config.MAX_TOKEN_PRICE}")
                            continue

                        # Placeholder for fee calculation (this needs to be dynamic based on volume and maker/taker)
                        estimated_fees = 0.0026 # Example: 0.26% taker fee
                        
                        # Check for existing open orders
                        has_existing = has_open_orders_for_pair(pair)
                        print(f"[DEBUG] {pair} has existing orders: {has_existing}")
                        
                        # Check if it's a profitable opportunity
                        is_profitable = is_profitable_opportunity(pair, current_price, estimated_fees)
                        print(f"[DEBUG] {pair} is profitable opportunity: {is_profitable}")
                        
                        if not has_existing and is_profitable:
                            print(f"[DEBUG] Placing trade for {pair} at price {current_price}")
                            simple_trading_strategy(pair, current_price, estimated_fees, total_usdt_balance, info["ordermin"], info["pair_decimals"])
                        else:
                            print(f"Skipping {pair}: Already has open orders ({has_existing}) or not a profitable opportunity ({is_profitable})")
                    else:
                        print(f"Could not get ticker information for {pair}.")
                except Exception as e:
                    print(f"Error processing {pair}: {e}")
            
            # Wait before next iteration
            print(f"[DEBUG] Waiting {time_to_sleep} seconds before next trading cycle...")
            time.sleep(time_to_sleep)
            
        except KeyboardInterrupt:
            print("\nBot stopped by user.")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            print(f"Waiting {time_to_sleep} seconds before retrying...")
            time.sleep(time_to_sleep)

if __name__ == "__main__":
    # Ensure hmac is imported for signature generation
    import hmac
    main()




