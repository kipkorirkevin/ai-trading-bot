"""
common.py — shared types used across all engine modules.

Every engine (momentum, volume, exhaustion, fakeout, MTF, SMC, straddle...)
consumes lists of Candle objects. Keeping this in one place means
marketData.py only has to produce one shape of data, and every engine
downstream can rely on it.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class Candle:
    timestamp: int      # unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


# Shared across brokers/ and data/ so "M15" means the same 900 seconds
# everywhere — mockAdapter uses this to generate realistic timestamps,
# marketData.py uses it for staleness/gap checks.
TIMEFRAME_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}


def true_range(prev: Candle, cur: Candle) -> float:
    return max(
        cur.high - cur.low,
        abs(cur.high - prev.close),
        abs(cur.low - prev.close),
    )


def atr(candles: List[Candle], period: int = 14) -> float:
    """Simple moving-average ATR over the last `period` candles."""
    if len(candles) < period + 1:
        raise ValueError(f"Need at least {period + 1} candles to compute ATR({period})")
    trs = [
        true_range(candles[i - 1], candles[i])
        for i in range(len(candles) - period, len(candles))
    ]
    return sum(trs) / len(trs)


def sma(values: List[float], period: int) -> float:
    if len(values) < period:
        raise ValueError(f"Need at least {period} values for SMA({period})")
    window = values[-period:]
    return sum(window) / period


def ema_series(values: List[float], period: int) -> List[float]:
    """Returns the full EMA series (same length as `values`, seeded by SMA)."""
    if len(values) < period:
        raise ValueError(f"Need at least {period} values for EMA({period})")
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out
