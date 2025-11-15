"""Price movement analysis functions"""

import logging
import config
from utils.helpers import get_price_range_category
from exchanges.kraken import get_recent_trades_kraken

logger = logging.getLogger(__name__)


def analyze_price_movement(pair, exchange=None):
    """Analyze recent price movement to determine trend"""
    if not exchange:
        from exchanges.kraken import ExchangeKraken
        exchange = ExchangeKraken(config.KRAKEN_API_KEY, config.KRAKEN_API_SECRET)
    
    # Note: BitMart may not have recent trades API, so return neutral
    if exchange.name == 'bitmart':
        return "neutral"
    
    # For Kraken, use get_recent_trades_kraken
    try:
        if exchange.name == 'kraken':
            trades = get_recent_trades_kraken(pair, api_key=exchange.api_key, api_secret=exchange.api_secret)
        else:
            return "neutral"
        if not trades or pair not in trades:
            return "neutral"
        
        recent_trades = trades[pair][-20:]  # Last 20 trades
        if len(recent_trades) < 10:
            return "neutral"
        
        # Calculate price changes
        price_changes = []
        for i in range(1, len(recent_trades)):
            prev_price = float(recent_trades[i - 1][0])
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
    except Exception as e:
        logger.error(f"Error analyzing price movement for {pair}: {e}")
        return "neutral"


def is_profitable_opportunity(pair, current_price, estimated_fees, exchange=None, ml_analyzer=None):
    """Check if a pair represents a profitable trading opportunity using ML when available"""
    if not exchange:
        from exchanges.kraken import ExchangeKraken
        exchange = ExchangeKraken(config.KRAKEN_API_KEY, config.KRAKEN_API_SECRET)
    
    try:
        # First, try ML-based prediction if ML is enabled and model is available
        if config.ML_ENABLED and ml_analyzer and ml_analyzer.is_trained:
            import trade_analyzer_ml
            # Estimate volume for prediction (use a reasonable default)
            estimated_volume = 100.0

            prediction, confidence = trade_analyzer_ml.predict_trade_opportunity(
                pair=pair,
                price=current_price,
                volume=estimated_volume,
                fees=estimated_fees
            )

            if prediction is not None and confidence > 0.6:  # Require 60% confidence
                logger.info(
                    f"ML Prediction for {pair}: {'BUY' if prediction else 'SKIP'} (confidence: {confidence:.2f})")
                return prediction

        # Fallback to traditional analysis if ML is disabled or not available/confident
        # First check 24h volume - must be over 500k
        ticker_info = exchange.get_ticker(pair)
        exchange_pair = exchange.get_pair_format(pair)
        
        if not ticker_info:
            print(f"[DEBUG] No ticker info for {pair}")
            return False
        
        # Extract price data (handle different exchange formats)
        if exchange_pair in ticker_info:
            price_data = ticker_info[exchange_pair]
        else:
            price_data = list(ticker_info.values())[0] if ticker_info else None
        
        if not price_data:
            print(f"[DEBUG] No price data for {pair}")
            return False
        
        # Get 24h volume in quote currency (USDT)
        volume_24h = float(price_data.get("v", [0, 0])[1] if isinstance(price_data.get("v"), list) else price_data.get("v", 0))
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
        trend = analyze_price_movement(pair, exchange)
        
        # Get order book to check liquidity
        order_book = exchange.get_order_book(pair, count=5)
        if not order_book:
            return False
        
        # Extract order book data
        if exchange_pair in order_book:
            book_data = order_book[exchange_pair]
        else:
            book_data = list(order_book.values())[0] if order_book else None
        
        if not book_data:
            return False

        bids = book_data.get("bids", [])
        asks = book_data.get("asks", [])
        
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

