"""Download historical OHLCV data via yfinance with daily pickle cache."""
import pickle
import time
from datetime import date

import pandas as pd
import yfinance as yf

from config import CACHE_DIR, HISTORY_PERIOD, YF_BATCH_SIZE, MIN_DATA_POINTS, REQUEST_DELAY


def fetch_prices(stocks: list[dict]) -> dict[str, pd.DataFrame]:
    """Return ``{yf_ticker: DataFrame}`` with >= MIN_DATA_POINTS rows each.

    Results are cached to ``CACHE_DIR/prices_YYYY-MM-DD.pkl`` so that
    re-running on the same day skips the download.
    """
    today = date.today().isoformat()
    cache_file = CACHE_DIR / f"prices_{today}.pkl"

    if cache_file.exists():
        print(f"  Loading cached prices ({cache_file.name})")
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    tickers = [s["yf_ticker"] for s in stocks]
    all_data: dict[str, pd.DataFrame] = {}
    total = len(tickers)
    total_batches = (total + YF_BATCH_SIZE - 1) // YF_BATCH_SIZE

    for i in range(0, total, YF_BATCH_SIZE):
        batch = tickers[i : i + YF_BATCH_SIZE]
        batch_num = i // YF_BATCH_SIZE + 1
        print(f"  Batch {batch_num}/{total_batches}  ({len(batch)} tickers) ...")

        try:
            data = yf.download(
                batch,
                period=HISTORY_PERIOD,
                auto_adjust=True,
                threads=True,
                progress=False,
            )
            if data.empty:
                continue

            # yfinance returns MultiIndex columns for multi-ticker downloads
            if isinstance(data.columns, pd.MultiIndex):
                for ticker in batch:
                    try:
                        df = data.xs(ticker, level="Ticker", axis=1)
                    except KeyError:
                        continue
                    df = df.dropna(how="all")
                    if len(df) >= MIN_DATA_POINTS:
                        all_data[ticker] = df
            else:
                # single-ticker edge case
                df = data.dropna(how="all")
                if len(df) >= MIN_DATA_POINTS:
                    all_data[batch[0]] = df

        except Exception as exc:
            print(f"    [WARN] batch {batch_num} error: {exc}")

        if i + YF_BATCH_SIZE < total:
            time.sleep(REQUEST_DELAY)

    # cache for today
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "wb") as f:
        pickle.dump(all_data, f)

    print(f"  Downloaded data for {len(all_data)}/{total} stocks")
    return all_data
