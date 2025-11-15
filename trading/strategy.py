"""Trading strategy functions"""

import config
from utils.helpers import get_risk_multiplier, get_profit_margin, get_price_range_category
from trading.position_tracker import add_open_position
from utils.session import update_session_metrics
from display import ColorPrint


def calculate_dynamic_buy_price(pair, current_price, lot_decimals, exchange):
    """Calculate aggressive buy price for quick fills and fast trading"""
    # Get order book for best bid price
    order_book = exchange.get_order_book(pair, count=10)
    exchange_pair = exchange.get_pair_format(pair)
    
    if order_book:
        if exchange_pair in order_book:
            book_data = order_book[exchange_pair]
        else:
            book_data = list(order_book.values())[0] if order_book else None
        
        if book_data:
            bids = book_data.get("bids", [])
            if bids:
                best_bid = float(bids[0][0])
                # For aggressive quick fills: place order just above the best bid
                # This ensures immediate fill in most cases
                buy_price = best_bid * 1.0001  # 0.01% above best bid
                print(
                    f"[DEBUG] Aggressive buy: best_bid={best_bid:.6f}, buy_price={buy_price:.6f}")
            else:
                # Fallback: very close to current price
                buy_price = current_price * 1.0002  # 0.02% above current
                print(f"[DEBUG] No bids found, using current price: {buy_price:.6f}")
        else:
            # Ultimate fallback: very close to current price for guaranteed fills
            buy_price = current_price * 1.0001  # 0.01% above current
            print(f"[DEBUG] No order book data, using current price: {buy_price:.6f}")
    else:
        # Ultimate fallback: very close to current price for guaranteed fills
        buy_price = current_price * 1.0001  # 0.01% above current
        print(f"[DEBUG] No order book, using current price: {buy_price:.6f}")

    # Ensure we don't set price too high (sanity check)
    max_reasonable_price = current_price * 1.01  # Max 1% above current
    buy_price = min(buy_price, max_reasonable_price)
    
    # Round to appropriate decimal places
    buy_price = round(buy_price, lot_decimals)
    
    print(
        f"[DEBUG] Final aggressive buy price for {pair}: {buy_price:.6f} (current: {current_price:.6f})")
    
    return buy_price


def simple_trading_strategy(
        pair,
        current_price,
        fees,
        account_balance,
        ordermin,
        pair_decimals,
        exchange,
        exchange_open_order_values,
        session_metrics=None,
        open_positions=None):
    """Simple trading strategy with price-adjusted risk management"""
    exchange_name = exchange.name if hasattr(exchange, 'name') else 'kraken'
    total_open_order_value = exchange_open_order_values.get(exchange_name, 0.0)

    print(
        f"Applying price-adjusted strategy for {pair} at price {current_price} on {exchange_name}")

    # Get price-based risk adjustments
    risk_multiplier = get_risk_multiplier(current_price)
    price_category = get_price_range_category(current_price)

    # Get pair information for decimal precision from exchange
    asset_pairs = exchange.get_tradable_pairs()
    if asset_pairs:
        # Normalize pair for exchange lookup
        exchange_pair = exchange.get_pair_format(pair)
        if exchange_pair in asset_pairs:
            pair_info = asset_pairs[exchange_pair]
            lot_decimals = pair_info.get("lot_decimals", 8)
            price_decimals = pair_info.get(
                "pair_decimals",
                pair_decimals)  # Use passed value or API value
        else:
            lot_decimals = 8
            price_decimals = pair_decimals
    else:
        lot_decimals = 8
        price_decimals = pair_decimals

    print(
        f"[DEBUG] Using {price_decimals} price decimals and {lot_decimals} lot decimals for {pair}")

    print(
        f"[DEBUG] Price category: {price_category}, Risk multiplier: {risk_multiplier}")

    # Calculate maximum trading amount with price-based adjustments
    base_max_trade_amount = account_balance * config.MAX_ACCOUNT_USAGE_PERCENT
    max_total_trade_amount = base_max_trade_amount * risk_multiplier
    max_trade_as_percentage = (max_total_trade_amount / account_balance) * 100

    print(f"[DEBUG] Account balance ({exchange_name}): {account_balance}")
    print(
        f"[DEBUG] Base max trade amount ({config.MAX_ACCOUNT_USAGE_PERCENT * 100}%): {base_max_trade_amount}")
    print(
        f"[DEBUG] Adjusted max trade amount ({max_trade_as_percentage:.1f}%): {max_total_trade_amount}")
    print(f"[DEBUG] Current total open order value ({exchange_name}): {total_open_order_value}")

    # Check if we can place another order without exceeding limit
    remaining_budget = max_total_trade_amount - total_open_order_value
    if remaining_budget <= 0:
        print(
            f"[DEBUG] Cannot place order for {pair}: Already at {max_trade_as_percentage:.1f}% limit")
        return
    
    # Calculate how much of the token we can buy with remaining budget
    fee_multiplier = 1 + fees
    max_volume = remaining_budget / (current_price * fee_multiplier)
    
    # Apply price-based trade size limit
    trade_size_limit = config.MAX_TRADE_SIZE_PERCENT * risk_multiplier
    max_volume = max_volume * trade_size_limit

    print(
        f"[DEBUG] Trade size limit: {trade_size_limit:.2f} ({trade_size_limit * 100:.1f}% of remaining budget)")
    
    # Ensure ordermin is a float
    ordermin = float(ordermin)

    print(
        f"[DEBUG] Order minimum: {ordermin}, calculated max volume: {max_volume}")

    # Ensure we trade at least the minimum volume, rounded to lot decimals
    volume_to_trade = max(round(max_volume, lot_decimals), ordermin)
    
    if volume_to_trade <= 0:
        print(f"[DEBUG] Insufficient remaining budget to trade {pair}")
        return
    
    # Additional check: ensure the volume meets ordermin after rounding
    if volume_to_trade < ordermin:
        print(
            f"[DEBUG] Calculated volume {volume_to_trade} below ordermin {ordermin} for {pair}")
        return

    print(
        f"[DEBUG] Final volume to trade: {volume_to_trade} (ordermin: {ordermin})")
    
    # Use dynamic pricing instead of fixed 99% of current price
    price_decimals_int = int(price_decimals)
    buy_price = calculate_dynamic_buy_price(
        pair, current_price, price_decimals_int, exchange)
    
    # Calculate order value (price * volume) - this is what gets locked in the order
    # Note: This matches how manage_open_orders calculates order value
    order_value = buy_price * volume_to_trade
    
    # Calculate actual cost including fees (for display purposes)
    order_cost = volume_to_trade * buy_price * fee_multiplier
    
    # Double-check we're not exceeding the limit using order value (not cost with fees)
    if total_open_order_value + order_value > max_total_trade_amount:
        print(
            f"[DEBUG] Order would exceed {max_trade_as_percentage}% limit. Skipping {pair}")
        return
    
    print(
        f"[DEBUG] Attempting to buy {volume_to_trade} {pair} at {buy_price} on {exchange_name}")
    
    try:
        print(
            f"Attempting to place buy order for {volume_to_trade} {pair} at {buy_price} on {exchange_name}")
        
        # Use exchange-specific order placement with optional margin support
        exchange_pair = exchange.get_pair_format(pair)
        leverage = None
        if hasattr(config, 'MARGIN_TRADING_ENABLED') and config.MARGIN_TRADING_ENABLED and exchange_name == 'kraken':
            leverage = config.DEFAULT_LEVERAGE
            print(f"[DEBUG] Using {leverage}x leverage for margin trading")

            # Check margin availability for safety
            try:
                trade_balance = exchange.get_trade_balance()
                if trade_balance:
                    margin_level = float(trade_balance.get('m', '0'))  # Margin level
                    if margin_level < 1.1:  # Require at least 10% margin buffer
                        print(f"[WARNING] Insufficient margin level ({margin_level:.2f}) - skipping margin order")
                        leverage = None
            except Exception as e:
                print(f"[WARNING] Could not check margin level: {e} - proceeding without margin")
                leverage = None

        order = exchange.place_buy_order(exchange_pair, volume_to_trade, buy_price, leverage)
        
        if order:
            leverage_text = f" ({leverage}x margin)" if leverage else ""
            ColorPrint.trade(
                f"BUY {volume_to_trade} {pair} @ ${buy_price:.6f} on {exchange_name.upper()}{leverage_text} = ${order_value:.2f} (cost with fees: ${order_cost:.2f})",
                trade_type="buy"
            )
            # Update exchange-specific total open order value using order_value (not order_cost)
            # This matches how manage_open_orders calculates it
            exchange_open_order_values[exchange_name] = total_open_order_value + order_value
            ColorPrint.debug(
                f"[DEBUG] Updated total open order value ({exchange_name}): ${exchange_open_order_values[exchange_name]:.2f}")

            # Record the open order
            # Extract order ID from the response (Kraken returns txid in various formats)
            order_id = None
            if isinstance(order, dict):
                if 'txid' in order:
                    txid_data = order['txid']
                    if isinstance(txid_data, list) and txid_data:
                        order_id = txid_data[0]
                    elif isinstance(txid_data, str):
                        order_id = txid_data

            if order_id:
                try:
                    from .order_manager import record_open_order
                    record_open_order(order_id, exchange_name, 'buy')
                    ColorPrint.debug(f"[DEBUG] Recorded open buy order {order_id}")
                except Exception as e:
                    ColorPrint.debug(f"[DEBUG] Failed to record open order {order_id}: {e}")

            # Update session metrics
            if session_metrics is not None:
                update_session_metrics(session_metrics, order_placed=True)

            # Add to open positions tracking
            if open_positions is not None:
                order_id = order.get('txid', [''])[0] if isinstance(order.get('txid'), list) else order.get('txid', '')
                add_open_position(open_positions, pair, order_id, 'buy', volume_to_trade, buy_price, exchange=exchange_name)

            # Note: Trade will be recorded when order is actually filled
        else:
            print(f"Failed to place buy order for {pair} on {exchange_name}.")
    except Exception as e:
        print(f"Error placing buy order on {exchange_name}: {e}")


def calculate_optimal_sell_price(
        pair,
        buy_price,
        price_decimals,
        estimated_fees,
        exchange):
    """Calculate optimal sell price based on market conditions and fees"""
    # Get current market price
    ticker_info = exchange.get_ticker(pair)
    if not ticker_info:
        return None
    
    exchange_pair = exchange.get_pair_format(pair)
    if exchange_pair in ticker_info:
        price_data = ticker_info[exchange_pair]
    else:
        price_data = list(ticker_info.values())[0] if ticker_info else None
    
    if not price_data:
        return None

    current_price = float(price_data.get('c', [0])[0] if isinstance(price_data.get('c'), list) else price_data.get('c', 0))
    
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

