#!/bin/bash

# Kraken Microtrading Bot Launcher
# This script sets up the environment and runs the trading bot

echo "=== Kraken Microtrading Bot Launcher ==="
echo

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    echo "Please create a .env file with your Kraken API credentials:"
    echo "KRAKEN_API_KEY=your_api_key_here"
    echo "KRAKEN_API_SECRET=your_api_secret_here"
    echo
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Setting up virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Run tests first
echo "Running tests..."
python -m pytest test_trading_bot.py -v
if [ $? -ne 0 ]; then
    echo "ERROR: Tests failed! Please fix issues before running the bot."
    exit 1
fi

echo
echo "=== Starting Trading Bot ==="
echo "Press Ctrl+C to stop the bot gracefully."
echo "Check trading_bot.log for detailed logs."
echo

# Run the bot
python bot.py
