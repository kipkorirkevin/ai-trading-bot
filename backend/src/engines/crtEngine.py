"""
crtEngine.py — Phase 2 (spec section 11, optional confirmation module)

Detects candle-range-theory-style reversal signals: a liquidity sweep of a
recent extreme followed by a strong rejection close back inside the range.
This is explicitly informational — per spec, it's a confirmation input the
AI Brain may use to boost confidence, never an independent override.
"""

from dataclasses import dataclass
from typing import List, Optional, Literal

from .common import Candle

Signal = Literal["BUY_REVERSAL", "SELL_REVERSAL", "NONE"]


@dataclass
class CRTResult:
    signal: Signal
    confidence: float   # 0-100
    reason: str


def analyze(candles: List[Candle], lookback: int = 10) -> CRTResult:
    if len(candles) < lookback + 1:
        raise ValueError(f"Need at least {lookback + 1} candles, got {len(candles)}")

    window = candles[-(lookback + 1):-1]
    latest = candles[-1]

    range_high = max(c.high for c in window)
    range_low = min(c.low for c in window)

    # Swept the low, then closed back above it with a strong up-close -> bullish reversal
    swept_low = latest.low < range_low
    closed_bullish = latest.close > latest.open and latest.close > range_low
    if swept_low and closed_bullish:
        body = latest.close - latest.open
        rng = latest.high - latest.low
        strength = (body / rng) if rng else 0
        confidence = min(90.0, 50 + strength * 50)
        return CRTResult(
            signal="BUY_REVERSAL",
            confidence=round(confidence, 1),
            reason="Swept range low, closed back above it with a strong bullish candle",
        )

    swept_high = latest.high > range_high
    closed_bearish = latest.close < latest.open and latest.close < range_high
    if swept_high and closed_bearish:
        body = latest.open - latest.close
        rng = latest.high - latest.low
        strength = (body / rng) if rng else 0
        confidence = min(90.0, 50 + strength * 50)
        return CRTResult(
            signal="SELL_REVERSAL",
            confidence=round(confidence, 1),
            reason="Swept range high, closed back below it with a strong bearish candle",
        )

    return CRTResult(signal="NONE", confidence=0.0, reason="No sweep-and-reject pattern detected")
