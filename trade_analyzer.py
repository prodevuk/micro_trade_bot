import pandas as pd

def analyze_trades(trade_file=None):
    trades = []
    try:
        with open(trade_file, "r") as f:
            for line in f:
                try:
                    trade_data = eval(line.strip()) # Using eval for simplicity, but consider safer parsing for production
                    trades.append(trade_data)
                except Exception as e:
                    print(f"Error parsing trade data: {line.strip()} - {e}")
    except FileNotFoundError:
        print(f"Trade file {trade_file} not found. No trades to analyze.")
        return

    if not trades:
        print("No trades recorded yet.")
        return

    df = pd.DataFrame(trades)
    print("\n--- Trade Analysis ---")
    print(f"Total trades: {len(df)}")

    # Example analysis: Calculate total profit/loss (requires 'profit' field in trade_data)
    if 'profit' in df.columns:
        total_profit = df['profit'].sum()
        print(f"Total P&L: {total_profit:.8f}")

    # Example analysis: Most profitable pairs
    if 'pair' in df.columns and 'profit' in df.columns:
        profitable_pairs = df.groupby('pair')['profit'].sum().sort_values(ascending=False)
        print("\nMost profitable pairs:")
        print(profitable_pairs.head())

    # Example analysis: Average profit per trade
    if 'profit' in df.columns:
        avg_profit_per_trade = df['profit'].mean()
        print(f"\nAverage P&L per trade: {avg_profit_per_trade:.8f}")

    print("----------------------")

if __name__ == "__main__":
    analyze_trades()


