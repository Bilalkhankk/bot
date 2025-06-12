# Trading Parameters
PAIRS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT']
TIMEFRAME = "15m"

# Telegram Configuration
TELEGRAM_BOT_TOKEN = "7981744692:AAEo4dmDLqrbIr0vUOCeQLnQFDHfaoTqcOw"  # Replace with your actual token
TELEGRAM_CHAT_ID = "-1002655134174"  # Replace with your actual chat ID

# Signal Parameters (for display in notifications)
LEVERAGE = 5
RISK_PERCENT = 1


ADX_THRESHOLDS = {
    "BTCUSDT": 22,
    "ETHUSDT": 20,
    "SOLUSDT": 25,
    "DOGEUSDT": 25,  # Require stronger trend for volatile assets
    "XRPUSDT": 20
}
MAX_LEVERAGE = {
    "DOGEUSDT": 15,
    "TRXUSDT": 10,
    "XRPUSDT": 20,
    "ADAUSDT": 20,
    "ETHUSDT": 50,
    "SOLUSDT": 50
}
VOLATILITY_RATINGS = {
    "BTCUSDT": 0.9,
    "ETHUSDT": 0.85,
    "SOLUSDT": 0.8,
    "XRPUSDT": 0.7,
    "DOGEUSDT": 0.6,  # High volatility
    "ADAUSDT": 0.75,
    "TRXUSDT": 0.65
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
