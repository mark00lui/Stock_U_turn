"""Fetch paid-in capital (實收資本額) for TWSE/TPEx-listed companies including KY 股.

Data sources:
  - TWSE: https://openapi.twse.com.tw/v1/opendata/t187ap03_L  (Big5 — 實收資本額 at col idx 17)
  - TPEx: https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O  (UTF-8 — Paidin.Capital.NTDollars)

Returns ``{code: {"capital": int, "name": str, "market": str, "is_ky": bool}}``.
Cached for 7 days under ``data/cache/capital.json`` — paid-in capital rarely changes.
"""
import json
import time
import warnings
from datetime import date, datetime, timedelta

import requests
import urllib3

from config import CACHE_DIR, REQUEST_DELAY


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_SESSION = requests.Session()
_SESSION.verify = False
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

_CACHE_TTL_DAYS = 7


# ── TWSE (上市) ────────────────────────────────────────
def _fetch_twse_capital() -> dict[str, dict]:
    """Fetch 上市公司基本資料 — index-based parse because Big5 headers come back garbled.

    TWSE column order (verified 2026-04-24):
      [0] 出表日期  [1] 公司代號  [2] 公司名稱  [3] 公司簡稱
      [17] 實收資本額  [32] 已發行普通股數或TDR原股發行股數
    """
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    resp = _SESSION.get(url, timeout=30)
    resp.raise_for_status()
    rows = resp.json()

    result: dict[str, dict] = {}
    for row in rows:
        values = list(row.values())
        if len(values) < 18:
            continue
        code = str(values[1]).strip()           # 公司代號
        name = str(values[3]).strip()           # 公司簡稱
        capital_raw = str(values[17]).strip()   # 實收資本額(元)
        shares_raw = str(values[32]).strip() if len(values) > 32 else ""   # 已發行普通股數
        try:
            capital = int(float(capital_raw)) if capital_raw else 0
        except ValueError:
            continue
        try:
            issued_shares = int(float(shares_raw)) if shares_raw else 0
        except ValueError:
            issued_shares = 0
        if not code or capital <= 0:
            continue
        result[code] = {
            "capital": capital,
            "issued_shares": issued_shares,  # may be 0 if unavailable
            "name": name,
            "market": "TWSE",
            "is_ky": ("KY" in name) or name.endswith("-KY") or code.startswith("91"),
        }
    return result


# ── TPEx (上櫃) ────────────────────────────────────────
def _fetch_tpex_capital() -> dict[str, dict]:
    """Fetch 上櫃公司基本資料 — UTF-8 with clean English field names."""
    url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
    resp = _SESSION.get(url, timeout=30)
    resp.raise_for_status()
    rows = resp.json()

    result: dict[str, dict] = {}
    for row in rows:
        code = str(row.get("SecuritiesCompanyCode", "")).strip()
        name = str(row.get("CompanyAbbreviation", "") or row.get("CompanyName", "")).strip()
        capital_raw = str(row.get("Paidin.Capital.NTDollars", "0")).replace(",", "").strip()
        try:
            capital = int(float(capital_raw)) if capital_raw else 0
        except ValueError:
            continue
        if not code or capital <= 0:
            continue
        result[code] = {
            "capital": capital,
            "issued_shares": 0,  # TPEx t187ap03_O doesn't expose; fall back to capital/10
            "name": name,
            "market": "TPEx",
            "is_ky": ("KY" in name) or name.endswith("-KY"),
        }
    return result


# ── Public entry ───────────────────────────────────────
def get_capital_data(force_refresh: bool = False) -> dict[str, dict]:
    """Return ``{code: {capital, name, market, is_ky}}`` merged across TWSE+TPEx.

    Cached for 7 days at ``data/cache/capital.json``.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / "capital.json"

    if cache_file.exists() and not force_refresh:
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(payload.get("fetched_at", "2000-01-01"))
            if datetime.now() - fetched_at < timedelta(days=_CACHE_TTL_DAYS):
                print(f"  Using cached capital data ({payload.get('fetched_at')[:10]}, "
                      f"{len(payload['data'])} companies)")
                return payload["data"]
        except Exception:
            pass  # fall through to refetch

    print("  Fetching TWSE company basic data (t187ap03_L) ...")
    twse = _fetch_twse_capital()
    print(f"    {len(twse)} TWSE companies")

    time.sleep(REQUEST_DELAY)

    print("  Fetching TPEx company basic data (mopsfin_t187ap03_O) ...")
    tpex = _fetch_tpex_capital()
    print(f"    {len(tpex)} TPEx companies")

    merged = {**twse, **tpex}

    cache_file.write_text(
        json.dumps({
            "fetched_at": datetime.now().isoformat(),
            "count": len(merged),
            "data": merged,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Cached {len(merged)} companies → {cache_file.name}")
    return merged


if __name__ == "__main__":
    import sys, io
    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    data = get_capital_data(force_refresh=True)
    # Quick sanity histogram
    buckets = {"<10億": 0, "10-30億": 0, "30-50億": 0, "50-100億": 0, "100-200億": 0, ">=200億": 0}
    ky_count = 0
    for code, info in data.items():
        cap = info["capital"]
        if info["is_ky"]:
            ky_count += 1
        if cap < 1e9:
            buckets["<10億"] += 1
        elif cap < 3e9:
            buckets["10-30億"] += 1
        elif cap < 5e9:
            buckets["30-50億"] += 1
        elif cap < 10e9:
            buckets["50-100億"] += 1
        elif cap < 20e9:
            buckets["100-200億"] += 1
        else:
            buckets[">=200億"] += 1
    print(f"\nTotal: {len(data)} companies, KY: {ky_count}")
    for k, v in buckets.items():
        print(f"  {k}: {v}")
