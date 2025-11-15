"""Profit calculation functions"""

import time
import logging

logger = logging.getLogger(__name__)


def calculate_trade_profit(sell_trade, exchange=None):
    """
    Calculate profit/loss for a sell trade by matching with corresponding buy trades
    """
    if not exchange:
        from exchanges.kraken import ExchangeKraken
        import config
        exchange = ExchangeKraken(config.KRAKEN_API_KEY, config.KRAKEN_API_SECRET)
    
    try:
        # Get closed orders from the last 30 minutes
        since = int(time.time() - 1800)  # Last 30 minutes
        closed_orders = exchange.get_closed_orders(since=since)

        if not closed_orders:
            print("[DEBUG] No closed orders found")
            return None

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

                # Check if this is a filled buy order for the same pair
                if (order_type == "buy" and 
                    order_info["status"] == "closed" and 
                    float(order_info["vol_exec"]) > 0 and
                    pair == sell_trade.get("pair")):

                    vol_exec = float(order_info["vol_exec"])
                    vol_orig = float(order_info.get("vol", 0))

                    # Only consider fully filled orders (or very close to fully filled)
                    fill_ratio = vol_exec / vol_orig if vol_orig > 0 else 0
                    if fill_ratio < 0.95:  # Less than 95% filled
                        logger.debug(f"Skipping order {txid}: Only {fill_ratio:.2%} filled")
                        continue

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

        # Match sell trade with buy trades using FIFO
        sell_volume = sell_trade.get("volume", 0)
        sell_price = sell_trade.get("price", 0)
        sell_fee = sell_trade.get("fees", 0)
        
        if not filled_buy_orders or sell_volume <= 0:
            return None
        
        # Sort buy orders by time (FIFO)
        filled_buy_orders.sort(key=lambda x: x.get("txid", ""))
        
        # Match volumes
        remaining_sell_volume = sell_volume
        total_cost = 0.0
        total_buy_fees = 0.0
        
        for buy_order in filled_buy_orders:
            if remaining_sell_volume <= 0:
                break
            
            buy_volume = buy_order["volume"]
            buy_price = buy_order["price"]
            buy_fee = buy_order["fee"]
            
            matched_volume = min(remaining_sell_volume, buy_volume)
            matched_cost = matched_volume * buy_price
            matched_fee = buy_fee * (matched_volume / buy_volume) if buy_volume > 0 else 0
            
            total_cost += matched_cost
            total_buy_fees += matched_fee
            remaining_sell_volume -= matched_volume
        
        if remaining_sell_volume > 0:
            logger.warning(f"Could not match all sell volume: {remaining_sell_volume} remaining")
        
        # Calculate profit
        sell_revenue = sell_volume * sell_price
        total_cost_with_fees = total_cost + total_buy_fees + sell_fee
        profit = sell_revenue - total_cost_with_fees
        
        return profit

    except Exception as e:
        logger.error(f"Error calculating trade profit: {e}")
        return None


def update_matched_buy_trades(matched_buy_trades, pair):
    """
    Update buy trades that were matched in profit calculations to prevent double-counting
    """
    import os
    
    try:
        if not matched_buy_trades:
            return

        # Read all current trades
        all_trades = []
        if os.path.exists(config.TRADES_FILE):
            with open(config.TRADES_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            trade = eval(line.strip())
                            all_trades.append(trade)
                        except BaseException:
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

                    # Mark as matched
                    trade['matched_volume'] = trade.get('matched_volume', 0) + matched_volume
                    if trade['matched_volume'] >= trade.get('volume', 0):
                        trade['fully_matched'] = True

                    updated_count += 1
                    break

        if updated_count > 0:
            # Write back updated trades
            with open(config.TRADES_FILE, "w") as f:
                for trade in all_trades:
                    f.write(str(trade) + "\n")

            logger.info(f"Updated {updated_count} matched buy trades for {pair}")

    except Exception as e:
        logger.error(f"Error updating matched buy trades: {e}")

