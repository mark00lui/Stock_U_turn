"""CTA Dashboard configuration."""
from pathlib import Path

# ── Paths ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"

# ── Stock universe ─────────────────────────────────────
TOP_N = 1000
MIN_PRICE = 50.0                  # drop sub-NT$50 names (focus on 3-4位數 strong stocks)
EXCLUDE_CODE_PREFIXES = ("00",)   # drop ETFs/bonds (0050, 00878, 等)
EXCLUDE_NAME_PATTERNS = ("-DR",)  # drop 存託憑證 (9105 泰金寶-DR 等)

# ── Volume gate (momentum & breakout) ──────────────────
VOLUME_RATIO_GATE = 1.2           # recent vol / 20d avg — gate at 1.2x (Strategist consensus)
MIN_DAILY_VALUE_NTD = 3.0e8       # 20d avg daily value ≥ NT$3億 (Trader liquidity floor)
MIN_HISTORY_DAYS = 60             # reject signals for newly listed stocks (Data RD caveat)

# ── RSI parameters ─────────────────────────────────────
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_RECOVERY = 35

# ── MACD parameters ────────────────────────────────────
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# ── Signal detection ───────────────────────────────────
LOOKBACK_DAYS = 5          # trading days to scan for signal events

# ── Data fetching ──────────────────────────────────────
HISTORY_PERIOD = "5y"      # yfinance history window (5 years for deep backtest)
YF_BATCH_SIZE = 80         # tickers per yfinance batch
MIN_DATA_POINTS = 35       # minimum rows needed for MACD(26)+buffer
REQUEST_DELAY = 1.0        # seconds between API calls
