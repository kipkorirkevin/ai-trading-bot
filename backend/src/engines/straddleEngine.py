"""
straddleEngine.py — Phase 1 (spec section 5)

Detects consolidation/ranges and, when a valid range exists, produces a
straddle setup: range high/low, a breakout buffer (so pending orders don't
trigger on noise), and a choice between TWO_SIDED (place both buy-stop and
sell-stop) or DIRECTIONAL (place only the HTF-bias-aligned side, per spec
section 5 point 6: "SMC bias determines which side receives priority").

This module does NOT place orders — it produces a StraddleSetup that
executionRouter.execute() consumes with setup_type="STRADDLE". Cancelling
the opposite side once one triggers (spec section 5 point 8) and expiring
stale pending orders (point 10) are execution-time concerns handled by
whoever holds the order state (main.py's orchestrator loop / a future
position manager), not by this stateless analysis function — this module
only tells you what a valid setup looks like, once.
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional

from .common import Candle, atr

SetupType = Literal["TWO_SIDED", "DIRECTIONAL", "NONE"]
Side = Literal["BUY", "SELL"]


@dataclass
class RangeInfo:
    is_ranging: bool
    range_high: float
    range_low: float
    range_width: float
    atr_value: float
    width_to_atr_ratio: float


@dataclass
class StraddleSetup:
    valid: bool
    setup_type: SetupType
    range_high: float = 0.0
    range_low: float = 0.0
    buy_trigger: float = 0.0
    sell_trigger: float = 0.0
    breakout_buffer: float = 0.0
    priority_side: Optional[Side] = None   # set only for DIRECTIONAL
    suggested_expiry_candles: int = 20      # spec 5.10: cancel stale pending orders
    reasons: List[str] = field(default_factory=list)


def detect_range(
    candles: List[Candle],
    lookback: int = 20,
    max_width_atr_ratio: float = 6.0,
    min_width_atr_ratio: float = 1.0,
) -> RangeInfo:
    """
    A valid range is tight relative to volatility (width_to_atr_ratio below
    max_width_atr_ratio) but not so tight it's dead/illiquid noise
    (above min_width_atr_ratio) — spec section 5 implies both: a real
    consolidation, not a trend, and not a market with no meaningful range
    to break out of.

    Thresholds are calibrated against measured behavior, not guessed: a
    20-candle lookback range naturally runs several multiples of a
    single-candle ATR even in genuine consolidation (empirically ~3-4x on
    synthetic mean-reverting data), while genuine trends separate clearly
    higher (~10x+). These defaults reflect that measured gap — re-verify
    against real market data before relying on them, since synthetic data
    only proves the mechanism works, not the exact real-world cutoff.
    """
    if len(candles) < max(lookback, 15) + 1:
        raise ValueError(f"Need at least {max(lookback, 15) + 1} candles, got {len(candles)}")

    window = candles[-lookback:]
    range_high = max(c.high for c in window)
    range_low = min(c.low for c in window)
    width = range_high - range_low

    atr_val = atr(candles, period=14)
    ratio = width / atr_val if atr_val else float("inf")

    is_ranging = min_width_atr_ratio <= ratio <= max_width_atr_ratio

    return RangeInfo(
        is_ranging=is_ranging, range_high=range_high, range_low=range_low,
        range_width=width, atr_value=atr_val, width_to_atr_ratio=ratio,
    )


def analyze(
    candles: List[Candle],
    mtf_alignment_score: float,
    mtf_dominant_direction: str,     # "BUY" | "SELL" | "NEUTRAL"
    spread_ok: bool = True,
    lookback: int = 20,
    breakout_buffer_atr_mult: float = 0.15,
    directional_alignment_threshold: float = 65.0,
    max_width_atr_ratio: float = 6.0,
    min_width_atr_ratio: float = 1.0,
) -> StraddleSetup:
    reasons: List[str] = []

    if not spread_ok:
        return StraddleSetup(valid=False, setup_type="NONE", reasons=["Spread abnormal — straddle setup rejected"])

    range_info = detect_range(candles, lookback, max_width_atr_ratio, min_width_atr_ratio)

    if not range_info.is_ranging:
        if range_info.width_to_atr_ratio > max_width_atr_ratio:
            reasons.append(
                f"Range too wide relative to volatility "
                f"({range_info.width_to_atr_ratio:.2f}x ATR > {max_width_atr_ratio}x) — likely trending, not ranging"
            )
        else:
            reasons.append(
                f"Range too tight relative to volatility "
                f"({range_info.width_to_atr_ratio:.2f}x ATR < {min_width_atr_ratio}x) — insufficient room to trade"
            )
        return StraddleSetup(valid=False, setup_type="NONE", reasons=reasons)

    buffer = range_info.atr_value * breakout_buffer_atr_mult
    buy_trigger = range_info.range_high + buffer
    sell_trigger = range_info.range_low - buffer

    if mtf_alignment_score >= directional_alignment_threshold and mtf_dominant_direction in ("BUY", "SELL"):
        setup_type: SetupType = "DIRECTIONAL"
        priority_side: Optional[Side] = mtf_dominant_direction  # type: ignore
        reasons.append(
            f"MTF alignment {mtf_alignment_score:.0f} >= {directional_alignment_threshold:.0f} threshold — "
            f"directional straddle, {mtf_dominant_direction} side prioritized"
        )
    else:
        setup_type = "TWO_SIDED"
        priority_side = None
        reasons.append(
            f"MTF alignment {mtf_alignment_score:.0f} below {directional_alignment_threshold:.0f} threshold — "
            f"two-sided straddle, no directional bias strong enough to prioritize"
        )

    reasons.append(
        f"Range detected: {range_info.range_low:.5f} - {range_info.range_high:.5f} "
        f"({range_info.width_to_atr_ratio:.2f}x ATR)"
    )

    return StraddleSetup(
        valid=True, setup_type=setup_type,
        range_high=range_info.range_high, range_low=range_info.range_low,
        buy_trigger=buy_trigger, sell_trigger=sell_trigger, breakout_buffer=buffer,
        priority_side=priority_side, reasons=reasons,
    )


def opposite_side(side: Side) -> Side:
    """Spec 5.8: when one side of a straddle triggers, cancel the opposite
    pending order. Small helper so callers don't hand-roll this."""
    return "SELL" if side == "BUY" else "BUY"
