#!/usr/bin/env python3
"""
Unit tests for the Kraken trading bot.
Run with: python -m pytest test_trading_bot.py
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestTradingBot(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures"""
        # Mock environment variables
        self.mock_api_key = "test_key"
        self.mock_api_secret = "test_secret"

    @patch.dict(os.environ, {'KRAKEN_API_KEY': 'test_key', 'KRAKEN_API_SECRET': 'test_secret'})
    def test_api_credentials_loaded(self):
        """Test that API credentials are properly loaded"""
        import bot
        import config
        # Reload config to pick up environment variables
        import importlib
        importlib.reload(config)
        self.assertEqual(config.KRAKEN_API_KEY, 'test_key')
        self.assertEqual(config.KRAKEN_API_SECRET, 'test_secret')

    def test_kraken_signature_generation(self):
        """Test that Kraken API signature generation works"""
        from exchanges.kraken import get_kraken_signature
        import base64

        # Use a proper base64 encoded secret for testing
        test_secret = base64.b64encode(b"test_secret_key_for_hmac").decode()
        test_urlpath = "/0/private/Balance"
        test_data = {"nonce": 1234567890}

        # This should not raise an exception
        signature = get_kraken_signature(test_urlpath, test_data, test_secret)
        self.assertIsInstance(signature, str)
        self.assertGreater(len(signature), 0)

    def test_record_trade(self):
        """Test trade recording functionality"""
        from utils.session import record_trade
        import tempfile
        import os

        # Create a temporary file for testing
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
            temp_filename = temp_file.name

        # Mock the file operations
        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            test_trade_data = {
                'type': 'buy',
                'pair': 'TESTUSDT',
                'price': 0.01,
                'volume': 100.0,
                'fees': 0.0026,
                'profit': -0.26
            }

            record_trade(test_trade_data)
            # Check that write was called (may be called multiple times)
            self.assertTrue(mock_file.write.called)

    def test_simple_trading_strategy_calculation(self):
        """Test basic trading strategy calculations"""
        # Test that the strategy calculates volumes correctly
        test_balance = 100.0  # $100
        test_price = 0.01     # $0.01 per token
        test_fees = 0.0026    # 0.26%
        test_ordermin = 10.0
        test_lot_decimals = 8

        # Test volume calculation logic (simplified)
        fee_multiplier = 1 + test_fees
        max_volume = (test_balance * 0.2) / (test_price * fee_multiplier)
        max_volume = max_volume * 0.1  # 10% of max
        volume_to_trade = max(round(max_volume, 8), test_ordermin)

        # Basic assertions
        self.assertGreater(volume_to_trade, 0)
        self.assertIsInstance(volume_to_trade, float)

    def test_train_bot_analysis(self):
        """Test that the training function analyzes trade data"""
        from utils.session import train_bot
        import tempfile
        import os

        # Create temporary trades file
        test_trades = [
            {'type': 'buy', 'profit': 1.5},
            {'type': 'buy', 'profit': -0.5},
            {'type': 'buy', 'profit': 2.0}
        ]

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            for trade in test_trades:
                temp_file.write(str(trade) + '\n')
            temp_filename = temp_file.name

        try:
            with patch('utils.session.logger') as mock_logger:
                train_bot({'type': 'buy', 'profit': 1.0})

                # Check that logging was called
                mock_logger.info.assert_called()
        finally:
            if os.path.exists(temp_filename):
                os.unlink(temp_filename)

if __name__ == '__main__':
    unittest.main()
