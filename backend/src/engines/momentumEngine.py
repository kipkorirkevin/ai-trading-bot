"""
momentumEngine.py — Phase 2

Produces a normalized momentum score in [0.0, 1.0] that feeds directly into
aiBrain.MarketSnapshot.momentum_score (compared against momentum_required,
default 0.65 per spec section 12).

Momentum here is a blend of three measurable, backtestable components:
  1. Rate of change (ROC) over a short lookback, normalized by ATR
     (so a 10-pip move means something different on a quiet pair vs
     a volatile one)
  2. Candle body strength — average (close-open)/(high-low) over the
     lookback, i.e. how "full-bodied" recent candles are vs wicky/indecisive
  3. Directional consistency — fraction of recent candles that closed
     in the breakout direction

Nothing here predicts the future; it only measures what already happened.
"""

from dataclasses import dataclass
from typing import List, Literal

from .common import Candle, atr

Direction = Literal["BUY", "SELL"]


@dataclass
class MomentumResult:
    score: float                 # normalized 0.0 - 1.0
    roc_component: float
    body_strength_component: float
    consistency_component: float

    def summary(self) -> str:
        return (
            f"Momentum Score: {self.score:.2f}\n"
            f"  ROC component: {self.roc_component:.2f}\n"
            f"  Body strength component: {self.body_strength_component:.2f}\n"
            f"  Directional consistency component: {self.consistency_component:.2f}"
        )


def _roc_component(candles: List[Candle], lookback: int, direction: Direction) -> float:
    window = candles[-lookback:]
    move = window[-1].close - window[0].close
    atr_val = atr(candles, period=max(lookback, 14))
    if atr_val == 0:
        return 0.0
    normalized = move / (atr_val * lookback)  # move per candle, in ATR units
    if direction == "SELL":
        normalized = -normalized
    # squash to 0-1: 0 ATR/candle -> 0.0, 1+ ATR/candle -> 1.0
    return max(0.0, min(1.0, normalized))


def _body_strength_component(candles: List[Candle], lookback: int) -> float:
    window = candles[-lookback:]
    ratios = []
    for c in window:
        rng = c.high - c.low
        if rng == 0:
            continue
        ratios.append(abs(c.close - c.open) / rng)
    if not ratios:
        return 0.0
    return sum(ratios) / len(ratios)


def _consistency_component(candles: List[Candle], lookback: int, direction: Direction) -> float:
    window = candles[-lookback:]
    if direction == "BUY":
        matches = sum(1 for c in window if c.close > c.open)
    else:
        matches = sum(1 for c in window if c.close < c.open)
    return matches / len(window)


def analyze(
    candles: List[Candle],
    direction: Direction,
    lookback: int = 8,
    weights: tuple = (0.5, 0.25, 0.25),
) -> MomentumResult:
    """
    Args:
        candles: full candle history, most recent last. Needs at least
                 lookback + 14 candles (for ATR warmup).
        direction: the proposed trade direction, "BUY" or "SELL" — momentum
                   is directional, not absolute.
        lookback: number of recent candles to evaluate.
        weights: (roc_weight, body_strength_weight, consistency_weight),
                 must sum to 1.0. Not assumed optimal — tune via backtest.
    """
    if len(candles) < lookback + 14:
        raise ValueError(
            f"Need at least {lookback + 14} candles (lookback + ATR warmup), "
            f"got {len(candles)}"
        )
    w_roc, w_body, w_cons = weights
    roc = _roc_component(candles, lookback, direction)
    body = _body_strength_component(candles, lookback)
    cons = _consistency_component(candles, lookback, direction)

    score = w_roc * roc + w_body * body + w_cons * cons
    return MomentumResult(
        score=max(0.0, min(1.0, score)),
        roc_component=roc,
        body_strength_component=body,
        consistency_component=cons,
    )
