"""Order management functions"""

import time
import logging
import config
from utils.helpers import get_profit_margin
from utils.session import record_trade, update_session_metrics
from trading.position_tracker import update_position_status, add_open_position
from display import ColorPrint

logger = logging.getLogger(__name__)


def manage_open_orders(exchange, exchange_open_order_values):
    """Manage existing open orders - cancel old ones and adjust prices"""
    exchange_name = exchange.name if hasattr(exchange, 'name') else 'kraken'
    total_open_order_value = exchange_open_order_values.get(exchange_name, 0.0)
    
    print(f"[DEBUG] Managing open orders on {exchange_name}...")
    open_orders_response = exchange.get_open_orders()
    
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
                    print(
                        f"[DEBUG] Skipping order {txid}: Missing required fields")
                    continue

                # Get price from descr section (not top-level price which can be 0)
                price_raw = order_info.get("descr", {}).get("price", 0)
                try:
                    price_float = float(price_raw)
                    if price_float <= 0:
                        print(
                            f"[DEBUG] Order {txid} has invalid price {price_raw}. Full order_info: {order_info}")
                        continue
                except (ValueError, TypeError):
                    print(
                        f"[DEBUG] Order {txid} has non-numeric price {price_raw}. Full order_info: {order_info}")
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
                    print(
                        f"[DEBUG] Skipping order {txid}: Invalid volume {volume}")
                    continue

                print(
                    f"[DEBUG] Processing order {txid}: {order_type} {pair} {volume} @ {price}")
                
                # Calculate order value
                order_value = price * volume
                total_open_order_value += order_value
                
                # Cancel orders older than 30 minutes (1800 seconds)
                if time_open > 1800:
                    print(
                        f"[DEBUG] Order {txid} is {time_open / 60:.1f} minutes old, canceling...")
                    orders_to_cancel.append(txid)
                    continue
                
                # Adjust price for orders older than 10 minutes
                if time_open > 600:
                    print(
                        f"[DEBUG] Order {txid} is {time_open / 60:.1f} minutes old, checking for price adjustment...")
                    
                    # Get current market price
                    ticker_info = exchange.get_ticker(pair)
                    exchange_pair = exchange.get_pair_format(pair)
                    if ticker_info:
                        if exchange_pair in ticker_info:
                            price_data = ticker_info[exchange_pair]
                        else:
                            price_data = list(ticker_info.values())[0] if ticker_info else None
                        
                        if price_data:
                            current_price = float(price_data.get('c', [0])[0] if isinstance(price_data.get('c'), list) else price_data.get('c', 0))
                            
                            # If order is buy and current price is much lower, cancel and re-place
                            if order_type == "buy" and current_price < price * 0.95:
                                print(
                                    f"[DEBUG] Current price {current_price} is much lower than order price {price}, canceling...")
                                orders_to_cancel.append(txid)
                                continue
                            
                            # If order is buy and current price is higher, adjust order price
                            elif order_type == "buy" and current_price > price * 1.02:
                                print(
                                    f"[DEBUG] Current price {current_price} is higher than order price {price}, adjusting...")
                                orders_to_cancel.append(txid)
                                # Re-place order at better price (will be done in main loop)
                                continue
                            
            except (KeyError, ValueError, TypeError) as e:
                print(f"[DEBUG] Error processing order {txid}: {e}")
                continue
        
        # Update exchange-specific order value BEFORE canceling orders
        # This ensures the value reflects actual open orders
        exchange_open_order_values[exchange_name] = total_open_order_value
        
        # Cancel orders that need to be canceled
        # After canceling, we need to subtract their value from the total
        canceled_value = 0.0
        for txid in orders_to_cancel:
            try:
                # Get order value before canceling
                if txid in open_orders_response["open"]:
                    order_info = open_orders_response["open"][txid]
                    price = float(order_info.get("descr", {}).get("price", 0))
                    volume = float(order_info.get("vol", 0))
                    canceled_value += price * volume
                
                cancel_result = exchange.cancel_order(txid)
                if cancel_result:
                    print(f"[DEBUG] Successfully canceled order {txid}")
                else:
                    print(f"[DEBUG] Failed to cancel order {txid}")
            except Exception as e:
                print(f"[DEBUG] Error canceling order {txid}: {e}")
        
        # Subtract canceled orders value from total
        if canceled_value > 0:
            exchange_open_order_values[exchange_name] = max(0.0, exchange_open_order_values[exchange_name] - canceled_value)
            print(f"[DEBUG] Subtracted ${canceled_value:.2f} from total for canceled orders")
        
        print(
            f"[DEBUG] Updated total open order value ({exchange_name}): ${exchange_open_order_values[exchange_name]:.2f}")
        return len(orders_to_cancel) > 0  # Return True if orders were canceled
        
    except Exception as e:
        print(f"[DEBUG] Error in manage_open_orders: {e}")
        return False


def record_open_order(order_id, exchange_name, order_type='buy'):
    """Record a newly placed open order"""
    try:
        recorded_orders = {}

        # Load existing records
        try:
            with open(config.RECORDED_ORDERS_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        parts = line.strip().split('|')
                        if len(parts) >= 4:
                            order_id_existing, timestamp, exchange, status = parts[:4]
                            recorded_orders[order_id_existing] = {
                                'time': float(timestamp),
                                'exchange': exchange,
                                'status': status
                            }
        except FileNotFoundError:
            pass

        # Add the new open order
        recorded_orders[order_id] = {
            'time': time.time(),
            'exchange': exchange_name,
            'status': 'open'
        }

        # Save updated records
        with open(config.RECORDED_ORDERS_FILE, "w") as f:
            for order_id_entry, order_info in recorded_orders.items():
                f.write(f"{order_id_entry}|{order_info['time']}|{order_info['exchange']}|{order_info['status']}\n")

        logger.debug(f"Recorded open order {order_id} on {exchange_name}")

    except Exception as e:
        logger.error(f"Error recording open order {order_id}: {e}")


def check_and_record_completed_trades(session_metrics=None, open_positions=None, exchange=None, exchange_open_order_values=None):
    """Check for recently completed trades and record them for training"""
    if not exchange:
        from exchanges.kraken import ExchangeKraken
        from bot import API_KEY, API_SECRET
        exchange = ExchangeKraken(API_KEY, API_SECRET)
    
    exchange_name = exchange.name if hasattr(exchange, 'name') else 'kraken'
    
    try:
        # Only check orders from the last 30 minutes to focus on recent fills
        since = int(time.time() - 1800)  # Last 30 minutes
        closed_orders = exchange.get_closed_orders(since=since)

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
        
        # Track filled buy orders to subtract from total order value
        filled_buy_order_value = 0.0
        
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
            
            # If this is a filled buy order, subtract its value from total order value
            if type == "buy" and exchange_open_order_values is not None:
                order_value = price * volume
                filled_buy_order_value += order_value
            
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
            record_trade(trade_data, session_metrics, exchange_name=exchange_name)

            # Update position status if tracking positions
            if open_positions is not None:
                update_position_status(open_positions, txid, 'filled', exchange=exchange_name)
            
            # Mark this order as recorded with additional info
            closetm = order_info.get("closetm", time.time())
            recorded_orders[txid] = {
                'time': closetm,
                'exchange': exchange_name,
                'status': 'closed'
            }
        
        # Subtract filled buy orders from total order value
        if filled_buy_order_value > 0 and exchange_open_order_values is not None:
            current_total = exchange_open_order_values.get(exchange_name, 0.0)
            exchange_open_order_values[exchange_name] = max(0.0, current_total - filled_buy_order_value)
            logger.debug(f"Subtracted ${filled_buy_order_value:.2f} from total order value for filled buy orders on {exchange_name}")
        
        # Save updated recorded orders list
        with open(config.RECORDED_ORDERS_FILE, "w") as f:
            for order_id, order_info in recorded_orders.items():
                f.write(f"{order_id}|{order_info['time']}|{order_info['exchange']}|{order_info['status']}\n")
                
    except KeyError as e:
        logger.error(f"Missing expected key in closed orders response: {e}")
        logger.debug(f"Closed orders response structure: {closed_orders}")
    except Exception as e:
        logger.error(f"Error checking completed trades: {e}")


def check_and_place_sell_orders(open_positions=None, exchange=None, exchange_open_order_values=None):
    """Check for filled buy orders and place corresponding sell orders"""
    if not exchange:
        from exchanges.kraken import ExchangeKraken
        exchange = ExchangeKraken(config.KRAKEN_API_KEY, config.KRAKEN_API_SECRET)
    
    exchange_name = exchange.name if hasattr(exchange, 'name') else 'kraken'

    print(f"[DEBUG] Checking for filled buy orders on {exchange_name}...")

    # Add a delay to allow recent buy orders to settle and tokens to be credited
    settlement_delay = 5  # 5 seconds
    print(f"[DEBUG] Waiting {settlement_delay} seconds for buy orders to settle...")
    time.sleep(settlement_delay)

    try:
        # Get closed orders from the last 30 minutes
        since = int(time.time() - 1800)  # Last 30 minutes
        closed_orders = exchange.get_closed_orders(since=since)
        
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

                # Extract data from descr field
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
                if (order_type == "buy" and order_info["status"] == "closed" and float(order_info["vol_exec"]) > 0):
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
            except Exception as e:
                logger.error(f"Error processing order {txid}: {e}")
                continue

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

        # Check if we already have sell orders for this pair to prevent duplicates
        if has_open_sell_orders_for_pair(pair, exchange):
            print(f"[DEBUG] Already have open sell order for {pair} from previous buy order {buy_order['txid']}, skipping")
            continue

        # Check account balance before placing sell order
        max_balance_checks = 3
        balance_ok = False

        for attempt in range(max_balance_checks):
            if attempt > 0:
                # Exponential backoff for rate limits
                wait_time = (2 ** (attempt - 1)) * 3  # 3, 6, 12 seconds
                print(f"[DEBUG] Balance check attempt {attempt + 1}, waiting {wait_time} seconds...")
                time.sleep(wait_time)

            # Try to get cached balance first, then fallback to fresh call if needed
            balance_response = None
            try:
                # Import the cached balance function from bot.py
                from bot import get_cached_balance
                balance_response = get_cached_balance(exchange, exchange_name)
            except ImportError:
                # Fallback to direct call if import fails
                balance_response = exchange.get_balance()
            if balance_response:
                # Get the correct currency code from exchange
                base_currency = exchange.get_currency_code(pair)
                logger.debug(f"Extracted base currency '{base_currency}' from pair '{pair}'")
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
            actual_sell_volume = min(volume, available_balance * 0.99)  # Leave 1% buffer

            if actual_sell_volume < volume:
                print(f"[DEBUG] WARNING: Order volume {volume} exceeds available balance {available_balance}")
                print(f"[DEBUG] Adjusting sell volume to {actual_sell_volume} (99% of available balance)")
                print("[DEBUG] This suggests partial fills, fees, or price discrepancies")

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
        exchange_pair = exchange.get_pair_format(pair)
        asset_pairs = exchange.get_tradable_pairs()
        if asset_pairs and exchange_pair in asset_pairs:
            pair_info = asset_pairs[exchange_pair]
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

        # Place sell order with the correct precision using exchange method
        profit_margin = get_profit_margin(buy_price)
        total_fees = actual_fee_rate * 2  # Buy + sell fees
        min_sell_price = buy_price * (1 + total_fees + profit_margin)
        min_sell_price = round(min_sell_price, price_decimals)
        
        exchange_pair = exchange.get_pair_format(pair)

        # Check if margin trading is enabled and this is a Kraken order
        leverage = None
        if hasattr(config, 'MARGIN_TRADING_ENABLED') and config.MARGIN_TRADING_ENABLED and exchange_name == 'kraken':
            leverage = config.DEFAULT_LEVERAGE
            print(f"[DEBUG] Using {leverage}x leverage for margin sell order")

        sell_order = exchange.place_sell_order(exchange_pair, sell_volume, min_sell_price, leverage)
        
        if sell_order:
            expected_profit = (min_sell_price - buy_price) * sell_volume
            leverage_text = f" ({leverage}x margin)" if leverage else ""
            ColorPrint.trade(
                f"SELL {sell_volume} {pair} @ ${min_sell_price:.6f} on {exchange_name.upper()}{leverage_text} (Expected profit: ${expected_profit:.4f})",
                trade_type="sell"
            )

            # Add to open positions tracking
            if open_positions is not None:
                # Extract order ID from response
                order_id = sell_order.get('txid', [''])[0] if isinstance(sell_order.get('txid'), list) else sell_order.get('txid', '')
                add_open_position(open_positions, pair, order_id, 'sell', sell_volume, min_sell_price, exchange=exchange_name)
        else:
            print(f"[DEBUG] Failed to place sell order for {pair} buy order {buy_order['txid']}")


def has_open_sell_orders_for_pair(pair, exchange):
    """Check if there are already open SELL orders for a specific pair"""
    try:
        open_orders = exchange.get_open_orders()

        if not open_orders or "open" not in open_orders:
            return False

        exchange_pair = exchange.get_pair_format(pair)
        for txid, order_info in open_orders["open"].items():
            descr = order_info.get("descr", {})
            order_type = descr.get("type")
            order_pair = descr.get("pair")

            # Normalize pair for comparison
            if order_pair:
                order_pair_normalized = exchange.normalize_pair(order_pair)
                if (order_pair_normalized == exchange_pair or order_pair == exchange_pair or order_pair == pair) and order_type == "sell":
                    return True

        return False
    except Exception as e:
        print(f"[DEBUG] Error checking open sell orders for {pair}: {e}")
        return False


def has_open_orders_for_pair(pair, exchange):
    """Check if there are already open orders for a specific pair"""
    try:
        print(f"[DEBUG] Checking for existing open orders for {pair}")
        open_orders = exchange.get_open_orders()
        
        if not open_orders:
            print(f"[DEBUG] No open orders response for {pair}")
            return False
        
        print(f"[DEBUG] Open orders response keys: {list(open_orders.keys())}")
        
        if "open" not in open_orders:
            print(f"[DEBUG] No 'open' key in response for {pair}")
            return False
        
        open_orders_list = open_orders["open"]
        print(f"[DEBUG] Found {len(open_orders_list)} total open orders")
        
        exchange_pair = exchange.get_pair_format(pair)
        for txid, order_info in open_orders_list.items():
            # Check if pair is in the descr object
            descr = order_info.get("descr", {})
            order_pair = descr.get("pair", "NO_PAIR")
            print(f"[DEBUG] Checking order {txid}: {order_pair}")
            # Normalize pair for comparison
            if order_pair:
                order_pair_normalized = exchange.normalize_pair(order_pair)
                if order_pair_normalized == exchange_pair or order_pair == exchange_pair or order_pair == pair:
                    print(f"[DEBUG] Found existing open order for {pair}: {txid}")
                    return True
        
        print(f"[DEBUG] No existing open orders found for {pair}")
        return False
    except Exception as e:
        print(f"[DEBUG] Error checking open orders for {pair}: {e}")
        return False

