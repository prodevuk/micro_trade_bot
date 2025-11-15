# Display Features Guide

## Overview

The trading bot now includes a sophisticated display system with:
- 🎨 Color-coded console output
- 📊 Live dashboard with real-time updates
- 💰 Balance and order tracking
- 📈 Session statistics and metrics

## Installation

Install the required libraries (already in requirements.txt):

```bash
pip install rich colorama
```

Or install all dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

### Via config.py

```python
# Display Settings in config.py
ENABLE_COLOR_OUTPUT = True        # Enable colored console output
ENABLE_LIVE_DASHBOARD = True      # Enable live dashboard view
DASHBOARD_REFRESH_INTERVAL = 5    # Seconds between dashboard updates
DASHBOARD_POSITION = "top"        # Dashboard position: "top" or "bottom"
```

### Via Environment Variables

Add to your `.env` file:

```bash
# Enable/disable colored output
ENABLE_COLOR_OUTPUT=True

# Enable/disable live dashboard
ENABLE_LIVE_DASHBOARD=True
```

## Features

### 1. Live Dashboard

When enabled, the bot displays a real-time dashboard that shows:

**Left Panel - Balances & Orders:**
- Exchange connection status (🟢 connected, 🔴 error, 🟡 pending)
- USDT balance per exchange
- Number of open orders
- Total value of open orders

**Right Panel - Session Statistics:**
- Total trades (buy/sell breakdown)
- Win rate percentage (color-coded: green ≥70%, yellow ≥50%, red <50%)
- Total profit/loss (green = profit, red = loss)
- Per-exchange statistics
- Total fees paid

**Footer:**
- List of trading pairs currently being monitored
- Last update timestamp

### 2. Colored Console Output

All messages are color-coded for easy identification:

- 🟢 **Green (Success)**: 
  - Successful operations
  - Profitable trades
  - Buy orders placed
  - Balance retrieved successfully

- 🔴 **Red (Errors)**:
  - Errors and failures
  - Sell orders placed
  - Connection issues
  - Failed operations

- 🟡 **Yellow (Warnings)**:
  - Warning messages
  - No tokens found
  - Balance issues

- 🔵 **Blue (Info)**:
  - Informational messages
  - Status updates
  - General information

- ⚫ **Gray/Dim (Debug)**:
  - Debug messages
  - Detailed logs

### 3. Trade Messages

Buy and sell orders are displayed with special formatting:

```
📈 BUY 1000 KASUSDT @ $0.000123 on KRAKEN = $0.12
📉 SELL 1000 KASUSDT @ $0.000135 on KRAKEN (Expected profit: $0.012)
```

## Display Modes

### Mode 1: Live Dashboard (Recommended)

**Requirements:** `rich` library

**Features:**
- Formatted tables and panels
- Real-time updates every 5 seconds
- No console clutter
- Color-coded metrics
- Professional appearance

**When to use:** Best for monitoring the bot during active trading

### Mode 2: Basic Mode (Fallback)

**Requirements:** `colorama` library (or none)

**Features:**
- Colored text output
- Simple format
- Works on all terminals
- Lower resource usage

**When to use:** If `rich` is not available or for simple monitoring

## Usage Examples

### Example 1: Full Features Enabled

```python
# config.py
ENABLE_COLOR_OUTPUT = True
ENABLE_LIVE_DASHBOARD = True
DASHBOARD_REFRESH_INTERVAL = 5

# Result: Full live dashboard with colors
```

### Example 2: Colors Only (No Dashboard)

```python
# config.py
ENABLE_COLOR_OUTPUT = True
ENABLE_LIVE_DASHBOARD = False

# Result: Colored messages without live dashboard
```

### Example 3: Basic Mode (No Colors)

```python
# config.py
ENABLE_COLOR_OUTPUT = False
ENABLE_LIVE_DASHBOARD = False

# Result: Plain text output (original behavior)
```

## API Integration

The display system automatically updates when the bot:
- Retrieves account balances
- Gets open orders
- Places new orders
- Records completed trades
- Updates session metrics

### Manual Updates (Advanced)

You can manually update the dashboard in your code:

```python
from display import get_dashboard, ColorPrint

# Get the dashboard instance
dashboard = get_dashboard()

# Update balance
dashboard.update_balances('kraken', {'USDT': '100.50', 'BTC': '0.01'})

# Update open orders
dashboard.update_open_orders('kraken', orders_response)

# Update session metrics
dashboard.update_session_metrics(session_metrics)

# Update exchange status
dashboard.update_exchange_status('kraken', 'connected')

# Update current pairs being monitored
dashboard.update_current_pairs(['KASUSDT', 'SHIBUSDT', 'ALGOUSDT'])

# Print colored messages
ColorPrint.success("Operation completed successfully!")
ColorPrint.error("An error occurred")
ColorPrint.warning("Warning: Low balance")
ColorPrint.info("Information message")
ColorPrint.trade("BUY order placed", trade_type="buy")
ColorPrint.debug("Debug message")
```

## Troubleshooting

### Dashboard not appearing

1. Check if `rich` is installed:
   ```bash
   pip install rich
   ```

2. Verify settings in config.py:
   ```python
   ENABLE_LIVE_DASHBOARD = True
   ```

3. Check terminal compatibility (some terminals don't support rich formatting)

### Colors not showing

1. Check if `colorama` is installed:
   ```bash
   pip install colorama
   ```

2. Verify settings:
   ```python
   ENABLE_COLOR_OUTPUT = True
   ```

3. Some terminals may not support ANSI colors

### Dashboard updates slowly

1. Increase refresh interval in config.py:
   ```python
   DASHBOARD_REFRESH_INTERVAL = 10  # Update every 10 seconds instead of 5
   ```

2. Check system resources (CPU/memory)

### Terminal shows garbled text

1. Try disabling live dashboard:
   ```python
   ENABLE_LIVE_DASHBOARD = False
   ```

2. Use basic mode:
   ```python
   ENABLE_COLOR_OUTPUT = False
   ENABLE_LIVE_DASHBOARD = False
   ```

## Performance Impact

The display system is designed to be lightweight:

- **Live Dashboard:** Updates in a separate thread
- **Memory Usage:** Minimal (only stores last known values)
- **CPU Usage:** Negligible (<1% on most systems)
- **Network:** No additional API calls (uses cached data)

## Customization

You can customize the display by modifying `display.py`:

### Change Dashboard Layout

Edit the `_generate_rich_dashboard()` method in `TradingDashboard` class.

### Add New Metrics

1. Add data fields to `self.data` in `__init__()`
2. Create update method (e.g., `update_custom_metric()`)
3. Add display logic in `_create_stats_table()`

### Change Colors

Modify the color strings in `ColorPrint` class methods:
- `"green"` for success
- `"red"` for errors
- `"yellow"` for warnings
- `"blue"` for info

## Best Practices

1. **Always enable colors** - Makes monitoring much easier
2. **Use live dashboard for active monitoring** - Best real-time view
3. **Disable dashboard for logging** - If piping output to files
4. **Check dashboard regularly** - Monitor balances and orders
5. **Watch for red indicators** - Sign of errors or losses

## Module Structure

The display module (`display.py`) contains:

- `TradingDashboard` class: Main dashboard management
- `ColorPrint` class: Colored message utilities
- `get_dashboard()`: Get global dashboard instance
- `init_display()`: Initialize display system
- `shutdown_display()`: Clean shutdown

## Integration Points

The display is integrated at key points in main.py:

1. **Startup:** Initialize display system
2. **Balance retrieval:** Update balance display
3. **Order management:** Update open orders
4. **Trade execution:** Show colored trade messages
5. **Session metrics:** Update statistics
6. **Shutdown:** Clean display shutdown

## Future Enhancements

Possible future improvements:
- Export dashboard to HTML
- Historical charts and graphs
- Alert notifications
- Web-based dashboard
- Mobile app integration

## Support

If you encounter issues with the display system:

1. Check this guide
2. Review README.md
3. Check terminal compatibility
4. Verify library installation
5. Test with basic mode first

## Credits

Built with:
- [Rich](https://github.com/Textualize/rich) - Advanced terminal formatting
- [Colorama](https://github.com/tartley/colorama) - Cross-platform colored terminal text

