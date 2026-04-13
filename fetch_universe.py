"""Fetch top-N Taiwan stocks (TWSE + TPEx) ranked by trading value."""
import json
import time
import warnings

import requests
import urllib3

from config import CACHE_DIR, TOP_N, REQUEST_DELAY

# TWSE/TPEx certs sometimes lack Subject Key Identifier — suppress warning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_SESSION = requests.Session()
_SESSION.verify = False
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


# ── TWSE (上市) ────────────────────────────────────────
def fetch_twse_stocks() -> list[dict]:
    """Fetch all TWSE-listed stocks from the open-data daily report."""
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
                "code": code,
                "name": name,
                "market": "TWSE",
                "yf_ticker": f"{code}.TW",
                "trade_value": float(trade_value) if trade_value else 0,
                "close": float(close_str) if close_str else 0,
                "change": float(change_str) if change_str else 0,
            })
        except ValueError:
            continue
    return stocks


# ── TPEx (上櫃) ────────────────────────────────────────
def fetch_tpex_stocks() -> list[dict]:
    """Fetch all TPEx-listed stocks from the open-data daily report."""
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
                "code": code,
                "name": name,
                "market": "TPEx",
                "yf_ticker": f"{code}.TWO",
                "trade_value": float(trade_value) if trade_value else 0,
                "close": float(close_str) if close_str else 0,
                "change": float(change_str) if change_str else 0,
            })
        except ValueError:
            continue
    return stocks


# ── Public entry point ─────────────────────────────────
def get_top_stocks(n: int = TOP_N) -> list[dict]:
    """Return the top *n* stocks by trading value (TWSE + TPEx)."""
    cache_file = CACHE_DIR / "stock_universe.json"

    try:
        print("  Fetching TWSE stock list ...")
        twse = fetch_twse_stocks()
        print(f"    {len(twse)} TWSE stocks")

        time.sleep(REQUEST_DELAY)

        print("  Fetching TPEx stock list ...")
        tpex = fetch_tpex_stocks()
        print(f"    {len(tpex)} TPEx stocks")

        all_stocks = twse + tpex
        all_stocks.sort(key=lambda s: s["trade_value"], reverse=True)
        top = all_stocks[:n]

        # persist for offline fallback
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(top, f, ensure_ascii=False, indent=2)

        print(f"  Selected top {len(top)} stocks by trading value")
        return top

    except Exception as exc:
        print(f"  [WARN] API error: {exc}")
        if cache_file.exists():
            print("  Using cached stock universe ...")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        raise
