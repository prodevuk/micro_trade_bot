"""Exchange comparison logic for selecting best exchange per trading pair"""

import logging
import config

logger = logging.getLogger(__name__)


def normalize_pair_format(pair, exchange):
    """
    Normalize pair format for a specific exchange
    Args:
        pair: Pair in any format (e.g., BTCUSDT or BTC_USDT)
        exchange: Exchange object (ExchangeKraken or ExchangeBitMart)
    Returns:
        Exchange-specific pair format
    """
    return exchange.normalize_pair(pair)


def get_exchange_pair_format(pair, exchange):
    """
    Get exchange-specific pair format
    Args:
        pair: Normalized pair (e.g., BTCUSDT)
        exchange: Exchange object
    Returns:
        Exchange-specific pair format
    """
    return exchange.get_pair_format(pair)


def compare_exchanges(pair, exchanges):
    """
    Compare exchanges for a given pair based on price and liquidity
    Args:
        pair: Trading pair to compare
        exchanges: Dictionary of exchange_name -> exchange_object
    Returns:
        List of tuples: (exchange_name, exchange_object, score, price, liquidity)
        Sorted by score (higher is better)
    """
    comparison_results = []
    
    for exchange_name, exchange in exchanges.items():
        try:
            # Get ticker (price)
            ticker = exchange.get_ticker(pair)
            if not ticker:
                logger.debug(f"No ticker data for {pair} on {exchange_name}")
                continue
            
            # Extract price (handle different exchange formats)
            exchange_pair = exchange.get_pair_format(pair)
            if exchange_pair in ticker:
                price_data = ticker[exchange_pair]
            else:
                # Try to find any key in ticker
                price_data = list(ticker.values())[0] if ticker else None
            
            if not price_data:
                continue
            
            # Get price (format: ['last_price', ...])
            current_price = float(price_data.get('c', [0])[0] if isinstance(price_data.get('c'), list) else price_data.get('c', 0))
            
            if current_price <= 0:
                continue
            
            # Get order book for liquidity analysis
            order_book = exchange.get_order_book(pair, count=10)
            liquidity_score = 0.0
            
            if order_book:
                exchange_pair = exchange.get_pair_format(pair)
                if exchange_pair in order_book:
                    book_data = order_book[exchange_pair]
                else:
                    book_data = list(order_book.values())[0] if order_book else None
                
                if book_data:
                    # Calculate liquidity depth (sum of top 10 bids/asks)
                    bids = book_data.get('bids', [])
                    asks = book_data.get('asks', [])
                    
                    bid_depth = sum(float(bid[1]) for bid in bids[:10])
                    ask_depth = sum(float(ask[1]) for ask in asks[:10])
                    liquidity_score = (bid_depth + ask_depth) * current_price  # Total USD liquidity
            
            # Calculate score (lower price = better, higher liquidity = better)
            # Score = liquidity_score / price (higher is better)
            score = liquidity_score / current_price if current_price > 0 else 0
            
            comparison_results.append((exchange_name, exchange, score, current_price, liquidity_score))
            
        except Exception as e:
            logger.error(f"Error comparing {exchange_name} for {pair}: {e}")
            continue
    
    # Sort by score (higher is better)
    comparison_results.sort(key=lambda x: x[2], reverse=True)
    return comparison_results


def select_best_exchange(pair, exchanges):
    """
    Select the best exchange for a given pair based on price and liquidity comparison
    Args:
        pair: Trading pair
        exchanges: Dictionary of exchange_name -> exchange_object
    Returns:
        Tuple: (exchange_name, exchange_object) or (None, None) if no suitable exchange
    """
    if not exchanges:
        return None, None
    
    comparison_results = compare_exchanges(pair, exchanges)
    
    if not comparison_results:
        logger.debug(f"No exchange data available for {pair}")
        return None, None
    
    # Get best exchange
    best_exchange_name, best_exchange, best_score, best_price, best_liquidity = comparison_results[0]
    
    # Log comparison results
    logger.info(f"Exchange comparison for {pair}:")
    for exchange_name, exchange, score, price, liquidity in comparison_results:
        marker = " <-- SELECTED" if exchange_name == best_exchange_name else ""
        logger.info(f"  {exchange_name}: Price=${price:.8f}, Liquidity=${liquidity:.2f}, Score={score:.2f}{marker}")
    
    # Check if price difference is significant enough
    if len(comparison_results) > 1:
        second_best_price = comparison_results[1][3]
        price_diff = abs(best_price - second_best_price) / second_best_price if second_best_price > 0 else 0
        
        if price_diff < config.EXCHANGE_PRICE_DIFF_THRESHOLD:
            # Price difference is small, prefer liquidity if configured
            if config.EXCHANGE_LIQUIDITY_PREFERENCE:
                # Already sorted by score (which includes liquidity), so best_exchange is correct
                logger.debug(f"Price difference ({price_diff*100:.2f}%) below threshold, using liquidity preference")
            else:
                logger.debug(f"Price difference ({price_diff*100:.2f}%) below threshold, using first exchange")
    
    return best_exchange_name, best_exchange

