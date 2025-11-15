"""Main entry point for the trading bot"""

import os
import time
import logging
import config
import trade_analyzer_ml
import display
from display import ColorPrint

# Import exchange classes
from exchanges import ExchangeKraken, ExchangeBitMart, select_best_exchange

# Import trading functions
from trading import (
    simple_trading_strategy,
    manage_open_orders,
    check_and_place_sell_orders,
    check_and_record_completed_trades,
    has_open_orders_for_pair,
    load_open_positions,
    cleanup_filled_positions,
    get_open_positions_for_pair,
)

# Import utility functions
from utils import (
    generate_session_summary,
    update_session_metrics,
    is_profitable_opportunity,
)

# Import Kraken-specific functions
from exchanges.kraken import get_sub_cent_tokens

# API credentials
API_KEY = config.KRAKEN_API_KEY
API_SECRET = config.KRAKEN_API_SECRET

# BitMart API credentials (optional)
BITMART_API_KEY = config.BITMART_API_KEY
BITMART_SECRET_KEY = config.BITMART_SECRET_KEY
BITMART_MEMO = config.BITMART_MEMO

# Validate API credentials
if not API_KEY or not API_SECRET:
    raise ValueError(
        "Missing Kraken API credentials. Please check your .env file.")

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

# Global state
exchange_open_order_values = {'kraken': 0.0, 'bitmart': 0.0}
exchange_balances = {'kraken': {}, 'bitmart': {}}
balance_cache = {'kraken': {'data': None, 'timestamp': 0}, 'bitmart': {'data': None, 'timestamp': 0}}
ml_analyzer = None


def get_cached_balance(exchange, exchange_name, force_refresh=False):
    """Get balance with caching to avoid rate limits"""
    import time

    current_time = time.time()
    cache_entry = balance_cache[exchange_name]

    # Check if we have valid cached data and it's not expired
    if not force_refresh and cache_entry['data'] and (current_time - cache_entry['timestamp']) < config.BALANCE_CACHE_DURATION:
        logger.debug(f"Using cached balance for {exchange_name}")
        return cache_entry['data']

    # Need to fetch fresh balance
    max_retries = 3
    for attempt in range(max_retries):
        try:
            balance_response = exchange.get_balance()

            # Check if the response contains rate limit error
            if balance_response is None:
                # Check if this might be a rate limit error (exchange.get_balance() returns None on error)
                logger.warning(f"Balance request returned None for {exchange_name} (attempt {attempt + 1})")
                # Assume rate limit and use exponential backoff
                wait_time = (2 ** attempt) * 5  # 5, 10, 20 seconds
                logger.warning(f"Possible rate limit for {exchange_name}, waiting {wait_time} seconds")
                time.sleep(wait_time)
                continue
            elif balance_response and isinstance(balance_response, dict):
                # Check for rate limit in error field (for exchanges like Kraken)
                if 'error' in balance_response and balance_response['error']:
                    error_list = balance_response['error']
                    if isinstance(error_list, list) and any('Rate limit' in str(err) for err in error_list):
                        wait_time = (2 ** attempt) * 5  # 5, 10, 20 seconds
                        logger.warning(f"Rate limit error for {exchange_name}, waiting {wait_time} seconds")
                        time.sleep(wait_time)
                        continue

                # Successful response
                cache_entry['data'] = balance_response
                cache_entry['timestamp'] = current_time
                logger.debug(f"Fetched fresh balance for {exchange_name}")
                return balance_response
            else:
                logger.warning(f"Unexpected balance response format from {exchange_name} (attempt {attempt + 1})")

        except Exception as e:
            error_str = str(e).lower()
            if 'rate limit' in error_str or 'rate_limit' in error_str:
                # Exponential backoff for rate limits
                wait_time = (2 ** attempt) * 5  # 5, 10, 20 seconds
                logger.warning(f"Rate limit exception for {exchange_name}, waiting {wait_time} seconds")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"Error getting balance from {exchange_name}: {e}")
                break

        # Wait before retry (except on rate limit which has its own wait)
        if attempt < max_retries - 1:
            time.sleep(2)

    logger.error(f"Failed to get balance from {exchange_name} after {max_retries} attempts")
    return None


def main():
    """Main trading bot function"""
    global ml_analyzer, exchange_open_order_values, exchange_balances
    
    logger.info("Multi-Exchange Trading Bot Started.")
    
    # Initialize display system
    dashboard = display.init_display()
    ColorPrint.success("Trading bot starting up...")

    # Initialize session tracking
    session_start_time = time.time()
    session_metrics = {
        'start_time': session_start_time,
        'end_time': None,
        'total_trades': 0,
        'buy_trades': 0,
        'sell_trades': 0,
        'total_volume': 0.0,
        'total_profit_loss': 0.0,
        'winning_trades': 0,
        'losing_trades': 0,
        'errors_encountered': 0,
        'orders_placed': 0,
        'orders_filled': 0,
        'total_fees': 0.0,
        'pairs_traded': set(),
        'shutdown_reason': 'normal',
        'trades_per_exchange': {'kraken': 0, 'bitmart': 0},
        'profit_per_exchange': {'kraken': 0.0, 'bitmart': 0.0}
    }

    # Initialize exchanges
    exchanges = {}
    
    # Initialize Kraken if enabled
    if config.KRAKEN_ENABLED and API_KEY and API_SECRET:
        kraken_exchange = ExchangeKraken(API_KEY, API_SECRET)
        exchanges['kraken'] = kraken_exchange
        logger.info("Kraken exchange initialized")
    elif config.KRAKEN_ENABLED:
        logger.warning("Kraken enabled in config but API credentials missing")
    
    # Initialize BitMart if enabled
    if config.BITMART_ENABLED and BITMART_API_KEY and BITMART_SECRET_KEY and BITMART_MEMO:
        bitmart_exchange = ExchangeBitMart(BITMART_API_KEY, BITMART_SECRET_KEY, BITMART_MEMO)
        if bitmart_exchange.client:
            exchanges['bitmart'] = bitmart_exchange
            logger.info("BitMart exchange initialized")
        else:
            logger.warning("BitMart enabled but client initialization failed")
    elif config.BITMART_ENABLED:
        logger.warning("BitMart enabled in config but API credentials missing")

    if not exchanges:
        logger.error("No exchanges initialized. Cannot trade.")
        return

    # Initialize open position tracking per exchange
    all_open_positions = {}
    position_cleanup_counter = 0

    try:
        # Load existing open positions from disk for each exchange
        for exchange_name in exchanges.keys():
            all_open_positions[exchange_name] = load_open_positions(exchange_name)
            logger.info(f"Tracking {len(all_open_positions[exchange_name])} existing open positions for {exchange_name}")
        

        # Initialize ML system if enabled
        if config.ML_ENABLED:
            ml_analyzer = trade_analyzer_ml.initialize_ml_system()
            logger.info("Machine Learning system enabled")
        else:
            ml_analyzer = None
            logger.info("Machine Learning system disabled - using traditional analysis only")

        time_to_sleep = config.SLEEP_INTERVAL_SECONDS

        # Get account balances for each exchange (with caching and rate limit handling)
        exchange_usdt_balances = {}
        for exchange_name, exchange in exchanges.items():
            balance_response = get_cached_balance(exchange, exchange_name, force_refresh=True)  # Force refresh at startup
            if balance_response:
                logger.info(f"{exchange_name} Account Balance: {balance_response}")
                
                # Update dashboard with balance
                dashboard.update_balances(exchange_name, balance_response)
                dashboard.update_exchange_status(exchange_name, "connected")
                
                # Calculate total USDT balance
                total_usdt_balance = 0
                for currency, amount in balance_response.items():
                    if currency == "USDT" or (exchange_name == 'bitmart' and 'USDT' in str(currency)):
                        total_usdt_balance = float(amount)
                        break
                
                if total_usdt_balance <= 0:
                    ColorPrint.warning(f"No USDT balance found on {exchange_name}. Skipping this exchange.")
                    continue
                
                exchange_usdt_balances[exchange_name] = total_usdt_balance
                exchange_balances[exchange_name] = balance_response
                ColorPrint.success(f"Total USDT Balance on {exchange_name}: ${total_usdt_balance:.2f}")
            else:
                ColorPrint.error(f"Could not retrieve account balance from {exchange_name}")
                dashboard.update_exchange_status(exchange_name, "error")

        if not exchange_usdt_balances:
            logger.error("No USDT balance found on any exchange. Cannot trade.")
            session_metrics['shutdown_reason'] = 'no_balance'
            return

        ColorPrint.success("Starting trading loop...")
        
        while True:
            try:
                # First, check for and record any completed trades per exchange
                for exchange_name, exchange in exchanges.items():
                    try:
                        check_and_record_completed_trades(
                            session_metrics, 
                            all_open_positions.get(exchange_name, []), 
                            exchange,
                            exchange_open_order_values
                        )
                    except Exception as e:
                        ColorPrint.debug(f"[DEBUG] Error checking completed trades on {exchange_name}: {e}")

                # Update dashboard with latest session metrics after trade processing
                dashboard.update_session_metrics(session_metrics)

                # Then, manage existing open orders per exchange
                orders_canceled_any = False
                for exchange_name, exchange in exchanges.items():
                    try:
                        # Get open orders and update dashboard
                        open_orders_response = exchange.get_open_orders()
                        if open_orders_response:
                            dashboard.update_open_orders(exchange_name, open_orders_response)
                        
                        orders_canceled = manage_open_orders(exchange, exchange_open_order_values)
                        if orders_canceled:
                            orders_canceled_any = True
                    except Exception as e:
                        ColorPrint.debug(f"[DEBUG] Error in manage_open_orders on {exchange_name}: {e}")
                
                # Check for filled buy orders and place sell orders per exchange
                for exchange_name, exchange in exchanges.items():
                    try:
                        check_and_place_sell_orders(
                            all_open_positions.get(exchange_name, []), 
                            exchange,
                            exchange_open_order_values
                        )
                    except Exception as e:
                        print(f"[DEBUG] Error in check_and_place_sell_orders on {exchange_name}: {e}")
                
                # If orders were canceled, wait a bit before placing new ones
                if orders_canceled_any:
                    print(f"[DEBUG] Waiting {time_to_sleep / 2} seconds after canceling orders...")
                    time.sleep(time_to_sleep / 2)
                
                # Get sub-cent tokens from all exchanges
                all_sub_cent_tokens = {}
                for exchange_name, exchange in exchanges.items():
                    try:
                        ColorPrint.info(f"Getting sub-1-cent tokens from {exchange_name}...")
                        # TODO: Update get_sub_cent_tokens to accept exchange parameter
                        # For now, only get from Kraken
                        if exchange_name == 'kraken':
                            sub_cent_tokens = get_sub_cent_tokens(API_KEY, API_SECRET)
                            # Merge tokens, preferring lower prices
                            for pair, info in sub_cent_tokens.items():
                                if pair not in all_sub_cent_tokens:
                                    all_sub_cent_tokens[pair] = {'exchange': exchange_name, 'info': info}
                    except Exception as e:
                        ColorPrint.debug(f"[DEBUG] Error getting sub-cent tokens from {exchange_name}: {e}")
                
                if not all_sub_cent_tokens:
                    ColorPrint.warning(f"No sub-cent tokens found. Waiting {time_to_sleep} seconds...")
                    time.sleep(time_to_sleep)
                    continue

                ColorPrint.success(f"Sub-1-cent tokens found: {len(all_sub_cent_tokens)}")
                
                # Update dashboard with current pairs being monitored
                dashboard.update_current_pairs(list(all_sub_cent_tokens.keys()))

                # Place new orders for available tokens using exchange selection
                for pair, pair_data in all_sub_cent_tokens.items():
                    try:
                        print(f"[DEBUG] Processing {pair}")
                        
                        # Select best exchange for this pair
                        best_exchange_name, best_exchange = select_best_exchange(pair, exchanges)
                        if not best_exchange or not best_exchange_name:
                            print(f"[DEBUG] No suitable exchange found for {pair}")
                            continue
                        
                        # Get ticker from selected exchange
                        ticker_info = best_exchange.get_ticker(pair)
                        exchange_pair = best_exchange.get_pair_format(pair)
                        
                        if ticker_info:
                            # Extract price (handle different exchange formats)
                            if exchange_pair in ticker_info:
                                price_data = ticker_info[exchange_pair]
                            else:
                                price_data = list(ticker_info.values())[0] if ticker_info else None
                            
                            if price_data:
                                current_price = float(price_data.get('c', [0])[0] if isinstance(price_data.get('c'), list) else price_data.get('c', 0))

                                # Double-check that the token still meets our price criteria
                                if current_price > config.MAX_TOKEN_PRICE:
                                    print(f"[DEBUG] Skipping {pair}: Price {current_price} now exceeds limit {config.MAX_TOKEN_PRICE}")
                                    continue

                                # Placeholder for fee calculation
                                estimated_fees = 0.0026  # Example: 0.26% taker fee

                                # Check for existing open orders on this exchange
                                exchange_positions = all_open_positions.get(best_exchange_name, [])
                                existing_positions = get_open_positions_for_pair(exchange_positions, pair)
                                print(f"[DEBUG] {pair} has {len(existing_positions)} existing orders on {best_exchange_name}")

                                # Check if we've exceeded max orders per pair
                                if len(existing_positions) >= config.MAX_ORDERS_PER_PAIR:
                                    print(f"[DEBUG] Skipping {pair}: Already have {len(existing_positions)} orders (max {config.MAX_ORDERS_PER_PAIR})")
                                    continue

                                # Check if it's a profitable opportunity
                                is_profitable = is_profitable_opportunity(
                                    pair, current_price, estimated_fees, best_exchange, ml_analyzer)
                                print(f"[DEBUG] {pair} is profitable opportunity: {is_profitable}")

                                if is_profitable:
                                    print(f"[DEBUG] Placing trade for {pair} at price {current_price} on {best_exchange_name}")
                                    
                                    # Get pair info from exchange
                                    exchange_pairs = best_exchange.get_tradable_pairs()
                                    if exchange_pairs and exchange_pair in exchange_pairs:
                                        pair_info = exchange_pairs[exchange_pair]
                                        ordermin = pair_info.get('ordermin', '0')
                                        pair_decimals = pair_info.get('pair_decimals', 8)
                                    else:
                                        ordermin = pair_data['info'].get('ordermin', '0')
                                        pair_decimals = pair_data['info'].get('pair_decimals', 8)
                                    
                                    account_balance = exchange_usdt_balances.get(best_exchange_name, 0)
                                    if account_balance > 0:
                                        simple_trading_strategy(
                                            pair,
                                            current_price,
                                            estimated_fees,
                                            account_balance,
                                            ordermin,
                                            pair_decimals,
                                            best_exchange,
                                            exchange_open_order_values,
                                            session_metrics,
                                            exchange_positions)
                                else:
                                    print(f"Skipping {pair}: Not a profitable opportunity ({is_profitable})")
                            else:
                                print(f"[DEBUG] No price data for {pair} on {best_exchange_name}")
                        else:
                            print(f"[DEBUG] No ticker info for {pair} on {best_exchange_name}")
                    except Exception as e:
                        print(f"[DEBUG] Error processing {pair}: {e}")

                # Periodic cleanup of old filled positions per exchange
                position_cleanup_counter += 1
                if position_cleanup_counter >= 10:  # Every 10 cycles
                    for exchange_name in exchanges.keys():
                        all_open_positions[exchange_name] = cleanup_filled_positions(
                            all_open_positions.get(exchange_name, []), exchange_name)
                    position_cleanup_counter = 0
                
                # Wait before next iteration
                print(f"[DEBUG] Waiting {time_to_sleep} seconds before next trading cycle...")
                time.sleep(time_to_sleep)
                
            except KeyboardInterrupt:
                print("\nBot stopped by user.")
                session_metrics['shutdown_reason'] = 'user_interrupt'
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                print(f"Waiting {time_to_sleep} seconds before retrying...")
                time.sleep(time_to_sleep)
                update_session_metrics(session_metrics, error_occurred=True)

    except Exception as e:
        logger.error(f"Fatal error in main function: {e}")
        session_metrics['shutdown_reason'] = f'fatal_error: {str(e)}'
        ColorPrint.error(f"Fatal error: {e}")
        raise
    finally:
        # Shutdown display system
        ColorPrint.info("Shutting down display system...")
        display.shutdown_display()
        
        # Generate and save session summary
        logger.info("Generating session summary...")
        ColorPrint.info("Generating session summary...")
        summary_file = generate_session_summary(session_metrics)
        if summary_file:
            logger.info(f"Session summary saved successfully to {summary_file}")
            ColorPrint.success(f"Session summary saved to {summary_file}")
        else:
            logger.error("Failed to generate session summary")
            ColorPrint.error("Failed to generate session summary")


if __name__ == "__main__":
    import hmac  # Ensure hmac is imported for signature generation
    main()

