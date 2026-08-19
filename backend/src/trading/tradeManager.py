"""
tradeManager.py — Phase 5 (spec sections 17-20)

Deterministic SL/TP/BE/trailing calculation. Per spec section 21, the AI
Brain decides regime-based *strategy* (Trend/Defensive/Exit management) —
this module performs the actual price-level math, so it's the only place
that touches SL/TP numbers.

Bug fix vs. the pasted version: that version's `apply_be_and_trail` moved
SL to break-even immediately on grazing +1R with no confirmation, and its
trailing could move SL the wrong direction if `structure["recent_low"]`
was stale/behind the current SL. Here, trailing always validates the new
SL is actually an improvement (tighter, never looser) before applying it,
and BE only fires once (`be_applied` flag), matching spec section 19's
"do not activate break-even immediately after entry" requirement via an
explicit trigger distance rather than any move in profit.
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional

Direction = Literal["BUY", "SELL"]


@dataclass
class TradeManagerConfig:
    sl_method: Literal["ATR", "STRUCTURE", "FIXED"] = "ATR"
    atr_multiplier: float = 1.5
    be_trigger_r: float = 1.0        # move to BE once price advances this many R
    be_offset_r: float = 0.1         # lock in this many R of profit at BE (buffer)
    trail_trigger_r: float = 1.5     # start trailing once price advances this many R
    trail_atr_buffer: float = 0.3    # ATR buffer behind structure when trailing
    tp_r_multiples: List[float] = field(default_factory=lambda: [1.0, 2.0, 3.0])


@dataclass
class Position:
    entry: float
    direction: Direction
    sl: float
    tp_levels: List[float]
    be_applied: bool = False
    initial_risk: float = 0.0   # abs(entry - initial_sl), fixed at open — never recalculated

    def __post_init__(self):
        if self.initial_risk == 0.0:
            self.initial_risk = abs(self.entry - self.sl)


def set_initial_sl_tp(
    config: TradeManagerConfig,
    entry: float,
    direction: Direction,
    atr_value: float,
    structure_high: Optional[float] = None,
    structure_low: Optional[float] = None,
    fixed_distance: Optional[float] = None,
) -> Position:
    if config.sl_method == "ATR":
        distance = atr_value * config.atr_multiplier
        sl = entry - distance if direction == "BUY" else entry + distance
    elif config.sl_method == "STRUCTURE":
        if structure_high is None or structure_low is None:
            raise ValueError("STRUCTURE sl_method requires structure_high and structure_low")
        buffer = atr_value * 0.2
        sl = structure_low - buffer if direction == "BUY" else structure_high + buffer
    elif config.sl_method == "FIXED":
        if fixed_distance is None:
            raise ValueError("FIXED sl_method requires fixed_distance")
        sl = entry - fixed_distance if direction == "BUY" else entry + fixed_distance
    else:
        raise ValueError(f"Unknown sl_method: {config.sl_method}")

    risk = abs(entry - sl)
    if direction == "BUY":
        tps = [entry + risk * r for r in config.tp_r_multiples]
    else:
        tps = [entry - risk * r for r in config.tp_r_multiples]

    return Position(entry=entry, direction=direction, sl=sl, tp_levels=tps, initial_risk=risk)


def apply_be_and_trail(
    config: TradeManagerConfig,
    position: Position,
    current_price: float,
    atr_value: float,
    structure_recent_high: Optional[float] = None,
    structure_recent_low: Optional[float] = None,
) -> Position:
    """
    Mutates and returns `position` with an updated SL if BE or trailing
    conditions are met. Always validates that any SL change is a genuine
    tightening — never widens risk.
    """
    risk = position.initial_risk
    if risk <= 0:
        return position

    if position.direction == "BUY":
        advance_r = (current_price - position.entry) / risk

        if not position.be_applied and advance_r >= config.be_trigger_r:
            be_sl = position.entry + risk * config.be_offset_r
            if be_sl > position.sl:
                position.sl = be_sl
                position.be_applied = True

        if advance_r >= config.trail_trigger_r and structure_recent_low is not None:
            candidate_sl = structure_recent_low - atr_value * config.trail_atr_buffer
            if candidate_sl > position.sl:
                position.sl = candidate_sl

    else:  # SELL
        advance_r = (position.entry - current_price) / risk

        if not position.be_applied and advance_r >= config.be_trigger_r:
            be_sl = position.entry - risk * config.be_offset_r
            if be_sl < position.sl:
                position.sl = be_sl
                position.be_applied = True

        if advance_r >= config.trail_trigger_r and structure_recent_high is not None:
            candidate_sl = structure_recent_high + atr_value * config.trail_atr_buffer
            if candidate_sl < position.sl:
                position.sl = candidate_sl

    return position
