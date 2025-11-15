"""
Display module for trading bot - handles colored output and live dashboard
"""

import time
import threading
from datetime import datetime
from typing import Dict, List, Optional
import config

# Try to import rich for advanced display, fallback to colorama for basic colors
try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Rich library not available. Install with: pip install rich")

try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    # Fallback: no colors
    class Fore:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    class Back:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = BLACK = RESET = ""
    class Style:
        BRIGHT = DIM = NORMAL = RESET_ALL = ""


class TradingDashboard:
    """
    Manages live trading dashboard display with color formatting
    """
    
    def __init__(self, enable_colors=True, enable_live=True):
        self.enable_colors = enable_colors and config.ENABLE_COLOR_OUTPUT
        self.enable_live = enable_live and config.ENABLE_LIVE_DASHBOARD and RICH_AVAILABLE
        
        # Console for rich output
        self.console = Console() if RICH_AVAILABLE else None
        
        # Tracked data (last known values from API calls)
        self.data = {
            'balances': {},
            'open_orders': {},
            'recent_trades': [],
            'session_metrics': {},
            'last_update': {},
            'exchange_status': {},
            'current_pairs': []
        }
        
        # Thread safety
        self.lock = threading.Lock()
        
        # Live display
        self.live_display = None
        self.live_thread = None
        self.running = False
    
    def update_balances(self, exchange: str, balance_data: Dict):
        """Update balance data from API response"""
        with self.lock:
            if 'balances' not in self.data:
                self.data['balances'] = {}
            self.data['balances'][exchange] = balance_data
            self.data['last_update']['balances'] = time.time()
    
    def update_open_orders(self, exchange: str, orders_data: Dict):
        """Update open orders from API response"""
        with self.lock:
            if 'open_orders' not in self.data:
                self.data['open_orders'] = {}
            
            # Count orders
            order_count = 0
            total_value = 0.0
            
            if orders_data and 'open' in orders_data:
                order_count = len(orders_data['open'])
                for order_id, order_info in orders_data['open'].items():
                    try:
                        # Get price from descr section (not top-level price which can be 0)
                        price = float(order_info.get('descr', {}).get('price', 0))
                        volume = float(order_info.get('vol', 0))
                        if price > 0 and volume > 0:
                            total_value += price * volume
                    except (ValueError, TypeError):
                        pass
            
            self.data['open_orders'][exchange] = {
                'count': order_count,
                'total_value': total_value,
                'raw_data': orders_data
            }
            self.data['last_update']['open_orders'] = time.time()
    
    def update_session_metrics(self, metrics: Dict):
        """Update session metrics"""
        with self.lock:
            self.data['session_metrics'] = metrics.copy()
            self.data['last_update']['session_metrics'] = time.time()
    
    def add_trade(self, trade_data: Dict):
        """Add a recent trade to the display"""
        with self.lock:
            if 'recent_trades' not in self.data:
                self.data['recent_trades'] = []
            self.data['recent_trades'].insert(0, trade_data)
            # Keep only last 10 trades
            self.data['recent_trades'] = self.data['recent_trades'][:10]
    
    def update_exchange_status(self, exchange: str, status: str):
        """Update exchange connection status"""
        with self.lock:
            if 'exchange_status' not in self.data:
                self.data['exchange_status'] = {}
            self.data['exchange_status'][exchange] = {
                'status': status,
                'timestamp': time.time()
            }
    
    def update_current_pairs(self, pairs: List[str]):
        """Update list of pairs currently being monitored"""
        with self.lock:
            self.data['current_pairs'] = pairs[:20]  # Keep top 20
    
    def generate_dashboard(self) -> str:
        """Generate dashboard layout (rich or plain text)"""
        if not self.enable_live or not RICH_AVAILABLE:
            return self._generate_plain_dashboard()
        
        return self._generate_rich_dashboard()
    
    def _generate_rich_dashboard(self):
        """Generate rich formatted dashboard"""
        with self.lock:
            data = self.data.copy()
        
        # Create layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        # Header
        session_metrics = data.get('session_metrics', {})
        start_time = session_metrics.get('start_time', time.time())
        duration = time.time() - start_time
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        
        header_text = Text()
        header_text.append("🤖 Multi-Exchange Trading Bot", style="bold cyan")
        header_text.append(f" | Runtime: {hours}h {minutes}m", style="yellow")
        header_text.append(f" | Last Update: {datetime.now().strftime('%H:%M:%S')}", style="dim")
        
        layout["header"].update(Panel(header_text, box=box.ROUNDED))
        
        # Main content - split into 2 columns
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        # Left column: Balances & Orders
        left_content = self._create_balance_table(data)
        layout["main"]["left"].update(left_content)
        
        # Right column: Session Stats & Recent Trades
        right_content = self._create_stats_table(data)
        layout["main"]["right"].update(right_content)
        
        # Footer: Current pairs being monitored
        footer_text = Text()
        footer_text.append("Monitoring: ", style="bold")
        pairs = data.get('current_pairs', [])
        if pairs:
            footer_text.append(", ".join(pairs[:10]), style="cyan")
            if len(pairs) > 10:
                footer_text.append(f" +{len(pairs) - 10} more", style="dim")
        else:
            footer_text.append("No pairs", style="dim")
        
        layout["footer"].update(Panel(footer_text, box=box.ROUNDED))
        
        return layout
    
    def _create_balance_table(self, data: Dict):
        """Create balance and orders table with all wallet assets"""
        table = Table(title="💰 Wallet Assets & Orders", box=box.ROUNDED, show_header=True, header_style="bold magenta")
        table.add_column("Exchange", style="cyan", width=12)
        table.add_column("Asset", style="white", width=10)
        table.add_column("Balance", justify="right", style="green", width=15)
        table.add_column("Open Orders", justify="right", style="yellow", width=12)
        table.add_column("Order Value", justify="right", style="blue", width=15)

        balances = data.get('balances', {})
        open_orders = data.get('open_orders', {})
        exchange_status = data.get('exchange_status', {})

        for exchange in ['kraken', 'bitmart']:
            if exchange in balances or exchange in open_orders:
                # Balance data - show all non-zero assets
                balance_data = balances.get(exchange, {})
                non_zero_assets = [(asset, float(amount)) for asset, amount in balance_data.items()
                                 if float(amount) > 0.000001]  # Filter out dust

                # Orders info
                orders_info = open_orders.get(exchange, {})
                order_count = orders_info.get('count', 0)
                order_value = orders_info.get('total_value', 0)

                # Status
                status_info = exchange_status.get(exchange, {})
                status = status_info.get('status', 'unknown')
                status_icon = "🟢" if status == "connected" else "🔴" if status == "error" else "🟡"

                if non_zero_assets:
                    # Add first asset with exchange info and order data
                    first_asset, first_balance = non_zero_assets[0]
                    table.add_row(
                        f"{status_icon} {exchange.upper()}",
                        first_asset,
                        f"{first_balance:,.6f}",
                        str(order_count),
                        f"${order_value:,.2f}"
                    )

                    # Add remaining assets without duplicating exchange/order info
                    for asset, balance in non_zero_assets[1:]:
                        table.add_row(
                            "",  # Empty exchange column
                            asset,
                            f"{balance:,.6f}",
                            "",  # Empty orders columns
                            ""
                        )
                else:
                    # No assets, just show exchange with order info
                    table.add_row(
                        f"{status_icon} {exchange.upper()}",
                        "No assets",
                        "$0.00",
                        str(order_count),
                        f"${order_value:,.2f}"
                    )

        return Panel(table, box=box.ROUNDED)
    
    def _create_stats_table(self, data: Dict):
        """Create session statistics table"""
        metrics = data.get('session_metrics', {})
        
        table = Table(title="📊 Session Statistics", box=box.ROUNDED, show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", justify="right", style="white", width=20)
        
        # Calculate stats
        total_trades = metrics.get('total_trades', 0)
        buy_trades = metrics.get('buy_trades', 0)
        sell_trades = metrics.get('sell_trades', 0)
        total_profit = metrics.get('total_profit_loss', 0)
        winning_trades = metrics.get('winning_trades', 0)
        losing_trades = metrics.get('losing_trades', 0)
        total_fees = metrics.get('total_fees', 0)
        
        win_rate = (winning_trades / max(sell_trades, 1)) * 100
        
        # Color code profit/loss
        profit_color = "green" if total_profit > 0 else "red" if total_profit < 0 else "yellow"
        win_rate_color = "green" if win_rate >= 70 else "yellow" if win_rate >= 50 else "red"
        
        table.add_row("Total Trades", str(total_trades))
        table.add_row("Buy / Sell", f"{buy_trades} / {sell_trades}")
        table.add_row("Win Rate", Text(f"{win_rate:.1f}%", style=win_rate_color))
        table.add_row("Total P&L", Text(f"${total_profit:.4f}", style=profit_color))
        table.add_row("Total Fees", f"${total_fees:.4f}")
        table.add_row("Winning Trades", str(winning_trades), style="green")
        table.add_row("Losing Trades", str(losing_trades), style="red")
        
        # Per-exchange breakdown
        trades_per_exchange = metrics.get('trades_per_exchange', {})
        profit_per_exchange = metrics.get('profit_per_exchange', {})
        
        if trades_per_exchange:
            table.add_row("", "")  # Spacer
            for exchange, count in trades_per_exchange.items():
                if count > 0:
                    profit = profit_per_exchange.get(exchange, 0)
                    profit_style = "green" if profit > 0 else "red" if profit < 0 else "yellow"
                    table.add_row(
                        f"  {exchange.upper()}",
                        Text(f"{count} trades, ${profit:.4f}", style=profit_style)
                    )
        
        return Panel(table, box=box.ROUNDED)
    
    def _generate_plain_dashboard(self) -> str:
        """Generate plain text dashboard (fallback)"""
        with self.lock:
            data = self.data.copy()
        
        lines = []
        lines.append("=" * 80)
        lines.append("🤖 TRADING BOT DASHBOARD")
        lines.append("=" * 80)
        
        # Balances
        lines.append("\n💰 BALANCES & ORDERS:")
        balances = data.get('balances', {})
        open_orders = data.get('open_orders', {})
        
        for exchange in ['kraken', 'bitmart']:
            if exchange in balances or exchange in open_orders:
                balance_data = balances.get(exchange, {})
                usdt = float(balance_data.get('USDT', 0))
                
                orders_info = open_orders.get(exchange, {})
                order_count = orders_info.get('count', 0)
                order_value = orders_info.get('total_value', 0)
                
                lines.append(f"  {exchange.upper():10} | Balance: ${usdt:,.2f} | Orders: {order_count} (${order_value:,.2f})")
        
        # Session Stats
        lines.append("\n📊 SESSION STATISTICS:")
        metrics = data.get('session_metrics', {})
        
        total_trades = metrics.get('total_trades', 0)
        total_profit = metrics.get('total_profit_loss', 0)
        win_rate = (metrics.get('winning_trades', 0) / max(metrics.get('sell_trades', 1), 1)) * 100
        
        lines.append(f"  Total Trades: {total_trades}")
        lines.append(f"  Win Rate: {win_rate:.1f}%")
        lines.append(f"  Total P&L: ${total_profit:.4f}")
        
        # Current pairs
        pairs = data.get('current_pairs', [])
        if pairs:
            lines.append(f"\n📈 Monitoring {len(pairs)} pairs: {', '.join(pairs[:5])}")
            if len(pairs) > 5:
                lines.append(f"   +{len(pairs) - 5} more...")
        
        lines.append("\n" + "=" * 80)
        lines.append(f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def start_live_display(self):
        """Start the live dashboard in a separate thread"""
        if not self.enable_live or not RICH_AVAILABLE:
            return
        
        if self.running:
            return
        
        self.running = True
        self.live_thread = threading.Thread(target=self._live_display_loop, daemon=True)
        self.live_thread.start()
    
    def _live_display_loop(self):
        """Live display loop (runs in separate thread)"""
        try:
            with Live(self._generate_rich_dashboard(), console=self.console, refresh_per_second=1) as live:
                self.live_display = live
                while self.running:
                    time.sleep(config.DASHBOARD_REFRESH_INTERVAL)
                    live.update(self._generate_rich_dashboard())
        except Exception as e:
            print(f"Error in live display: {e}")
    
    def stop_live_display(self):
        """Stop the live dashboard"""
        self.running = False
        if self.live_thread:
            self.live_thread.join(timeout=2)
    
    def print_dashboard(self):
        """Print dashboard once (non-live mode)"""
        dashboard = self.generate_dashboard()
        if RICH_AVAILABLE and self.enable_colors:
            self.console.print(dashboard)
        else:
            print(dashboard)


# Colored print functions
class ColorPrint:
    """Utility class for colored console output"""
    
    @staticmethod
    def success(message: str):
        """Print success message in green"""
        if config.ENABLE_COLOR_OUTPUT:
            if RICH_AVAILABLE:
                Console().print(f"[green]✓[/green] {message}")
            elif COLORAMA_AVAILABLE:
                print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")
            else:
                print(f"✓ {message}")
        else:
            print(f"✓ {message}")
    
    @staticmethod
    def error(message: str):
        """Print error message in red"""
        if config.ENABLE_COLOR_OUTPUT:
            if RICH_AVAILABLE:
                Console().print(f"[red]✗[/red] {message}")
            elif COLORAMA_AVAILABLE:
                print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")
            else:
                print(f"✗ {message}")
        else:
            print(f"✗ {message}")
    
    @staticmethod
    def warning(message: str):
        """Print warning message in yellow"""
        if config.ENABLE_COLOR_OUTPUT:
            if RICH_AVAILABLE:
                Console().print(f"[yellow]⚠[/yellow] {message}")
            elif COLORAMA_AVAILABLE:
                print(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")
            else:
                print(f"⚠ {message}")
        else:
            print(f"⚠ {message}")
    
    @staticmethod
    def info(message: str):
        """Print info message in blue"""
        if config.ENABLE_COLOR_OUTPUT:
            if RICH_AVAILABLE:
                Console().print(f"[blue]ℹ[/blue] {message}")
            elif COLORAMA_AVAILABLE:
                print(f"{Fore.BLUE}ℹ {message}{Style.RESET_ALL}")
            else:
                print(f"ℹ {message}")
        else:
            print(f"ℹ {message}")
    
    @staticmethod
    def trade(message: str, trade_type: str = "buy"):
        """Print trade message with appropriate color"""
        icon = "📈" if trade_type == "buy" else "📉"
        color = "green" if trade_type == "buy" else "red"
        
        if config.ENABLE_COLOR_OUTPUT:
            if RICH_AVAILABLE:
                Console().print(f"[{color}]{icon}[/{color}] {message}")
            elif COLORAMA_AVAILABLE:
                color_code = Fore.GREEN if trade_type == "buy" else Fore.RED
                print(f"{color_code}{icon} {message}{Style.RESET_ALL}")
            else:
                print(f"{icon} {message}")
        else:
            print(f"{icon} {message}")
    
    @staticmethod
    def debug(message: str):
        """Print debug message in gray/dim"""
        if config.ENABLE_COLOR_OUTPUT:
            if RICH_AVAILABLE:
                Console().print(f"[dim]{message}[/dim]")
            elif COLORAMA_AVAILABLE:
                print(f"{Style.DIM}{message}{Style.RESET_ALL}")
            else:
                print(message)
        else:
            print(message)


# Global dashboard instance
_dashboard_instance: Optional[TradingDashboard] = None


def get_dashboard() -> TradingDashboard:
    """Get or create global dashboard instance"""
    global _dashboard_instance
    if _dashboard_instance is None:
        _dashboard_instance = TradingDashboard()
    return _dashboard_instance


def init_display():
    """Initialize display system"""
    dashboard = get_dashboard()
    if config.ENABLE_LIVE_DASHBOARD and RICH_AVAILABLE:
        ColorPrint.info("Live dashboard enabled. Starting...")
        dashboard.start_live_display()
    else:
        if not RICH_AVAILABLE:
            ColorPrint.warning("Rich library not available. Using basic display. Install with: pip install rich")
        ColorPrint.info("Using basic display mode")
    return dashboard


def shutdown_display():
    """Shutdown display system"""
    global _dashboard_instance
    if _dashboard_instance:
        _dashboard_instance.stop_live_display()


