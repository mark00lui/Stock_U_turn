"""Active ETF daily-holdings snapshot fetcher (Phase 2).

Fetches per-stock holdings from active-management ETFs (基金經理人每日調倉揭露).
Snapshots are stored daily so T-vs-T-1 diffs reveal manager buy/sell direction —
used as auxiliary momentum signals (not a primary driver).

Covered ETFs (HTTP-only, no browser):
  * 00981A 統一台股增長    — ezmoney xlsx endpoint (fundCode=49YTW)
  * 00980A 野村智慧優選    — Nomura JSON POST API
  * 00985A 野村台灣50      — Nomura JSON POST API

Output: ``data/active_etf/holdings_YYYY-MM-DD_<etf_id>.json``
"""
from __future__ import annotations

import io
import json
import re
import time
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ACTIVE_ETFS: dict[str, dict] = {
    "00981A": {
        "issuer": "統一",
        "name": "統一台股增長",
        "method": "unified_xlsx",
        "fund_code": "49YTW",
    },
    "00980A": {
        "issuer": "野村",
        "name": "野村智慧優選",
        "method": "nomura_json",
        "fund_id": "00980A",
    },
    "00985A": {
        "issuer": "野村",
        "name": "野村台灣50",
        "method": "nomura_json",
        "fund_id": "00985A",
    },
}

OUTPUT_DIR = Path(__file__).parent / "data" / "active_etf"

_HEADERS = {"User-Agent": "Mozilla/5.0"}
_TIMEOUT = 30
_RETRIES = 2
_RETRY_SLEEP = 3

_NOMURA_URL = "https://www.nomurafunds.com.tw/API/ETFAPI/api/Fund/GetFundAssets"
_UNIFIED_XLSX_URL = "https://www.ezmoney.com.tw/ETF/Fund/AssetExcelNPOI?fundCode={fund_code}"

_SESSION = requests.Session()
_SESSION.verify = False
_SESSION.headers.update(_HEADERS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_code(raw) -> str | None:
    """Normalise a TW stock code to 4-digit string; return None if unusable."""
    if raw is None:
        return None
    s = str(raw).strip()
    # pandas may give us '2330.0'
    if s.endswith(".0"):
        s = s[:-2]
    s = s.split(".")[0]
    # strip any trailing non-digit marker like '*', '-KY'
    m = re.match(r"^(\d{4,6})", s)
    if not m:
        return None
    code = m.group(1)
    # TW stocks are 4-digit (some 5-digit warrants, exclude); we only want 4-digit equities
    if len(code) == 4:
        return code
    return None


def _clean_name(raw) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    # collapse whitespace
    s = re.sub(r"\s+", "", s)
    return s


def _to_float(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    s = s.replace(",", "").replace("%", "").replace("NTD", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _to_int_shares(raw) -> int | None:
    v = _to_float(raw)
    if v is None:
        return None
    return int(round(v))


def _roc_to_ad(roc_date: str) -> str | None:
    """Convert 民國 115/04/24 → 2026-04-24."""
    m = re.search(r"(\d{2,3})[/\-](\d{1,2})[/\-](\d{1,2})", roc_date or "")
    if not m:
        return None
    y = int(m.group(1)) + 1911
    return f"{y:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _slash_date_to_iso(s: str) -> str | None:
    """Convert '2026/04/24' → '2026-04-24'."""
    m = re.search(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", s or "")
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _retry(fn, *args, **kwargs):
    last_exc = None
    for attempt in range(_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < _RETRIES:
                time.sleep(_RETRY_SLEEP)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Fetchers (per-method)
# ---------------------------------------------------------------------------


def _fetch_unified_xlsx(etf_id: str, meta: dict) -> dict:
    """Ezmoney / 統一投信 xlsx endpoint.

    Layout:
      row 0 col 0: '資料日期：115/04/24'
      row 3 col 1: 'NTD <total_aum>'
      row 5 col 1: 'NTD <nav>'
      row 19: header  股票代號 | 股票名稱 | 股數 | 持股權重
      row 20+: holdings
    """
    url = _UNIFIED_XLSX_URL.format(fund_code=meta["fund_code"])

    def _do():
        r = _SESSION.get(url, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.content

    content = _retry(_do)
    df = pd.read_excel(io.BytesIO(content), header=None, engine="openpyxl")

    disclose_date = None
    nav = None
    total_aum = None
    holdings_start = None

    # Scan metadata + find holdings header row
    for i in range(min(len(df), 40)):
        col0 = str(df.iat[i, 0]) if pd.notna(df.iat[i, 0]) else ""
        col1 = str(df.iat[i, 1]) if df.shape[1] > 1 and pd.notna(df.iat[i, 1]) else ""

        if disclose_date is None and "資料日期" in col0:
            disclose_date = _roc_to_ad(col0)
        if "淨資產" in col0 and col1:
            total_aum = _to_float(col1)
        if "每單位淨值" in col0 and col1:
            nav = _to_float(col1)
        if "股票代號" in col0 and "股票名稱" in col1:
            holdings_start = i + 1
            break

    holdings: list[dict] = []
    if holdings_start is not None:
        for i in range(holdings_start, len(df)):
            raw_code = df.iat[i, 0] if df.shape[1] > 0 else None
            code = _clean_code(raw_code)
            if code is None:
                continue
            name = _clean_name(df.iat[i, 1]) if df.shape[1] > 1 else ""
            shares = _to_int_shares(df.iat[i, 2]) if df.shape[1] > 2 else None
            weight = _to_float(df.iat[i, 3]) if df.shape[1] > 3 else None
            if shares is None and weight is None:
                continue
            holdings.append({
                "code": code,
                "name": name,
                "shares": shares or 0,
                "weight": weight if weight is not None else 0.0,
            })

    return {
        "etf_id": etf_id,
        "name": meta["name"],
        "issuer": meta["issuer"],
        "disclose_date": disclose_date,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "nav": nav,
        "total_aum": total_aum,
        "holdings": holdings,
        "source_url": url,
        "source_format": "xlsx",
    }


def _fetch_nomura_json(etf_id: str, meta: dict) -> dict:
    """Nomura 野村投信 JSON POST API.

    Response schema:
      Entries.Data.FundAsset: {Aum, Units, Nav, NavDate 'YYYY/MM/DD'}
      Entries.Data.Table[0].Rows: list of [code, name, shares, weight_pct_str]
    """
    today = datetime.now().strftime("%Y-%m-%d")
    payload = {"FundID": meta["fund_id"], "SearchDate": today}

    def _do():
        r = _SESSION.post(
            _NOMURA_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    data = _retry(_do)
    entries = (data or {}).get("Entries") or {}
    inner = entries.get("Data") or {}
    fund_asset = inner.get("FundAsset") or {}

    nav = _to_float(fund_asset.get("Nav"))
    total_aum = _to_float(fund_asset.get("Aum"))
    disclose_date = _slash_date_to_iso(fund_asset.get("NavDate", ""))

    tables = inner.get("Table") or []
    rows = []
    if tables:
        # Find the stock table (first one is usually 股票)
        rows = tables[0].get("Rows") or []

    holdings: list[dict] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 4:
            continue
        code = _clean_code(row[0])
        if code is None:
            continue
        name = _clean_name(row[1])
        shares = _to_int_shares(row[2])
        weight = _to_float(row[3])
        if shares is None and weight is None:
            continue
        holdings.append({
            "code": code,
            "name": name,
            "shares": shares or 0,
            "weight": weight if weight is not None else 0.0,
        })

    return {
        "etf_id": etf_id,
        "name": meta["name"],
        "issuer": meta["issuer"],
        "disclose_date": disclose_date,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "nav": nav,
        "total_aum": total_aum,
        "holdings": holdings,
        "source_url": f"{_NOMURA_URL}?FundID={meta['fund_id']}",
        "source_format": "json",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_etf_snapshot(etf_id: str) -> dict:
    """Fetch one ETF's current daily holdings snapshot (normalised schema)."""
    if etf_id not in ACTIVE_ETFS:
        raise ValueError(f"Unknown ETF: {etf_id}")
    meta = ACTIVE_ETFS[etf_id]
    method = meta["method"]
    if method == "unified_xlsx":
        return _fetch_unified_xlsx(etf_id, meta)
    if method == "nomura_json":
        return _fetch_nomura_json(etf_id, meta)
    raise ValueError(f"Unknown method: {method}")


def save_snapshot(snapshot: dict) -> Path:
    """Persist snapshot to ``data/active_etf/holdings_YYYY-MM-DD_<etf>.json``."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = snapshot.get("disclose_date") or datetime.now().strftime("%Y-%m-%d")
    path = OUTPUT_DIR / f"holdings_{date_tag}_{snapshot['etf_id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    return path


def fetch_all_snapshots() -> list[dict]:
    """Fetch + save snapshots for all ETFs in ``ACTIVE_ETFS``.

    Errors are logged; individual failures do not abort the batch.
    """
    results: list[dict] = []
    for etf_id in ACTIVE_ETFS:
        name = ACTIVE_ETFS[etf_id]["name"]
        print(f"[fetch] {etf_id} {name} ...", flush=True)
        try:
            snap = fetch_etf_snapshot(etf_id)
            path = save_snapshot(snap)
            n = len(snap["holdings"])
            print(
                f"  OK  {n:>3} holdings | disclose={snap.get('disclose_date')} | "
                f"nav={snap.get('nav')} | saved={path.name}"
            )
            results.append(snap)
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] {etf_id} fetch failed: {exc}")
        time.sleep(1)
    return results


def _load_snapshot(etf_id: str, date: str) -> dict | None:
    path = OUTPUT_DIR / f"holdings_{date}_{etf_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def diff_snapshots(etf_id: str, date_today: str, date_yesterday: str) -> dict | None:
    """Compute holdings diff (today - yesterday). Returns None if a file missing."""
    today = _load_snapshot(etf_id, date_today)
    yday = _load_snapshot(etf_id, date_yesterday)
    if today is None or yday is None:
        return None

    by_today = {h["code"]: h for h in today["holdings"]}
    by_yday = {h["code"]: h for h in yday["holdings"]}
    codes_today = set(by_today.keys())
    codes_yday = set(by_yday.keys())

    new_positions: list[dict] = []
    closed_positions: list[dict] = []
    increased: list[dict] = []
    decreased: list[dict] = []
    unchanged = 0

    for code in codes_today - codes_yday:
        h = by_today[code]
        new_positions.append({
            "code": code,
            "name": h["name"],
            "shares_delta": h["shares"],
            "weight_delta": h["weight"],
        })

    for code in codes_yday - codes_today:
        h = by_yday[code]
        closed_positions.append({
            "code": code,
            "name": h["name"],
            "shares_delta": -h["shares"],
            "weight_delta": -h["weight"],
        })

    for code in codes_today & codes_yday:
        ht = by_today[code]
        hy = by_yday[code]
        ds = (ht["shares"] or 0) - (hy["shares"] or 0)
        dw = (ht["weight"] or 0) - (hy["weight"] or 0)
        if ds == 0 and abs(dw) < 1e-9:
            unchanged += 1
            continue
        entry = {
            "code": code,
            "name": ht["name"],
            "shares_delta": ds,
            "weight_delta": round(dw, 4),
        }
        if ds > 0:
            increased.append(entry)
        elif ds < 0:
            decreased.append(entry)
        else:
            # shares flat but weight moved (price drift) — count as unchanged
            unchanged += 1

    # sort by magnitude of shares_delta
    increased.sort(key=lambda x: x["shares_delta"], reverse=True)
    decreased.sort(key=lambda x: x["shares_delta"])
    new_positions.sort(key=lambda x: x["weight_delta"], reverse=True)
    closed_positions.sort(key=lambda x: x["weight_delta"])

    return {
        "etf_id": etf_id,
        "from_date": date_yesterday,
        "to_date": date_today,
        "new_positions": new_positions,
        "increased": increased,
        "decreased": decreased,
        "closed_positions": closed_positions,
        "unchanged": unchanged,
    }


def compute_consensus_signal(
    date_today: str,
    date_yesterday: str,
    min_pct_delta: float = 0.01,
    min_abs_shares: int = 5_000,
) -> dict:
    """Cross-ETF consensus signal based on share-count delta (the truthful signal).

    This is the ONLY correct way to detect "smart-money buy/sell" — weight_delta
    is contaminated by stock price moves and AUM growth from inflows/redemptions.

    A single ETF position counts as "moved" only if either:
      - |Δshares / shares_yesterday| >= min_pct_delta (default 1%), OR
      - shares_yesterday == 0 and |Δshares| >= min_abs_shares (new position), OR
      - shares_today == 0 and |shares_yesterday| >= min_abs_shares (closed)

    A stock is classified as:
      - TRIPLE_BUY: ≥2 of 3 ETFs bought (Δshares > 0), 0 sold
      - TRIPLE_SELL: ≥2 of 3 ETFs sold (Δshares < 0), 0 bought
      - SINGLE_BUY: exactly 1 ETF bought, 0 sold
      - SINGLE_SELL: exactly 1 ETF sold, 0 bought
      - MIXED: at least 1 buy and 1 sell across ETFs (manager disagreement)
    """
    stock_data: dict[str, dict] = {}
    snapshots: dict[str, dict] = {}

    for etf_id in ACTIVE_ETFS:
        snap_t = _load_snapshot(etf_id, date_today)
        snap_y = _load_snapshot(etf_id, date_yesterday)
        if snap_t is None or snap_y is None:
            continue
        snapshots[etf_id] = {"today": snap_t, "yday": snap_y}
        by_y = {h["code"]: h for h in snap_y["holdings"]}
        by_t = {h["code"]: h for h in snap_t["holdings"]}

        for code in set(by_y.keys()) | set(by_t.keys()):
            h_y = by_y.get(code)
            h_t = by_t.get(code)
            shares_y = (h_y or {}).get("shares", 0) or 0
            shares_t = (h_t or {}).get("shares", 0) or 0
            ds = shares_t - shares_y
            if ds == 0:
                continue

            if shares_y == 0:  # new position
                significant = abs(ds) >= min_abs_shares
            elif shares_t == 0:  # closed
                significant = abs(ds) >= min_abs_shares
            else:
                significant = abs(ds / shares_y) >= min_pct_delta
            if not significant:
                continue

            name = (h_t or h_y or {}).get("name", "")
            weight_y = (h_y or {}).get("weight", 0) or 0
            weight_t = (h_t or {}).get("weight", 0) or 0
            entry = stock_data.setdefault(code, {"name": name, "etfs": {}})
            entry["etfs"][etf_id] = {
                "shares_yday": shares_y,
                "shares_today": shares_t,
                "shares_delta": ds,
                "weight_yday": weight_y,
                "weight_today": weight_t,
                "weight_delta": round(weight_t - weight_y, 4),
                "pct_delta": round(ds / shares_y * 100, 2) if shares_y > 0 else None,
            }

    triple_buy: list[dict] = []
    triple_sell: list[dict] = []
    single_buy: list[dict] = []
    single_sell: list[dict] = []
    mixed: list[dict] = []

    for code, info in stock_data.items():
        buys = [eid for eid, d in info["etfs"].items() if d["shares_delta"] > 0]
        sells = [eid for eid, d in info["etfs"].items() if d["shares_delta"] < 0]
        total = sum(d["shares_delta"] for d in info["etfs"].values())
        rec = {
            "code": code,
            "name": info["name"],
            "etfs_buying": buys,
            "etfs_selling": sells,
            "total_shares_delta": total,
            "etf_details": info["etfs"],
        }
        if len(buys) >= 2 and len(sells) == 0:
            triple_buy.append(rec)
        elif len(sells) >= 2 and len(buys) == 0:
            triple_sell.append(rec)
        elif len(buys) == 1 and len(sells) == 0:
            single_buy.append(rec)
        elif len(sells) == 1 and len(buys) == 0:
            single_sell.append(rec)
        else:
            mixed.append(rec)

    triple_buy.sort(key=lambda x: -x["total_shares_delta"])
    triple_sell.sort(key=lambda x: x["total_shares_delta"])
    single_buy.sort(key=lambda x: -x["total_shares_delta"])
    single_sell.sort(key=lambda x: x["total_shares_delta"])
    mixed.sort(key=lambda x: -abs(x["total_shares_delta"]))

    return {
        "date_today": date_today,
        "date_yesterday": date_yesterday,
        "TRIPLE_BUY": triple_buy,
        "TRIPLE_SELL": triple_sell,
        "SINGLE_BUY": single_buy,
        "SINGLE_SELL": single_sell,
        "MIXED": mixed,
        "_thresholds": {"min_pct_delta": min_pct_delta, "min_abs_shares": min_abs_shares},
    }


def format_consensus_report(consensus: dict, top_n: int = 8) -> str:
    """Render a human-readable summary block — used by daily report and console."""
    out = []
    d_t = consensus["date_today"]
    d_y = consensus["date_yesterday"]
    out.append(f"## ETF Smart-Money Consensus ({d_y} → {d_t}, share-delta basis)")
    out.append("")
    out.append("> Computed from raw holding share counts (the only truthful BUY/SELL signal).")
    out.append("> weight_delta is shown for context but is NOT used for classification —")
    out.append("> price moves and AUM swings dominate weight_delta and produce false signals.")
    out.append("")

    def render_list(label: str, items: list[dict], limit: int) -> None:
        if not items:
            out.append(f"### {label}: (none)")
            out.append("")
            return
        out.append(f"### {label} (top {min(limit, len(items))})")
        out.append("| Code | Name | ETFs | Total Δshares | Per-ETF detail |")
        out.append("|------|------|------|--------------:|----------------|")
        for r in items[:limit]:
            etfs = "+".join(r["etfs_buying"] or r["etfs_selling"])
            details = "; ".join(
                f"{eid}: {d['shares_delta']:+,d} ({d['pct_delta']:+.1f}%)" if d["pct_delta"] is not None
                else f"{eid}: {d['shares_delta']:+,d} (new/closed)"
                for eid, d in r["etf_details"].items()
            )
            out.append(f"| {r['code']} | {r['name']} | {etfs} | {r['total_shares_delta']:+,d} | {details} |")
        out.append("")

    render_list("🟢 TRIPLE BUY (≥2 ETFs bought, 0 sold)", consensus["TRIPLE_BUY"], top_n)
    render_list("🔴 TRIPLE SELL (≥2 ETFs sold, 0 bought)", consensus["TRIPLE_SELL"], top_n)
    render_list("🟡 SINGLE BUY (1 ETF bought)", consensus["SINGLE_BUY"], top_n)
    render_list("🟠 SINGLE SELL (1 ETF sold)", consensus["SINGLE_SELL"], top_n)
    if consensus["MIXED"]:
        out.append(f"### ⚪ MIXED (managers disagree): {len(consensus['MIXED'])} stocks")
        out.append("")
    return "\n".join(out)


def diff_all_today() -> list[dict]:
    """For every ETF, diff today's snapshot against the most recent prior one."""
    diffs: list[dict] = []
    if not OUTPUT_DIR.exists():
        return diffs

    for etf_id in ACTIVE_ETFS:
        # find files for this etf, sorted by date
        files = sorted(OUTPUT_DIR.glob(f"holdings_*_{etf_id}.json"))
        if len(files) < 2:
            print(f"[diff] {etf_id}: no yesterday snapshot, skipping")
            continue
        # use last two distinct dates
        dates = []
        for f in files:
            m = re.search(r"holdings_(\d{4}-\d{2}-\d{2})_", f.name)
            if m and m.group(1) not in dates:
                dates.append(m.group(1))
        dates.sort()
        if len(dates) < 2:
            print(f"[diff] {etf_id}: only 1 unique date, skipping")
            continue
        date_y, date_t = dates[-2], dates[-1]
        d = diff_snapshots(etf_id, date_t, date_y)
        if d is None:
            print(f"[diff] {etf_id}: snapshot load failed")
            continue
        print(
            f"[diff] {etf_id} {date_y} -> {date_t}: "
            f"+{len(d['new_positions'])} new / "
            f"↑{len(d['increased'])} inc / "
            f"↓{len(d['decreased'])} dec / "
            f"X{len(d['closed_positions'])} closed / "
            f"={d['unchanged']} unchanged"
        )
        diffs.append(d)
    return diffs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("=" * 60)
    print("Active ETF Daily Holdings Fetcher")
    print("=" * 60)
    print(f"Output dir: {OUTPUT_DIR}")
    print(f"ETFs: {list(ACTIVE_ETFS.keys())}")
    print()

    snaps = fetch_all_snapshots()

    print()
    print("-" * 60)
    print("Snapshot summary:")
    for s in snaps:
        print(
            f"  {s['etf_id']} {s['name']:<16} "
            f"holdings={len(s['holdings']):>3} "
            f"disclose={s.get('disclose_date')} "
            f"nav={s.get('nav')}"
        )

    print()
    print("-" * 60)
    print("Diff vs yesterday (per-ETF, shares-based classification):")
    diff_all_today()

    # Cross-ETF share-delta consensus (the truthful BUY/SELL signal)
    print()
    print("-" * 60)
    print("Cross-ETF consensus (shares-delta, AUM-immune):")
    files = sorted(OUTPUT_DIR.glob("holdings_*.json"))
    dates_seen: list[str] = []
    for f in files:
        m = re.search(r"holdings_(\d{4}-\d{2}-\d{2})_", f.name)
        if m and m.group(1) not in dates_seen:
            dates_seen.append(m.group(1))
    dates_seen.sort()
    if len(dates_seen) >= 2:
        d_y, d_t = dates_seen[-2], dates_seen[-1]
        consensus = compute_consensus_signal(d_t, d_y)
        print(format_consensus_report(consensus))
    else:
        print("  (need ≥2 distinct snapshot dates)")

    print()
    print("Done.")
