"""
mtfEngine.py — Phase 2

Derives a directional bias ("BUY" | "SELL" | "NEUTRAL") per timeframe from
price structure relative to a fast/slow EMA pair, and computes an alignment
score across the configured timeframes. Feeds the h4_bias / h1_bias /
m15_structure / m5_structure / m1_setup fields on aiBrain.MarketSnapshot.

This is intentionally simple and swappable — smcEngine.py's BOS/CHoCH
detection should eventually override/refine this for the entry timeframes;
this module gives a fast, deterministic baseline bias per timeframe using
only price data (no external indicators required).
"""

from dataclasses import dataclass
from typing import Dict, List, Literal

from .common import Candle, ema_series

Bias = Literal["BUY", "SELL", "NEUTRAL"]


@dataclass
class TimeframeBias:
    timeframe: str
    bias: Bias
    fast_ema: float
    slow_ema: float
    price: float


@dataclass
class MTFResult:
    biases: Dict[str, TimeframeBias]
    alignment_score: float          # 0-100
    dominant_direction: Bias

    def summary(self) -> str:
        lines = [f"{tf}: {b.bias}" for tf, b in self.biases.items()]
        lines.append(f"Alignment: {self.alignment_score:.0f}/100 -> {self.dominant_direction}")
        return "\n".join(lines)


def bias_for_timeframe(
    candles: List[Candle],
    fast_period: int = 20,
    slow_period: int = 50,
    neutral_band_pct: float = 0.0005,
) -> TimeframeBias:
    """
    Determines bias from EMA structure:
      price > fast > slow, fast meaningfully above slow -> BUY
      price < fast < slow, fast meaningfully below slow -> SELL
      otherwise -> NEUTRAL (choppy / no clear structure)
    """
    if len(candles) < slow_period + 1:
        raise ValueError(f"Need at least {slow_period + 1} candles, got {len(candles)}")

    closes = [c.close for c in candles]
    fast = ema_series(closes, fast_period)[-1]
    slow = ema_series(closes, slow_period)[-1]
    price = closes[-1]

    separation = abs(fast - slow) / slow if slow else 0.0

    if price > fast > slow and separation > neutral_band_pct:
        bias: Bias = "BUY"
    elif price < fast < slow and separation > neutral_band_pct:
        bias = "SELL"
    else:
        bias = "NEUTRAL"

    return TimeframeBias(timeframe="", bias=bias, fast_ema=fast, slow_ema=slow, price=price)


def analyze(candles_by_timeframe: Dict[str, List[Candle]]) -> MTFResult:
    """
    Args:
        candles_by_timeframe: e.g. {"H4": [...], "H1": [...], "M15": [...],
                                     "M5": [...], "M1": [...]}
    """
    biases: Dict[str, TimeframeBias] = {}
    for tf, candles in candles_by_timeframe.items():
        tf_bias = bias_for_timeframe(candles)
        tf_bias.timeframe = tf
        biases[tf] = tf_bias

    buy_count = sum(1 for b in biases.values() if b.bias == "BUY")
    sell_count = sum(1 for b in biases.values() if b.bias == "SELL")
    total = len(biases)

    if buy_count >= sell_count:
        dominant: Bias = "BUY" if buy_count > 0 else "NEUTRAL"
        alignment = (buy_count / total) * 100
    else:
        dominant = "SELL"
        alignment = (sell_count / total) * 100

    return MTFResult(biases=biases, alignment_score=alignment, dominant_direction=dominant)
