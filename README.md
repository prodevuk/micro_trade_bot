# Kraken Microtrading Bot for Sub-1-Cent Tokens

A sophisticated automated trading bot designed specifically for microtrading sub-1-cent tokens on the Kraken cryptocurrency exchange. The bot implements scalping strategies, dynamic pricing, and machine learning-based trade analysis.

## Features

- **Microtrading Focus**: Specialized for tokens priced below $0.01
- **Machine Learning**: Intelligent trade prediction using historical data
- **Dynamic Pricing**: ML-enhanced buy/sell price calculation based on market conditions
- **Risk Management**: Built-in position sizing and stop-loss mechanisms
- **Margin Trading**: Optional leveraged trading support (Kraken only)
- **Trade Recording**: Complete trade history with profit/loss tracking
- **Advanced Learning System**: ML model training and continuous strategy optimization
- **Real-time Monitoring**: Order book analysis and price movement tracking
- **Thread-safe Operations**: Concurrent processing for multiple trading pairs

## Requirements

- Python 3.8+
- Kraken API credentials (API Key and Secret)
- At least $10 USD in account balance for trading

## Installation

1. **Clone or download the project files**

2. **Set up virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure API credentials:**
   - Copy your Kraken API Key and Secret to the `.env` file:
   ```
   KRAKEN_API_KEY=your_api_key_here
   KRAKEN_API_SECRET=your_api_secret_here
   ```
   - Ensure your API key has trading permissions

## Configuration

The bot includes several configuration parameters that can be adjusted in `config.py`:

### Trading Parameters
- **MAX_ACCOUNT_USAGE_PERCENT**: Maximum percentage of account balance for open orders (default: 15%, adjusted by risk multiplier)
- **MAX_TRADE_SIZE_PERCENT**: Maximum percentage of allocated balance per trade (default: 5%, adjusted by risk multiplier)
- **SLEEP_INTERVAL_SECONDS**: Seconds between trading cycles (default: 60)

### Price-Based Risk Adjustments
- **PRICE_RANGE_LOW**: $0.00 - $0.05 tokens (highest risk multiplier: 1.0)
- **PRICE_RANGE_MED**: $0.05 - $0.15 tokens (medium risk multiplier: 0.7)
- **PRICE_RANGE_HIGH**: $0.15+ tokens (lowest risk multiplier: 0.4)

### Price-Adjusted Profit Margins
- **Low-priced tokens** ($0-0.05): 1.5% profit margin
- **Medium-priced tokens** ($0.05-0.15): 1.0% profit margin
- **High-priced tokens** ($0.15+): 0.7% profit margin

### Fee Settings
- **TAKER_FEE_PERCENT**: Taker fee percentage (default: 0.26%)
- **MAKER_FEE_PERCENT**: Maker fee percentage (default: 0.16%)

### Machine Learning Settings
- **ML_ENABLED**: Enable/disable machine learning predictions (default: True)
- **LEARNING_ENABLED**: Enable/disable trade analysis and learning (default: True)

### Margin Trading Settings (Kraken Only)
- **MARGIN_TRADING_ENABLED**: Enable/disable margin trading (default: False)
- **DEFAULT_LEVERAGE**: Leverage multiplier for margin orders (default: 2.0x)
- **Note**: Margin trading requires sufficient margin balance and increases risk

### Risk Management
- **WIN_RATE_WARNING_THRESHOLD**: Alert threshold for low win rates (default: 30%)
- **WIN_RATE_SUCCESS_THRESHOLD**: Success threshold for high win rates (default: 70%)

### Display Settings
- **ENABLE_COLOR_OUTPUT**: Enable colored console output (default: True)
- **ENABLE_LIVE_DASHBOARD**: Enable live dashboard view (default: True)
- **DASHBOARD_REFRESH_INTERVAL**: Seconds between dashboard updates (default: 5)
- **DASHBOARD_POSITION**: Dashboard position, "top" or "bottom" (default: "top")

### Example Configuration
```python
# Disable ML and use traditional analysis only
ML_ENABLED = False

# Conservative trading with smaller position sizes
MAX_ACCOUNT_USAGE_PERCENT = 0.1  # 10% of balance
MAX_TRADE_SIZE_PERCENT = 0.05    # 5% per trade

# Enable advanced display features
ENABLE_COLOR_OUTPUT = True       # Colored console output
ENABLE_LIVE_DASHBOARD = True     # Live dashboard with real-time updates
```

## ⚠️ Risk Warnings

### Margin Trading Risks
- **HIGH RISK**: Margin trading can amplify both profits and losses
- **Liquidation Risk**: Insufficient margin can lead to forced position closure at a loss
- **Interest Costs**: Margin positions may incur borrowing fees
- **Only enable margin trading if you fully understand leveraged trading risks**
- **Start with low leverage (2x) and small position sizes when testing**

### General Trading Risks
- **Market Volatility**: Cryptocurrency markets are highly volatile
- **API Risks**: Trading bots depend on exchange API availability
- **Technical Risks**: Software bugs or network issues can cause unexpected behavior
- **Always test with small amounts first**

## Display Features

### Live Dashboard

The bot includes a sophisticated display system with colored output and a live dashboard that shows real-time trading data:

#### Features:
- 🎨 **Colored Output**: Buy/sell orders, success/error messages in distinct colors
- 📊 **Live Dashboard**: Real-time updates of balances, orders, and statistics
- 💰 **Wallet Assets**: Complete portfolio view of all held assets per exchange
- 📈 **Order Monitoring**: Open orders count and total value
- 📉 **Session Statistics**: Win rate, P&L, trades per exchange
- 🔄 **Automatic Updates**: Dashboard refreshes every 5 seconds

#### Display Modes:

**1. Live Dashboard Mode (Recommended)**
- Requires `rich` library (automatically installed)
- Shows a formatted dashboard with tables and panels
- Real-time updates without cluttering the console
- Color-coded metrics (green for profit, red for loss)

**2. Basic Mode (Fallback)**
- Uses `colorama` for colored text
- Simpler output format
- Works on all terminals

#### Environment Variables:

You can control display features via environment variables in your `.env` file:

```bash
# Enable/disable colored output
ENABLE_COLOR_OUTPUT=True

# Enable/disable live dashboard
ENABLE_LIVE_DASHBOARD=True

# Enable/disable margin trading (Kraken only - HIGH RISK)
MARGIN_TRADING_ENABLED=False

# Set leverage for margin orders (default: 2.0)
DEFAULT_LEVERAGE=2.0
```

#### Requirements for Full Display Features:

```bash
# Install display libraries (included in requirements.txt)
pip install rich colorama
```

#### Dashboard Information:

The live dashboard displays:

**Left Panel:**
- Exchange connection status (🟢 connected, 🔴 error)
- USDT balance per exchange
- Number of open orders
- Total value of open orders

**Right Panel:**
- Total trades (buy/sell)
- Win rate percentage (color-coded)
- Total profit/loss (color-coded)
- Per-exchange statistics
- Total fees paid

**Footer:**
- List of trading pairs currently being monitored
- Last update timestamp

#### Colored Messages:

- 🟢 **Green**: Successful operations, profitable trades, buy orders
- 🔴 **Red**: Errors, losses, sell orders
- 🟡 **Yellow**: Warnings, neutral information
- 🔵 **Blue**: Informational messages
- ⚫ **Gray/Dim**: Debug messages

## Usage

### Running the Bot

```bash
python main.py
```

The bot will:
1. Validate API credentials
2. Check account balance
3. Identify sub-1-cent USDT trading pairs
4. Execute trading cycles every 60 seconds
5. Record all trades and analyze performance

### Monitoring

- **Logs**: Check `trade_logs/trading_bot.log` for detailed operation logs
- **Trades**: Review `trade_logs/trades.txt` for complete trade history
- **Console Output**: Real-time status updates during operation

## Trading Strategy

### Core Algorithm

1. **Token Selection**: Identifies tokens priced below $0.01
2. **ML Prediction**: Uses machine learning model to predict trade success probability
3. **Liquidity Check**: Ensures sufficient order book depth
4. **Profitability Analysis**: ML-enhanced evaluation of potential profit after fees
5. **Dynamic Pricing**: Calculates optimal entry/exit prices using market data
6. **Position Sizing**: Risk-managed trade sizes (max 2% of balance per trade)
7. **Order Management**: Places limit orders and monitors execution

### Machine Learning System

The bot includes a sophisticated ML system that learns from historical trading data:

- **Features Used**:
  - Price and volume data
  - Time-based patterns (hour of day, day of week)
  - Fee calculations
  - Market volatility and trends
  - Profit potential analysis

- **Model Type**: Random Forest Classifier optimized for small datasets
- **Training Trigger**: Automatically trains when 20+ trades are recorded
- **Prediction Confidence**: Requires 60%+ confidence for trade decisions
- **Fallback Strategy**: Uses traditional analysis when ML is unavailable
- **Enable/Disable**: Controlled by `ML_ENABLED` flag in `config.py`

### Price-Based Strategy Adjustments

The bot automatically adjusts its strategy based on token price ranges:

#### Low-Priced Tokens ($0.00 - $0.05)
- **Risk Level**: Highest (risk multiplier: 1.0)
- **Position Sizing**: Full allocated amounts
- **Profit Margin**: 1.5% (higher to account for volatility)
- **Volume Requirements**: $500k+ daily volume
- **Spread Tolerance**: Up to 8%
- **Use Case**: Microtrading, high-frequency scalping

#### Medium-Priced Tokens ($0.05 - $0.15)
- **Risk Level**: Medium (risk multiplier: 0.7)
- **Position Sizing**: 70% of allocated amounts
- **Profit Margin**: 1.0%
- **Volume Requirements**: $200k+ daily volume
- **Spread Tolerance**: Up to 5%
- **Use Case**: Balanced trading with moderate risk

#### High-Priced Tokens ($0.15+)
- **Risk Level**: Lowest (risk multiplier: 0.4)
- **Position Sizing**: 40% of allocated amounts
- **Profit Margin**: 0.7% (lower due to better liquidity)
- **Volume Requirements**: $100k+ daily volume
- **Spread Tolerance**: Up to 3%
- **Use Case**: Conservative trading with larger positions

### Risk Management

- Maximum 20% of account balance allocated to open orders
- Individual trades limited to 10% of allocated balance
- Respects minimum order sizes and trading fees
- ML-enhanced risk assessment
- Avoids overtrading through rate limiting

## File Structure

```
crypto_microbot/
├── main.py              # Main trading bot logic
├── display.py           # Display and dashboard module
├── trade_analyzer_ml.py # Machine learning module
├── test_trading_bot.py  # Unit tests for main bot
├── test_ml_system.py    # ML system tests
├── requirements.txt     # Python dependencies
├── config.py           # Configuration settings
├── run_bot.sh          # Deployment script
├── .env                # API credentials (create this file)
├── trade_logs/         # Trade logs directory
│   ├── trades.txt          # Trade history (generated)
│   ├── recorded_orders.txt # Order tracking (generated)
│   ├── trading_bot.log     # Operation logs (generated)
│   ├── open_positions.txt  # Current positions (generated)
│   └── sessions/           # Session summaries (generated)
├── trade_model.pkl     # ML model (generated)
├── scaler.pkl          # ML feature scaler (generated)
├── README.md           # This documentation
├── microtrading_strategies.md  # Strategy documentation
└── todo.md             # Development roadmap
```

## Testing

Run the unit tests to validate functionality:

```bash
# Test the main trading bot
python -m pytest test_trading_bot.py -v

# Test the ML system specifically
python test_ml_system.py

# Run all tests
python -m pytest test_trading_bot.py -v && python test_ml_system.py
```

## Safety Features

- **API Validation**: Ensures credentials are properly configured
- **Balance Checks**: Validates sufficient funds before trading
- **Error Handling**: Comprehensive exception handling and logging
- **Rate Limiting**: Built-in delays to respect API limits
- **Order Validation**: Verifies orders before submission

## Troubleshooting

### Common Issues

1. **"Missing Kraken API credentials"**
   - Ensure `.env` file exists with correct API key and secret
   - Verify API key has trading permissions

2. **"No USDT balance found"**
   - Ensure your Kraken account has USDT funds
   - Check API key permissions include balance viewing

3. **"Could not get ticker information"**
   - Check internet connection
   - Verify API credentials are correct
   - Ensure Kraken API is operational

4. **No sub-cent tokens found**
   - This is normal - sub-cent tokens are rare
   - The bot will continue monitoring for opportunities

### Logs and Debugging

- Check `trade_logs/trading_bot.log` for detailed error information
- Review `trade_logs/trades.txt` for trade execution details
- Enable debug logging by modifying the logging level in `main.py`

## Performance Analysis

The bot records all trades with the following metrics:
- Entry/exit prices
- Trade volume and value
- Fees paid
- Profit/loss calculation
- Win rate analysis

Use the built-in learning system to analyze performance and adjust strategies.

## Security Notes

- Never share your API credentials
- Use read-only API keys for testing
- Monitor account activity regularly
- Keep backup of trade records
- Test with small amounts first

## Development

### Adding New Features

1. Implement new functions in `main.py`
2. Add corresponding unit tests in `test_trading_bot.py`
3. Update documentation in `README.md`
4. Test thoroughly before production use

### Strategy Customization

The bot's trading logic can be customized by modifying:
- `simple_trading_strategy()` - Core trading logic
- `calculate_dynamic_buy_price()` - Entry price calculation
- `is_profitable_opportunity()` - Profitability checks
- `train_bot()` - Learning algorithm

## Legal Disclaimer

This software is for educational and research purposes only. Cryptocurrency trading involves significant risk of loss. The authors are not responsible for any financial losses incurred through the use of this software. Always trade with caution and never risk more than you can afford to lose.

## License

This project is provided as-is for educational purposes. See individual file headers for licensing information.
