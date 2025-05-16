# Trading Parameters
PAIRS = ["XRPUSDT", "DOGEUSDT", "ADAUSDT", "SUIUSDT", "TRXUSDT", "BLURUSDT"]
TIMEFRAME = "15m"

# Telegram Configuration
TELEGRAM_BOT_TOKEN = "7981744692:AAEo4dmDLqrbIr0vUOCeQLnQFDHfaoTqcOw"  # Replace with your actual token
TELEGRAM_CHAT_ID = "-1002655134174"               # Replace with your chat ID

# Signal Parameters (for display in notifications)
LEVERAGE = 5                                    # Shown in signals but not used
RISK_PERCENT = 1                                # For position size calculation in signal message

# Technical Indicator Thresholds
ADX_THRESHOLDS = {
    "XRPUSDT": 24,
    "DOGEUSDT": 22, 
    "ADAUSDT": 22,
    "SUIUSDT": 23,
    "TRXUSDT": 21,
    "BLURUSDT": 20
}

# Exchange configuration (only needs read-only access for signals)
EXCHANGE_CONFIG = {
    'enableRateLimit': True,
    'apiKey': 'bt6wtI5SlRsJn8IhECt2saUgLeaGbuVRH9ON8vjUmnI8wjpKR7p4Xf6xzss3JpPy',
    'secret': 'iLjBvRiaZDOEWgznGjDxFeB31vtEAKRpKP2qw4A38I2CPGmyCOrZlbqkjFyiWB8T',
    'options': {
        'defaultType': 'future',
    }
}

# Signal Display Settings
SHOW_RSI = True
SHOW_MACD = True
SHOW_VOLUME = True
SHOW_SUPPORT_RESISTANCE = True