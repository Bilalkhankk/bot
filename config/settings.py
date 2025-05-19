# Trading Parameters
PAIRS = ["XRPUSDT", "DOGEUSDT", "ADAUSDT", "SUIUSDT", "TRXUSDT", "BLURUSDT"]
TIMEFRAME = "15m"

# Telegram Configuration
TELEGRAM_BOT_TOKEN = "7981744692:AAEo4dmDLqrbIr0vUOCeQLnQFDHfaoTqcOw"  # Replace with your actual token
TELEGRAM_CHAT_ID = "-1002655134174"  # Replace with your actual chat ID

# Signal Parameters (for display in notifications)
LEVERAGE = 5
RISK_PERCENT = 1

# Technical Indicator Thresholds
ADX_THRESHOLDS = {
    "XRPUSDT": 24,
    "DOGEUSDT": 22,
    "ADAUSDT": 22,
    "SUIUSDT": 23,
    "TRXUSDT": 21,
    "BLURUSDT": 20
}

# Exchange configuration (read-only access, no account needed)
EXCHANGE_CONFIG = {
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',  # or 'spot' if you're using spot data
    }
}

# Signal Display Settings
SHOW_RSI = True
SHOW_MACD = True
SHOW_VOLUME = True
SHOW_SUPPORT_RESISTANCE = True
