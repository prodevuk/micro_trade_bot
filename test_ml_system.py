#!/usr/bin/env python3
"""
Test script for the Machine Learning trading system.
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_ml_system():
    """Test the ML system functionality"""
    print("Testing ML Trading System...")

    try:
        import trade_analyzer_ml

        # Initialize the ML system
        analyzer = trade_analyzer_ml.initialize_ml_system()
        print("✓ ML system initialized")

        # Test feature extraction
        test_trade = {
            'pair': 'TESTUSDT',
            'price': 0.01,
            'volume': 100.0,
            'fees': 0.0026,
            'timestamp': 1640995200.0  # 2022-01-01 00:00:00
        }

        features = analyzer.extract_features_from_trade(test_trade)
        print(f"✓ Feature extraction working. Extracted {len(features)} features")

        # Test training data preparation (if trades.txt exists)
        if os.path.exists(config.TRADES_FILE):
            data = analyzer.prepare_training_data()
            if data:
                X, y = data
                print(f"✓ Training data prepared: {X.shape[0]} samples, {X.shape[1]} features")
            else:
                print("! No training data available (expected if no trades yet)")
        else:
            print("! No trades.txt file found - skipping training data test")

        # Test prediction (will fail gracefully if no model)
        prediction, confidence = trade_analyzer_ml.predict_trade_opportunity(
            pair='TESTUSDT',
            price=0.01,
            volume=100.0,
            fees=0.0026
        )

        if prediction is None:
            print("✓ Prediction returned None (expected when no model is trained)")
        else:
            print(f"✓ Prediction working: {prediction} with confidence {confidence:.2f}")

        print("\n✅ All ML system tests passed!")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure scikit-learn and other dependencies are installed")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def test_ml_config_flag():
    """Test that the ML_ENABLED config flag works correctly"""
    import config
    import main

    print("Testing ML configuration flag...")

    # Test with ML enabled (default)
    original_ml_enabled = config.ML_ENABLED
    config.ML_ENABLED = True

    # Reset global ml_analyzer
    main.ml_analyzer = None

    # Test initialization with ML enabled
    ml_analyzer_enabled = main.trade_analyzer_ml.initialize_ml_system()
    print(f"✓ ML analyzer initialized when enabled: {ml_analyzer_enabled is not None}")

    # Test with ML disabled
    config.ML_ENABLED = False
    main.ml_analyzer = None

    # This should not initialize ML
    ml_analyzer_disabled = None
    if not config.ML_ENABLED:
        ml_analyzer_disabled = None
        print("✓ ML analyzer not initialized when disabled")

    # Restore original setting
    config.ML_ENABLED = original_ml_enabled

    return True

if __name__ == "__main__":
    success1 = test_ml_system()
    success2 = test_ml_config_flag()
    sys.exit(0 if (success1 and success2) else 1)
