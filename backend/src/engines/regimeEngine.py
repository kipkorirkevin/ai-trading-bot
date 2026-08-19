"""
regimeEngine.py — Phase 2

Classifies the market into TRENDING / RANGING / WEAK / REVERSAL per spec
section 7. Feeds aiBrain.MarketSnapshot.market_regime.

Bug fix vs. the pasted version: that version could return "REVERSAL" purely
because smc_bias=="NEUTRAL", which conflates "no clear bias" with "an
active reversal happened" — those are different things. Here, REVERSAL
requires an explicit opposing BOS/CHoCH against the prior established bias,
matching spec section 7's definition (opposite BOS/CHoCH, strong rejection,
liquidity reversal).
"""

from dataclasses import dataclass
from typing import List, Literal, Optional

from .common import Candle, atr, sma

Regime = Literal["TRENDING", "RANGING", "WEAK", "REVERSAL"]


@dataclass
class RegimeResult:
    regime: Regime
    trend_slope_pct: float
    atr_ratio: float
    management: str   # "TREND" | "DEFENSIVE" | "EXIT" | "RANGE"


def analyze(
    candles: List[Candle],
    momentum_score: float,
    fakeout_probability: float,
    prior_bias: str,        # "BUY" | "SELL" | "NEUTRAL" — from the prior SMC read
    current_bias: str,      # this cycle's SMC bias
    reversal_confirmed: bool,  # explicit opposing BOS/CHoCH flag from smcEngine, not inferred
) -> RegimeResult:
    if len(candles) < 51:
        raise ValueError("Need at least 51 candles for regime analysis")

    closes = [c.close for c in candles]
    ma_short = sma(closes, 10)
    ma_long = sma(closes, 50)
    slope = (ma_short - ma_long) / ma_long if ma_long else 0.0

    atr_val = atr(candles, period=14)
    avg_price = sma(closes, 50)
    atr_ratio = atr_val / avg_price if avg_price else 0.0

    # REVERSAL requires an explicit opposing structural break against the
    # established bias — not just "no bias this cycle."
    if reversal_confirmed and prior_bias in ("BUY", "SELL") and current_bias != prior_bias and current_bias != "NEUTRAL":
        return RegimeResult(regime="REVERSAL", trend_slope_pct=slope, atr_ratio=atr_ratio, management="EXIT")

    if abs(slope) > 0.01 and momentum_score > 0.6 and fakeout_probability < 30:
        return RegimeResult(regime="TRENDING", trend_slope_pct=slope, atr_ratio=atr_ratio, management="TREND")

    if abs(slope) < 0.003 and atr_ratio < 0.01:
        return RegimeResult(regime="RANGING", trend_slope_pct=slope, atr_ratio=atr_ratio, management="RANGE")

    return RegimeResult(regime="WEAK", trend_slope_pct=slope, atr_ratio=atr_ratio, management="DEFENSIVE")
