"""CTA Dashboard configuration."""
from pathlib import Path

# ── Paths ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"

# ── Stock universe — 市值(企業價值)主篩 (2026-04-24 reform v2) ──
# Replaces old TOP_N=1000 by single-day trade value.
# 企業價值 = 市值 = issued_shares × close price (回歸原則：市場給的價值)
#
# Stage 1 (static, fetch_universe.get_top_stocks):
#   市值 ≥ 100億  AND  股價 ≥ NT$50  AND  非 ETF/DR
# Stage 2 (dynamic liquidity, fetch_universe.apply_liquidity_filter):
#   20日日均成交值 ≥ 1億  AND  6月日均成交值 ≥ 1億
MIN_PRICE = 50.0
EXCLUDE_CODE_PREFIXES = ("00",)
EXCLUDE_NAME_PATTERNS = ("-DR",)

MKTCAP_THRESHOLD_NTD = 1.0e10            # 100億 市值 (涵蓋 M31/穎崴/譜瑞/信驊/世芯-KY 等 ASIC 成長股)
MIN_DAILY_VALUE_20D = 1.0e8              # 20日日均成交值 ≥ 1億
MIN_DAILY_VALUE_6M = 1.0e8               # 6月日均成交值 ≥ 1億 (流動性地板)

# Legacy — kept for backward compat with any external scripts; no longer used internally.
TOP_N = 1000
CAPITAL_THRESHOLD_NTD = 3.0e9            # deprecated (was primary gate; replaced by mktcap)

# ── Volume gate (momentum & breakout) — 20日主閘 + 6月地板 ─
VOLUME_RATIO_GATE = 1.2               # today / MA20 (主閘，保即時性)
VOLUME_RATIO_6M_FLOOR = 0.8           # today / MA120 (6月絕對量地板)
MIN_DAILY_VALUE_NTD = 1.5e8           # 今日 daily value ≥ 1.5億
MIN_DAILY_VALUE_MA120 = 1.5e8         # MA120 daily value ≥ 1.5億
MIN_HISTORY_DAYS = 140                # 60 → 140 (supports MA120 baseline)

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
MIN_DATA_POINTS = 35       # minimum rows needed (MACD(26)+buffer for reversal);
                           # momentum/breakout enforce their own 140-day gate internally
REQUEST_DELAY = 1.0        # seconds between API calls
