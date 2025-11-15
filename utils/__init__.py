"""Utility functions for trading bot"""

from .session import update_session_metrics, generate_session_summary, record_trade, train_bot
from .profit import calculate_trade_profit, update_matched_buy_trades
from .price_analysis import analyze_price_movement, is_profitable_opportunity
from .helpers import (
    get_price_range_category,
    get_risk_multiplier,
    get_profit_margin,
    cleanup_old_records,
)

__all__ = [
    'update_session_metrics',
    'generate_session_summary',
    'record_trade',
    'train_bot',
    'calculate_trade_profit',
    'update_matched_buy_trades',
    'analyze_price_movement',
    'is_profitable_opportunity',
    'get_price_range_category',
    'get_risk_multiplier',
    'get_profit_margin',
    'cleanup_old_records',
]

