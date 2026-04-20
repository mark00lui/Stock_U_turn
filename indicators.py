"""Technical indicator calculations — RSI, MACD, Bollinger Bands, MA, Volume."""
import numpy as np
import pandas as pd


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI using Wilder's exponential smoothing (alpha = 1/period)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (macd_line, signal_line, histogram)."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bollinger(close: pd.Series, period: int = 20, std_dev: float = 2.0
                   ) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (middle, upper, lower) Bollinger Bands."""
    middle = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return middle, upper, lower


def calc_ma(close: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return close.rolling(period).mean()


def calc_ma_slope(ma: pd.Series, lookback: int = 5) -> pd.Series:
    """MA slope as percentage change over lookback days."""
    return (ma / ma.shift(lookback) - 1) * 100


def calc_volume_ratio(volume: pd.Series, period: int = 20) -> pd.Series:
    """Volume relative to N-day average."""
    avg = volume.rolling(period).mean()
    return volume / avg


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series,
             period: int = 14) -> pd.Series:
    """Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean()


def calc_highest(close: pd.Series, period: int) -> pd.Series:
    """Rolling N-day highest close."""
    return close.rolling(period).max()


def calc_lowest(close: pd.Series, period: int) -> pd.Series:
    """Rolling N-day lowest close."""
    return close.rolling(period).min()
