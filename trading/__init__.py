"""Trading logic modules"""

from .strategy import simple_trading_strategy, calculate_dynamic_buy_price, calculate_optimal_sell_price
from .order_manager import (
    manage_open_orders,
    check_and_place_sell_orders,
    check_and_record_completed_trades,
    record_open_order,
    has_open_sell_orders_for_pair,
    has_open_orders_for_pair,
)
from .position_tracker import (
    save_open_positions,
    load_open_positions,
    add_open_position,
    update_position_status,
    get_open_positions_for_pair,
    cleanup_filled_positions,
)

__all__ = [
    'simple_trading_strategy',
    'calculate_dynamic_buy_price',
    'calculate_optimal_sell_price',
    'manage_open_orders',
    'check_and_place_sell_orders',
    'check_and_record_completed_trades',
    'record_open_order',
    'has_open_sell_orders_for_pair',
    'has_open_orders_for_pair',
    'save_open_positions',
    'load_open_positions',
    'add_open_position',
    'update_position_status',
    'get_open_positions_for_pair',
    'cleanup_filled_positions',
]

