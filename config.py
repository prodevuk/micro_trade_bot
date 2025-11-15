"""
Configuration settings for the Kraken Microtrading Bot.
Modify these values to customize bot behavior.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Trading Parameters
MAX_ACCOUNT_USAGE_PERCENT = 0.10  # Maximum 10% of account balance for open orders (conservative for micro-caps)
MAX_TRADE_SIZE_PERCENT = 0.03     # Maximum 3% of allocated balance per trade (smaller for micro-caps)
SLEEP_INTERVAL_SECONDS = 45       # Seconds between trading cycles (faster for scalping)

# Token Price-Based Adjustments
PRICE_RANGE_LOW = 0.0     # $0.00 - $0.05 (micro tokens)
PRICE_RANGE_MED = 0.05    # $0.05 - $0.15 (medium tokens)
PRICE_RANGE_HIGH = 0.15   # $0.15+ (higher-priced tokens)

# Fee Settings (adjust based on your Kraken fee tier)
TAKER_FEE_PERCENT = 0.0026        # 0.26% taker fee
MAKER_FEE_PERCENT = 0.0016        # 0.16% maker fee (if applicable)

# Risk Management
MIN_PROFIT_MARGIN = 0.005         # Minimum 0.5% profit margin required
MAX_OPEN_ORDERS = 6               # Maximum number of open orders allowed (reduced for micro-caps)
MAX_ORDERS_PER_PAIR = 2           # Maximum buy+sell orders per trading pair

# Price-Based Risk Adjustments
RISK_MULTIPLIER_LOW = 1.0         # Risk multiplier for low-priced tokens ($0-0.05)
RISK_MULTIPLIER_MED = 0.7         # Risk multiplier for medium-priced tokens ($0.05-0.15)
RISK_MULTIPLIER_HIGH = 0.4        # Risk multiplier for high-priced tokens ($0.15+)

# Profit Margins by Price Range (reduced for micro-cap scalping)
PROFIT_MARGIN_LOW = 0.003         # 0.3% profit margin for low-priced tokens
PROFIT_MARGIN_MED = 0.002         # 0.2% profit margin for medium-priced tokens
PROFIT_MARGIN_HIGH = 0.001        # 0.1% profit margin for high-priced tokens

# Technical Parameters
PRICE_ANALYSIS_WINDOW = 10        # Number of recent trades to analyze
VOLATILITY_THRESHOLD = 0.05       # Maximum volatility for safe trading
ORDER_BOOK_DEPTH = 10             # Number of order book levels to analyze

# Balance Management
BALANCE_CACHE_DURATION = 60       # Cache balance for 60 seconds to reduce API calls

# Margin Trading
MARGIN_TRADING_ENABLED = os.getenv("MARGIN_TRADING_ENABLED", "False").lower() == "true"  # Enable/disable margin trading
DEFAULT_LEVERAGE = float(os.getenv("DEFAULT_LEVERAGE", "2.0"))  # Default leverage for margin orders (2x, 3x, etc.)

# Logging Configuration
LOG_LEVEL = "INFO"                 # DEBUG, INFO, WARNING, ERROR
LOG_TO_FILE = True                 # Save logs to file
LOG_TO_CONSOLE = True              # Show logs in console

# File Paths
TRADE_LOGS_DIR = "trade_logs"      # Directory for trade logs
TRADES_FILE = f"{TRADE_LOGS_DIR}/trades.txt"                    # Trade history file
RECORDED_ORDERS_FILE = f"{TRADE_LOGS_DIR}/recorded_orders.txt"  # Order tracking file
LOG_FILE = f"{TRADE_LOGS_DIR}/trading_bot.log"                  # Main log file
OPEN_POSITIONS_FILE = f"{TRADE_LOGS_DIR}/open_positions_{{exchange}}.txt"    # Open positions file template
SESSIONS_DIR = f"{TRADE_LOGS_DIR}/sessions"                     # Session summaries directory

# API Settings
API_TIMEOUT_SECONDS = 60           # API request timeout
MAX_RETRIES = 3                    # Maximum API retry attempts
RETRY_DELAY_SECONDS = 5            # Delay between retries

# Sub-cent Token Criteria
MAX_TOKEN_PRICE = 0.2            # Maximum price for "sub-cent" tokens ($0.01)
MIN_LIQUIDITY_DEPTH = 1000         # Minimum order book liquidity required

# Learning System
LEARNING_ENABLED = os.getenv("LEARNING_ENABLED", "True").lower() == "true"            # Enable/disable trade analysis
ML_ENABLED = os.getenv("ML_ENABLED", "False").lower() == "true"                 # Enable/disable machine learning predictions
WIN_RATE_WARNING_THRESHOLD = 0.30  # Alert if win rate below 30%
WIN_RATE_SUCCESS_THRESHOLD = 0.70  # Log success if win rate above 70%

# Multi-Exchange Support
BITMART_ENABLED = os.getenv("BITMART_ENABLED", "False").lower() == "true"             # Enable/disable BitMart exchange integration
KRAKEN_ENABLED = os.getenv("KRAKEN_ENABLED", "True").lower() == "true"             # Enable/disable Kraken exchange integration

# Exchange Selection Parameters
EXCHANGE_PRICE_DIFF_THRESHOLD = 0.001  # Minimum 0.1% price difference to prefer one exchange
EXCHANGE_LIQUIDITY_PREFERENCE = True    # Prefer exchange with better liquidity (order book depth)

KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY", "")
KRAKEN_API_SECRET = os.getenv("KRAKEN_API_SECRET", "")
BITMART_API_KEY = os.getenv("BITMART_API_KEY", "")
BITMART_SECRET_KEY = os.getenv("BITMART_SECRET_KEY", "")
BITMART_MEMO = os.getenv("BITMART_MEMO", "")
BITMART_FUTURES_ENABLED = os.getenv("BITMART_FUTURES_ENABLED", "False")             # Enable/disable BitMart futures exchange integration
BITMART_FUTURES_MAKER_FEE = os.getenv("BITMART_FUTURES_MAKER_FEE", "0.0002")             # BitMart futures maker fee (0.02%)
BITMART_FUTURES_TAKER_FEE = os.getenv("BITMART_FUTURES_TAKER_FEE", "0.0006")             # BitMart futures taker fee (0.06%)

# Display Settings
ENABLE_COLOR_OUTPUT = os.getenv("ENABLE_COLOR_OUTPUT", "True").lower() == "true"  # Enable colored console output
ENABLE_LIVE_DASHBOARD = os.getenv("ENABLE_LIVE_DASHBOARD", "True").lower() == "true"  # Enable live dashboard view
DASHBOARD_REFRESH_INTERVAL = 5  # Seconds between dashboard updates
DASHBOARD_POSITION = "top"  # Position of dashboard: "top" or "bottom"
