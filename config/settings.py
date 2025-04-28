PAIRS = ["XRPUSDT","DOGEUSDT","ADAUSDT","SUIUSDT","TRXUSDT","BLURUSDT"]
TIMEFRAME = "15m"
LEVERAGE = 5 
TRADE_AMOUNT = 6      # $6 per trade
MAX_TRADES = 1
NEUTRAL_MAX_TRADES = 1
LOG_FILE = "trades.csv"
STATE_FILE = "bot_state.json"

ADX_THRESHOLDS = {
    "BTCUSDT": 18,
    "DOGEUSDT": 22,
    "XRPUSDT": 24,
    "SUIUSDT": 23,  
    "BLURUSDT": 20,
    "TRXUSDT": 21,
    "ADAUSDT": 22,
}
# Exchange configuration
EXCHANGE_CONFIG = {
    'enableRateLimit': True,
    'apiKey': 'bt6wtI5SlRsJn8IhECt2saUgLeaGbuVRH9ON8vjUmnI8wjpKR7p4Xf6xzss3JpPy',
    'secret': 'iLjBvRiaZDOEWgznGjDxFeB31vtEAKRpKP2qw4A38I2CPGmyCOrZlbqkjFyiWB8T',
    'options': {
        'defaultType': 'future',
    }
}
