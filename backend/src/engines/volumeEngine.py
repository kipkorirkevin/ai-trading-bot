"""
volumeEngine.py — Phase 2

Per spec section 13: volume confirmation must NOT be treated as mandatory
on instruments where volume data is unsuitable (e.g. most retail forex
feeds report tick volume, not real traded volume — still usable as a
relative signal, but spot/CFD instruments with all-zero volume are not).

Feeds aiBrain.MarketSnapshot.volume_confirmed, which is Optional[bool]:
    True  -> volume supports the move
    False -> volume contradicts/fails to support the move
    None  -> data unreliable for this instrument, AI Brain skips this factor
"""

from dataclasses import dataclass
from typing import List, Optional

from .common import Candle, sma


@dataclass
class VolumeResult:
    confirmed: Optional[bool]
    current_volume: float
    average_volume: float
    ratio: Optional[float]
    reason: str


def is_volume_data_usable(candles: List[Candle], min_nonzero_fraction: float = 0.9) -> bool:
    """
    Heuristic: if most recent candles report zero/missing volume, this
    instrument's feed can't be trusted for volume analysis.
    """
    if not candles:
        return False
    nonzero = sum(1 for c in candles if c.volume and c.volume > 0)
    return (nonzero / len(candles)) >= min_nonzero_fraction


def analyze(
    candles: List[Candle],
    lookback: int = 20,
    breakout_multiplier: float = 1.5,
) -> VolumeResult:
    """
    Args:
        candles: candle history, most recent last, needs at least lookback+1.
        lookback: window for the average volume baseline (excludes the
                  current/breakout candle).
        breakout_multiplier: current candle's volume must exceed
                  (average * breakout_multiplier) to count as confirmed.
    """
    if len(candles) < lookback + 1:
        raise ValueError(f"Need at least {lookback + 1} candles, got {len(candles)}")

    if not is_volume_data_usable(candles[-(lookback + 1):]):
        return VolumeResult(
            confirmed=None,
            current_volume=candles[-1].volume,
            average_volume=0.0,
            ratio=None,
            reason="Volume data unreliable for this instrument (mostly zero/missing) — skipped",
        )

    baseline_candles = candles[-(lookback + 1):-1]
    avg_volume = sma([c.volume for c in baseline_candles], lookback)
    current_volume = candles[-1].volume

    if avg_volume == 0:
        return VolumeResult(
            confirmed=None,
            current_volume=current_volume,
            average_volume=avg_volume,
            ratio=None,
            reason="Average volume is zero — cannot compute a meaningful ratio",
        )

    ratio = current_volume / avg_volume
    confirmed = ratio >= breakout_multiplier
    reason = (
        f"Current volume is {ratio:.2f}x the {lookback}-candle average "
        f"({'meets' if confirmed else 'below'} {breakout_multiplier}x threshold)"
    )
    return VolumeResult(
        confirmed=confirmed,
        current_volume=current_volume,
        average_volume=avg_volume,
        ratio=ratio,
        reason=reason,
    )
