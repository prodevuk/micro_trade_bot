"""Position tracking functions"""

import os
import time
import logging
import config

logger = logging.getLogger(__name__)


def save_open_positions(open_positions, exchange='kraken'):
    """Save open positions to disk for persistence across restarts"""
    try:
        filename = f"{config.TRADE_LOGS_DIR}/open_positions_{exchange}.txt"
        with open(filename, "w") as f:
            for position in open_positions:
                f.write(str(position) + "\n")
        logger.debug(f"Saved {len(open_positions)} open positions to disk for {exchange}")
    except Exception as e:
        logger.error(f"Error saving open positions for {exchange}: {e}")


def load_open_positions(exchange='kraken'):
    """Load open positions from disk on startup"""
    open_positions = []
    try:
        filename = f"{config.TRADE_LOGS_DIR}/open_positions_{exchange}.txt"
        if os.path.exists(filename):
            with open(filename, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            position = eval(line.strip())
                            # Only keep positions that are still relevant (not too old)
                            if time.time() - position.get('timestamp', 0) < 86400:  # 24 hours
                                open_positions.append(position)
                        except:
                            continue
            logger.info(f"Loaded {len(open_positions)} open positions from disk for {exchange}")

            # Clean up old positions file if we filtered some out
            if len(open_positions) < count_lines_in_file(filename):
                save_open_positions(open_positions, exchange)

    except Exception as e:
        logger.error(f"Error loading open positions for {exchange}: {e}")

    return open_positions


def count_lines_in_file(filename):
    """Count lines in a file"""
    try:
        with open(filename, "r") as f:
            return sum(1 for _ in f)
    except:
        return 0


def add_open_position(open_positions, pair, order_id, side, volume, price, exchange='kraken', timestamp=None):
    """Add a new open position to track"""
    if timestamp is None:
        timestamp = time.time()

    position = {
        'pair': pair,
        'order_id': order_id,
        'side': side,  # 'buy' or 'sell'
        'volume': volume,
        'price': price,
        'exchange': exchange,  # Track which exchange this position is on
        'timestamp': timestamp,
        'status': 'open'
    }

    open_positions.append(position)
    save_open_positions(open_positions, exchange)
    logger.info(f"Added open position on {exchange}: {side} {volume} {pair} @ {price}")


def update_position_status(open_positions, order_id, new_status, exchange='kraken'):
    """Update the status of an open position"""
    for position in open_positions:
        if position['order_id'] == order_id and position.get('exchange') == exchange:
            position['status'] = new_status
            if new_status == 'filled':
                position['filled_timestamp'] = time.time()
            save_open_positions(open_positions, exchange)
            logger.info(f"Updated position {order_id} on {exchange} status to {new_status}")
            return True
    return False


def get_open_positions_for_pair(open_positions, pair):
    """Get all open positions for a specific pair"""
    return [p for p in open_positions if p['pair'] == pair and p['status'] == 'open']


def cleanup_filled_positions(open_positions, exchange='kraken'):
    """Remove positions that have been filled and processed"""
    # This will be called periodically to clean up old filled positions
    # Keep filled positions for 1 hour in case we need to reference them
    cutoff_time = time.time() - 3600  # 1 hour ago

    cleaned_positions = []
    for position in open_positions:
        # Only process positions for this exchange
        if position.get('exchange') != exchange:
            cleaned_positions.append(position)
            continue
        
        if position['status'] == 'filled':
            if position.get('filled_timestamp', 0) < cutoff_time:
                continue  # Remove old filled positions
        cleaned_positions.append(position)

    if len(cleaned_positions) != len(open_positions):
        save_open_positions(cleaned_positions, exchange)
        logger.info(f"Cleaned up {len(open_positions) - len(cleaned_positions)} old filled positions for {exchange}")

    return cleaned_positions

