"""
exhaustionEngine.py — Phase 2

Detects signs that a move is running out of steam, even if structurally
it still looks like a valid breakout. Feeds
aiBrain.MarketSnapshot.exhaustion_detected (bool).

Three independent checks, any of which can flag exhaustion:
  1. Rejection wick — the most recent candle has a long wick against the
     move direction relative to its body (buyers/sellers stepping in).
  2. Momentum divergence — price made a new high/low but the candle-body
     "thrust" is weaker than the prior impulse candle (classic divergence,
     measured directly on price/body data rather than an oscillator).
  3. Volume climax — a volume spike far above average without further
     price progress (blow-off top/bottom signature), when volume data
     is usable.

This module deliberately does NOT use fixed pip thresholds — everything
is relative to the recent candle range/ATR so it works across instruments.
"""

from dataclasses import dataclass
from typing import List, Literal, Optional

from .common import Candle, atr
from .volumeEngine import is_volume_data_usable

Direction = Literal["BUY", "SELL"]


@dataclass
class ExhaustionResult:
    exhaustion_detected: bool
    rejection_wick: bool
    momentum_divergence: bool
    volume_climax: Optional[bool]
    reasons: list


def _rejection_wick(candles: List[Candle], direction: Direction, wick_ratio: float = 1.5) -> bool:
    c = candles[-1]
    body = abs(c.close - c.open)
    if body == 0:
        body = 1e-9
    if direction == "BUY":
        upper_wick = c.high - max(c.open, c.close)
        return upper_wick >= body * wick_ratio
    else:
        lower_wick = min(c.open, c.close) - c.low
        return lower_wick >= body * wick_ratio


def _momentum_divergence(candles: List[Candle], direction: Direction, lookback: int = 5) -> bool:
    """
    Compares the "thrust" (body size relative to range) of the most recent
    candle against the strongest impulse candle earlier in the lookback
    window, while price is still extending in the same direction.
    """
    window = candles[-lookback:]
    latest = window[-1]

    if direction == "BUY":
        made_new_high = latest.high == max(c.high for c in window)
    else:
        made_new_high = latest.low == min(c.low for c in window)

    if not made_new_high:
        return False

    def thrust(c: Candle) -> float:
        rng = c.high - c.low
        return abs(c.close - c.open) / rng if rng else 0.0

    earlier = window[:-1]
    if not earlier:
        return False
    strongest_prior_thrust = max(thrust(c) for c in earlier)
    latest_thrust = thrust(latest)

    return latest_thrust < strongest_prior_thrust * 0.6


def _volume_climax(candles: List[Candle], lookback: int = 20, spike_multiplier: float = 2.5) -> Optional[bool]:
    if not is_volume_data_usable(candles[-(lookback + 1):]):
        return None
    baseline = candles[-(lookback + 1):-1]
    avg_vol = sum(c.volume for c in baseline) / len(baseline)
    if avg_vol == 0:
        return None
    latest = candles[-1]
    price_progress = abs(latest.close - latest.open)
    rng = latest.high - latest.low
    weak_progress = (price_progress / rng < 0.3) if rng else True
    return (latest.volume >= avg_vol * spike_multiplier) and weak_progress


def analyze(candles: List[Candle], direction: Direction) -> ExhaustionResult:
    if len(candles) < 21:
        raise ValueError("Need at least 21 candles for exhaustion analysis")

    reasons = []
    rejection = _rejection_wick(candles, direction)
    if rejection:
        reasons.append("Long rejection wick against move direction on latest candle")

    divergence = _momentum_divergence(candles, direction)
    if divergence:
        reasons.append("New high/low made on weaker thrust than prior impulse candle (divergence)")

    climax = _volume_climax(candles)
    if climax:
        reasons.append("Volume spike with weak price progress (possible climax)")

    detected = rejection or divergence or bool(climax)

    return ExhaustionResult(
        exhaustion_detected=detected,
        rejection_wick=rejection,
        momentum_divergence=divergence,
        volume_climax=climax,
        reasons=reasons,
    )
