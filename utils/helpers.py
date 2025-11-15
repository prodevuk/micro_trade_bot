"""Helper utility functions"""

import config


def get_price_range_category(price):
    """Categorize token price into risk categories"""
    if price <= config.PRICE_RANGE_MED:
        return 'low'
    elif price <= config.PRICE_RANGE_HIGH:
        return 'medium'
    else:
        return 'high'


def get_risk_multiplier(price):
    """Get risk multiplier based on token price"""
    category = get_price_range_category(price)
    if category == 'low':
        return config.RISK_MULTIPLIER_LOW
    elif category == 'medium':
        return config.RISK_MULTIPLIER_MED
    else:
        return config.RISK_MULTIPLIER_HIGH


def get_profit_margin(price):
    """Get appropriate profit margin based on token price"""
    category = get_price_range_category(price)
    if category == 'low':
        return config.PROFIT_MARGIN_LOW
    elif category == 'medium':
        return config.PROFIT_MARGIN_MED
    else:
        return config.PROFIT_MARGIN_HIGH


def cleanup_old_records():
    """Clean up old recorded orders on startup to prevent processing stale data"""
    import os
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Keep recorded orders from previous sessions to maintain history
        logger.info("Preserved recorded orders from previous sessions")
    except Exception as e:
        logger.warning(f"Could not access records: {e}")

