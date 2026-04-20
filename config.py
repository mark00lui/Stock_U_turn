"""CTA Dashboard configuration."""
from pathlib import Path

# ── Paths ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"

# ── Stock universe ─────────────────────────────────────
TOP_N = 1000

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
HISTORY_PERIOD = "2y"      # yfinance history window (2 years for deeper backtest)
YF_BATCH_SIZE = 80         # tickers per yfinance batch
MIN_DATA_POINTS = 35       # minimum rows needed for MACD(26)+buffer
REQUEST_DELAY = 1.0        # seconds between API calls
