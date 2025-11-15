#!/usr/bin/env python3
"""
Machine Learning Module for Kraken Trading Bot
Provides intelligent trade analysis and prediction capabilities.
"""

import os
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report
import joblib
import logging
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class TradeAnalyzerML:
    """Machine Learning analyzer for trading decisions"""

    def __init__(self, model_path="trade_model.pkl", scaler_path="scaler.pkl"):
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.model = None
        self.scaler = None
        self.is_trained = False
        self.feature_columns = [
            'price', 'volume', 'fees', 'hour_of_day', 'day_of_week',
            'price_volatility', 'volume_trend', 'profit_potential'
        ]

    def load_model(self):
        """Load trained model and scaler if they exist"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                self.is_trained = True
                logger.info("Successfully loaded trained ML model")
                return True
        except Exception as e:
            logger.warning(f"Could not load ML model: {e}")

        return False

    def save_model(self):
        """Save trained model and scaler"""
        try:
            if self.model and self.scaler:
                joblib.dump(self.model, self.model_path)
                joblib.dump(self.scaler, self.scaler_path)
                logger.info("Successfully saved ML model")
                return True
        except Exception as e:
            logger.error(f"Could not save ML model: {e}")

        return False

    def extract_features_from_trade(self, trade_data, market_data=None):
        """Extract features from trade data for ML prediction"""
        features = {}

        # Basic trade features
        features['price'] = float(trade_data.get('price', 0))
        features['volume'] = float(trade_data.get('volume', 0))
        features['fees'] = float(trade_data.get('fees', 0))

        # Time-based features
        timestamp = trade_data.get('timestamp', '')
        if timestamp:
            try:
                dt = datetime.fromtimestamp(float(timestamp))
                features['hour_of_day'] = dt.hour
                features['day_of_week'] = dt.weekday()
            except:
                features['hour_of_day'] = datetime.now().hour
                features['day_of_week'] = datetime.now().weekday()
        else:
            features['hour_of_day'] = datetime.now().hour
            features['day_of_week'] = datetime.now().weekday()

        # Market-based features (if available)
        if market_data:
            # Price volatility (based on recent price movements)
            prices = market_data.get('recent_prices', [])
            if len(prices) > 1:
                features['price_volatility'] = np.std(prices) / np.mean(prices) if np.mean(prices) > 0 else 0
            else:
                features['price_volatility'] = 0.01  # Default small volatility

            # Volume trend
            volumes = market_data.get('recent_volumes', [])
            if len(volumes) > 1:
                features['volume_trend'] = (volumes[-1] - volumes[0]) / volumes[0] if volumes[0] > 0 else 0
            else:
                features['volume_trend'] = 0
        else:
            features['price_volatility'] = 0.01
            features['volume_trend'] = 0

        # Profit potential estimation
        # This is a simplified calculation - in reality you'd use more sophisticated analysis
        estimated_sell_price = features['price'] * 1.005  # Assume 0.5% target
        estimated_fees = features['price'] * features['volume'] * 0.005  # Estimate fees
        features['profit_potential'] = (estimated_sell_price * features['volume']) - (features['price'] * features['volume']) - estimated_fees

        return features

    def prepare_training_data(self, trades_file=None, min_samples=10):
        """Prepare training data from historical trades"""
        if not os.path.exists(trades_file):
            logger.warning(f"Trades file {trades_file} not found")
            return None

        trades = []
        try:
            with open(trades_file, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            trade = eval(line.strip())
                            trades.append(trade)
                        except:
                            continue
        except Exception as e:
            logger.error(f"Error reading trades file: {e}")
            return None

        if len(trades) < min_samples:
            logger.info(f"Not enough trades for training: {len(trades)} < {min_samples}")
            return None

        logger.info(f"Preparing training data from {len(trades)} trades")

        # Create features dataframe
        features_list = []
        labels = []

        for trade in trades:
            features = self.extract_features_from_trade(trade)

            # Label: 1 if profitable, 0 if not
            # For buy trades, we consider them successful if they were followed by sells
            # For now, we'll use a simple heuristic based on the profit field if available
            profit = trade.get('profit', 0)
            label = 1 if profit > 0 else 0
            labels.append(label)
            features_list.append(features)

        if not features_list:
            return None

        df = pd.DataFrame(features_list)
        df = df.fillna(0)  # Handle any NaN values

        # Ensure all feature columns exist
        for col in self.feature_columns:
            if col not in df.columns:
                df[col] = 0

        X = df[self.feature_columns].values
        y = np.array(labels)

        return X, y

    def train_model(self, test_size=0.2, random_state=42):
        """Train the ML model using historical trade data"""
        logger.info("Starting ML model training...")

        # Prepare training data
        import config
        data = self.prepare_training_data(config.TRADES_FILE)
        if data is None:
            logger.warning("No training data available")
            return False

        X, y = data

        if len(X) < 10:
            logger.warning("Insufficient data for training")
            return False

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y if len(np.unique(y)) > 1 else None
        )

        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Try Random Forest first (good for small datasets)
        self.model = RandomForestClassifier(
            n_estimators=50,
            max_depth=5,
            random_state=random_state,
            class_weight='balanced'
        )

        try:
            self.model.fit(X_train_scaled, y_train)

            # Evaluate
            y_pred = self.model.predict(X_test_scaled)
            accuracy = accuracy_score(y_test, y_pred)

            logger.info(".2%")
            logger.info(f"Classification Report:\n{classification_report(y_test, y_pred)}")

            # Feature importance
            feature_importance = dict(zip(self.feature_columns, self.model.feature_importances_))
            logger.info(f"Feature Importance: {json.dumps(feature_importance, indent=2)}")

            self.is_trained = True

            # Save the model
            self.save_model()

            return True

        except Exception as e:
            logger.error(f"Error training model: {e}")
            return False

    def predict_trade_success(self, trade_data, market_data=None, threshold=0.5):
        """Predict if a trade will be successful"""
        if not self.is_trained:
            logger.debug("ML model not trained, cannot make predictions")
            return None

        try:
            # Extract features
            features = self.extract_features_from_trade(trade_data, market_data)
            features_df = pd.DataFrame([features])

            # Ensure all columns exist
            for col in self.feature_columns:
                if col not in features_df.columns:
                    features_df[col] = 0

            # Scale features
            X = self.scaler.transform(features_df[self.feature_columns].values)

            # Make prediction
            prediction_proba = self.model.predict_proba(X)[0]
            prediction = self.model.predict(X)[0]

            confidence = prediction_proba[1] if prediction == 1 else prediction_proba[0]

            logger.debug(".2f")

            # Only return positive prediction if confidence is above threshold
            if prediction == 1 and confidence >= threshold:
                return True, confidence
            elif prediction == 0 and confidence >= threshold:
                return False, confidence
            else:
                return None, confidence  # Uncertain

        except Exception as e:
            logger.error(f"Error making prediction: {e}")
            return None, 0.0

    def get_market_data_for_prediction(self, pair, current_price):
        """Gather market data needed for predictions"""
        # This would ideally fetch real market data
        # For now, return mock data
        return {
            'recent_prices': [current_price * (1 + np.random.normal(0, 0.01)) for _ in range(10)],
            'recent_volumes': [1000 * (1 + np.random.normal(0, 0.2)) for _ in range(10)]
        }

    def update_model_with_new_trade(self, trade_data):
        """Update model with new trade data (online learning)"""
        # For now, we'll retrain periodically rather than true online learning
        # This is simpler and works well for small datasets
        logger.info("New trade recorded - model will be retrained on next cycle")
        # In a production system, you might want to implement incremental learning

# Global ML analyzer instance
ml_analyzer = TradeAnalyzerML()

def initialize_ml_system():
    """Initialize the ML system"""
    global ml_analyzer

    # Try to load existing model
    if not ml_analyzer.load_model():
        logger.info("No existing ML model found, will train new model when sufficient data is available")

    return ml_analyzer

def predict_trade_opportunity(pair, price, volume, fees):
    """Predict if a trade opportunity is likely to be profitable"""
    global ml_analyzer

    if not ml_analyzer.is_trained:
        return None, "Model not trained"

    trade_data = {
        'pair': pair,
        'price': price,
        'volume': volume,
        'fees': fees,
        'timestamp': datetime.now().timestamp()
    }

    market_data = ml_analyzer.get_market_data_for_prediction(pair, price)

    prediction, confidence = ml_analyzer.predict_trade_success(trade_data, market_data)

    return prediction, confidence

def train_ml_model():
    """Train the ML model with available data"""
    global ml_analyzer

    success = ml_analyzer.train_model()
    return success

if __name__ == "__main__":
    # Test the ML system
    print("Testing ML Trade Analyzer...")

    # Initialize
    analyzer = initialize_ml_system()

    # Try to train
    trained = train_ml_model()
    if trained:
        print("Model trained successfully!")
    else:
        print("Model training failed - likely insufficient data")

    # Test prediction
    test_trade = {
        'pair': 'TESTUSDT',
        'price': 0.01,
        'volume': 100.0,
        'fees': 0.0026,
        'timestamp': datetime.now().timestamp()
    }

    prediction, confidence = analyzer.predict_trade_success(test_trade)
    if prediction is not None:
        print(".2f")
    else:
        print("No prediction available (model not trained or uncertain)")
