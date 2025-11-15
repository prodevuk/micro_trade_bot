"""Session metrics and summary generation"""

import os
import time
import logging
import config
import trade_analyzer_ml

logger = logging.getLogger(__name__)


def record_trade(trade_data, session_metrics=None, exchange_name=None):
    """Record a trade to file and update session metrics"""
    from utils.profit import calculate_trade_profit

    # Calculate profit/loss for sell orders
    if trade_data.get('type') == 'sell':
        # Need exchange to calculate profit
        from exchanges.kraken import ExchangeKraken
        exchange = ExchangeKraken(config.KRAKEN_API_KEY, config.KRAKEN_API_SECRET)
        profit = calculate_trade_profit(trade_data, exchange)
        trade_data['actual_profit'] = profit

    with open(config.TRADES_FILE, "a") as f:
        f.write(str(trade_data) + "\n")

    # Update session metrics if provided
    if session_metrics is not None:
        update_session_metrics(session_metrics, trade_data=trade_data, exchange_name=exchange_name)

    train_bot(trade_data)


def update_session_metrics(
        session_metrics,
        trade_data=None,
        order_placed=False,
        error_occurred=False,
        exchange_name=None):
    """
    Update session metrics with trade data and other events
    """
    try:
        if trade_data:
            session_metrics['total_trades'] += 1
            session_metrics['total_volume'] += trade_data.get('volume', 0)
            session_metrics['total_fees'] += trade_data.get('fees', 0)
            session_metrics['pairs_traded'].add(
                trade_data.get('pair', 'UNKNOWN'))

            # Update per-exchange metrics
            if exchange_name:
                if 'trades_per_exchange' not in session_metrics:
                    session_metrics['trades_per_exchange'] = {'kraken': 0, 'bitmart': 0}
                session_metrics['trades_per_exchange'][exchange_name] = session_metrics['trades_per_exchange'].get(exchange_name, 0) + 1

            if trade_data.get('type') == 'buy':
                session_metrics['buy_trades'] += 1
            elif trade_data.get('type') == 'sell':
                session_metrics['sell_trades'] += 1
                profit = trade_data.get('actual_profit', 0)
                session_metrics['total_profit_loss'] += profit
                
                # Update per-exchange profit
                if exchange_name:
                    if 'profit_per_exchange' not in session_metrics:
                        session_metrics['profit_per_exchange'] = {'kraken': 0.0, 'bitmart': 0.0}
                    session_metrics['profit_per_exchange'][exchange_name] = session_metrics['profit_per_exchange'].get(exchange_name, 0.0) + profit
                
                if profit > 0:
                    session_metrics['winning_trades'] += 1
                elif profit < 0:
                    session_metrics['losing_trades'] += 1

        if order_placed:
            session_metrics['orders_placed'] += 1

        if error_occurred:
            session_metrics['errors_encountered'] += 1

    except Exception as e:
        logger.error(f"Error updating session metrics: {e}")


def generate_session_summary(session_metrics):
    """
    Generate and save a comprehensive session summary
    """
    try:
        session_metrics['end_time'] = time.time()
        session_duration = session_metrics['end_time'] - session_metrics['start_time']

        # Calculate additional metrics
        win_rate = (session_metrics['winning_trades'] /
                    max(session_metrics['sell_trades'], 1)) * 100
        avg_profit_per_trade = session_metrics['total_profit_loss'] / max(
            session_metrics['sell_trades'], 1)
        trades_per_hour = (
            session_metrics['total_trades'] / max(session_duration / 3600, 1))

        # Per-exchange statistics
        trades_per_exchange = session_metrics.get('trades_per_exchange', {'kraken': 0, 'bitmart': 0})
        profit_per_exchange = session_metrics.get('profit_per_exchange', {'kraken': 0.0, 'bitmart': 0.0})
        
        exchange_stats = ""
        for exchange_name in ['kraken', 'bitmart']:
            trades = trades_per_exchange.get(exchange_name, 0)
            profit = profit_per_exchange.get(exchange_name, 0.0)
            if trades > 0:
                exchange_stats += f"\n{exchange_name.upper()} Exchange:\n"
                exchange_stats += f"  - Trades: {trades}\n"
                exchange_stats += f"  - P&L: ${profit:.4f}\n"

        # Create summary
        summary = f"""
TRADING SESSION SUMMARY
{'=' * 50}

Session Details:
- Start Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(session_metrics['start_time']))}
- End Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(session_metrics['end_time']))}
- Duration: {session_duration:.1f} seconds ({session_duration / 3600:.2f} hours)

Trading Performance:
- Total Trades: {session_metrics['total_trades']}
- Buy Orders: {session_metrics['buy_trades']}
- Sell Orders: {session_metrics['sell_trades']}
- Total Volume: {session_metrics['total_volume']:.6f}
- Total P&L: ${session_metrics['total_profit_loss']:.4f}
- Win Rate: {win_rate:.1f}%
- Winning Trades: {session_metrics['winning_trades']}
- Losing Trades: {session_metrics['losing_trades']}
- Average P&L per Trade: ${avg_profit_per_trade:.4f}
- Trades per Hour: {trades_per_hour:.1f}
{exchange_stats}
Operational Metrics:
- Orders Placed: {session_metrics['orders_placed']}
- Orders Filled: {session_metrics['orders_filled']}
- Total Fees: ${session_metrics['total_fees']:.4f}
- Errors Encountered: {session_metrics['errors_encountered']}
- Pairs Traded: {', '.join(session_metrics['pairs_traded']) if session_metrics['pairs_traded'] else 'None'}

Shutdown Reason: {session_metrics['shutdown_reason']}
{'=' * 50}
"""

        # Generate filename with timestamp
        timestamp = time.strftime(
            '%Y%m%d_%H%M%S', time.localtime(
                session_metrics['start_time']))
        filename = f"{config.SESSIONS_DIR}/session_summary_{timestamp}.txt"

        # Ensure sessions directory exists
        os.makedirs(config.SESSIONS_DIR, exist_ok=True)

        # Save summary to file
        with open(filename, 'w') as f:
            f.write(summary)

        logger.info(f"Session summary saved to {filename}")
        print(f"\n{'=' * 60}")
        print("TRADING SESSION COMPLETE")
        print(f"Summary saved to: {filename}")
        print(f"Total P&L: ${session_metrics['total_profit_loss']:.4f}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Total Trades: {session_metrics['total_trades']}")
        print(f"Duration: {session_duration / 3600:.2f} hours")
        print('=' * 60)

        return filename

    except Exception as e:
        logger.error(f"Error generating session summary: {e}")
        return None


def train_bot(trade_data):
    """Train bot with trade data including ML model training"""
    logger.info(f"Training bot with trade data: {trade_data}")

    # Basic learning: analyze profitability and adjust strategy
    try:
        # Load existing trades for analysis
        trades = []
        if os.path.exists(config.TRADES_FILE):
            with open(config.TRADES_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            trades.append(eval(line.strip()))
                        except BaseException:
                            pass

        if trades:
            # Calculate basic statistics
            total_trades = len(trades)
            profitable_trades = sum(
                1 for t in trades if t.get('profit', 0) > 0)
            total_profit = sum(t.get('profit', 0) for t in trades)

            win_rate = profitable_trades / total_trades if total_trades > 0 else 0

            logger.info(
                f"Training analysis - Total trades: {total_trades}, Win rate: {win_rate:.2%}, Total profit: {total_profit:.6f}")

            # Try to train/update ML model if ML is enabled and we have enough data
            if config.ML_ENABLED and total_trades >= 20:  # Need minimum data for meaningful ML training
                logger.info(
                    "Attempting to train ML model with historical data...")
                ml_success = trade_analyzer_ml.train_ml_model()
                if ml_success:
                    logger.info("ML model training completed successfully")
                else:
                    logger.warning("ML model training failed")
            elif config.ML_ENABLED:
                logger.info(
                    f"Need {20 - total_trades} more trades before ML training")
            else:
                logger.debug("ML training skipped - ML system disabled")

            # Simple learning: adjust position sizes based on recent performance
            if win_rate < 0.3:  # Less than 30% win rate
                logger.warning(
                    "Low win rate detected. Consider adjusting strategy parameters.")
            elif win_rate > 0.7:  # More than 70% win rate
                logger.info(
                    "High win rate detected. Strategy performing well.")

    except Exception as e:
        logger.error(f"Error in training: {e}")

