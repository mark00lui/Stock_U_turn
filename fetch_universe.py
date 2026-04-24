"""Build Taiwan stock universe — 市值(企業價值)主篩 (2026-04-24 reform v2).

Stage 1 (``get_top_stocks``) — static metadata filter:
  * Fetch TWSE/TPEx daily quotes (trade value, close price)
  * Join with paid-in capital + issued shares via ``fetch_capital.get_capital_data``
  * Compute 市值 = issued_shares × close
      (if issued_shares unavailable, fall back to capital / NT$10 par)
  * Pass if: 市值 ≥ 100億  AND  close ≥ NT$50  AND  non-ETF/DR

Stage 2 (``apply_liquidity_filter``) — dynamic liquidity floor using price history:
  * 20日 daily value ≥ 1億
  * 120日 daily value ≥ 1億
"""
import json
import time

import requests
import urllib3

from config import (
    CACHE_DIR,
    REQUEST_DELAY,
    MIN_PRICE,
    EXCLUDE_CODE_PREFIXES,
    EXCLUDE_NAME_PATTERNS,
    MKTCAP_THRESHOLD_NTD,
    MIN_DAILY_VALUE_20D,
    MIN_DAILY_VALUE_6M,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_SESSION = requests.Session()
_SESSION.verify = False
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

_PAR_VALUE = 10.0  # NT$10 par value — used as shares-outstanding fallback


def fetch_twse_stocks() -> list[dict]:
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    resp = _SESSION.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    stocks = []
    for item in data:
        code = item.get("Code", "").strip()
        name = item.get("Name", "").strip()
        trade_value = item.get("TradeValue", "0").replace(",", "")
        close_str = item.get("ClosingPrice", "0").replace(",", "")
        change_str = item.get("Change", "0").replace(",", "")
        if not (len(code) == 4 and code.isdigit()):
            continue
        try:
            stocks.append({
                "code": code, "name": name, "market": "TWSE",
                "yf_ticker": f"{code}.TW",
                "trade_value": float(trade_value) if trade_value else 0,
                "close": float(close_str) if close_str else 0,
                "change": float(change_str) if change_str else 0,
            })
        except ValueError:
            continue
    return stocks


def fetch_tpex_stocks() -> list[dict]:
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
    resp = _SESSION.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    stocks = []
    for item in data:
        code = (item.get("SecuritiesCompanyCode") or item.get("Code") or "").strip()
        name = (item.get("CompanyName") or item.get("Name") or "").strip()
        trade_value = (item.get("TransactionAmount") or item.get("TradeValue") or "0").replace(",", "")
        close_str = (item.get("Close") or item.get("ClosingPrice") or "0").replace(",", "")
        change_str = (item.get("Change") or "0").replace(",", "")
        if not (len(code) == 4 and code.isdigit()):
            continue
        try:
            stocks.append({
                "code": code, "name": name, "market": "TPEx",
                "yf_ticker": f"{code}.TWO",
                "trade_value": float(trade_value) if trade_value else 0,
                "close": float(close_str) if close_str else 0,
                "change": float(change_str) if change_str else 0,
            })
        except ValueError:
            continue
    return stocks


def _passes_basic_filter(stock: dict) -> bool:
    """Price floor + drop ETFs/DR股."""
    if stock["close"] < MIN_PRICE:
        return False
    code = stock["code"]
    for prefix in EXCLUDE_CODE_PREFIXES:
        if code.startswith(prefix):
            return False
    name = stock["name"]
    for pattern in EXCLUDE_NAME_PATTERNS:
        if pattern in name:
            return False
    return True


def _compute_mktcap(capital: int, issued_shares: int, close: float) -> float:
    """市值 = issued_shares × close. Fall back to (capital / NT$10 par) × close."""
    if issued_shares and issued_shares > 0:
        return issued_shares * close
    return (capital / _PAR_VALUE) * close


def get_top_stocks(n: int | None = None) -> list[dict]:
    """Return Stage-1 filtered universe (static metadata only).

    Filter: 市值 ≥ 100億  AND  close ≥ NT$50  AND  non-ETF/DR.
    Liquidity floor applied in Stage 2 (``apply_liquidity_filter``).

    ``n`` is ignored — kept for backward-compat with old callers.
    """
    from fetch_capital import get_capital_data

    cache_file = CACHE_DIR / "stock_universe.json"

    try:
        print("  Fetching TWSE daily quotes ...")
        twse = fetch_twse_stocks()
        print(f"    {len(twse)} TWSE stocks")

        time.sleep(REQUEST_DELAY)

        print("  Fetching TPEx daily quotes ...")
        tpex = fetch_tpex_stocks()
        print(f"    {len(tpex)} TPEx stocks")

        all_stocks = twse + tpex
        pre_basic = len(all_stocks)

        all_stocks = [s for s in all_stocks if _passes_basic_filter(s)]
        after_basic = len(all_stocks)

        print("  Fetching capital data (7-day cache) ...")
        capital_map = get_capital_data()

        enriched = []
        for s in all_stocks:
            meta = capital_map.get(s["code"])
            if meta is None:
                continue
            capital = meta["capital"]
            issued_shares = meta.get("issued_shares", 0) or 0
            mktcap = _compute_mktcap(capital, issued_shares, s["close"])
            s["capital"] = capital
            s["issued_shares"] = issued_shares
            s["market_cap"] = mktcap
            s["is_ky"] = meta.get("is_ky", False)
            enriched.append(s)
        after_join = len(enriched)

        filtered = [s for s in enriched if s["market_cap"] >= MKTCAP_THRESHOLD_NTD]

        print(
            f"  Stage 1 filter: {pre_basic} raw → {after_basic} (price≥{MIN_PRICE:.0f}, no ETF/DR) "
            f"→ {after_join} (with capital) → {len(filtered)} (市值≥{MKTCAP_THRESHOLD_NTD/1e8:.0f}億)"
        )

        filtered.sort(key=lambda s: s["market_cap"], reverse=True)

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(filtered, f, ensure_ascii=False, indent=2)

        print(f"  Stage 1 universe: {len(filtered)} stocks (cached)")
        return filtered

    except Exception as exc:
        print(f"  [WARN] API error: {exc}")
        if cache_file.exists():
            print("  Using cached stock universe ...")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        raise


def apply_liquidity_filter(stocks: list[dict], prices: dict) -> tuple[list[dict], dict]:
    """Stage 2: enforce 20d & 120d daily-value liquidity floor.

    Keep if: 20d_dv ≥ 1億 AND 120d_dv ≥ 1億.
    Stocks with < 120 days of history are dropped (cannot evaluate 6m floor).
    Returns filtered ``(stocks_list, prices_dict)``.
    """
    kept_stocks: list[dict] = []
    kept_prices: dict = {}
    dropped_history = 0
    dropped_liquidity = 0

    for s in stocks:
        ticker = s["yf_ticker"]
        df = prices.get(ticker)
        if df is None or len(df) < 120:
            dropped_history += 1
            continue

        close = df["Close"]
        volume = df["Volume"] if "Volume" in df.columns else None
        if volume is None:
            dropped_history += 1
            continue

        dv_20 = float((close.iloc[-20:] * volume.iloc[-20:]).mean())
        dv_120 = float((close.iloc[-120:] * volume.iloc[-120:]).mean())

        if dv_20 >= MIN_DAILY_VALUE_20D and dv_120 >= MIN_DAILY_VALUE_6M:
            s["daily_value_20d"] = dv_20
            s["daily_value_120d"] = dv_120
            kept_stocks.append(s)
            kept_prices[ticker] = df
        else:
            dropped_liquidity += 1

    print(
        f"  Stage 2 liquidity filter: {len(stocks)} → {len(kept_stocks)} "
        f"(dropped {dropped_history} for <120d history, {dropped_liquidity} for liquidity)"
    )
    return kept_stocks, kept_prices
