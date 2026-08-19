"""
positionSizer.py — Phase 4/5 (spec section 16)

Risk-percent based position sizing. Bug fix vs. the pasted version: that
version's pip-value formula (`stop_loss_pips * 0.0001 * 100000`) hardcodes
a forex-style pip value and unit lot size that doesn't hold for crypto or
indices — it silently produces wrong sizes on any non-forex-standard
instrument. Here, the caller supplies pip_value directly (looked up per
instrument from the broker), which is the only way to get this right
across asset classes.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class PositionSizerConfig:
    lot_type: Literal["FIXED", "RISK_PERCENT"] = "RISK_PERCENT"
    fixed_lot: float = 0.01
    risk_per_trade_pct: float = 1.0
    min_lot: float = 0.01
    max_lot: float = 1.0
    lot_step: float = 0.01


def _round_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return round(round(value / step) * step, 8)


def calculate(
    config: PositionSizerConfig,
    balance: float,
    stop_loss_distance: float,   # price distance (not pips) between entry and SL
    pip_value_per_lot: float,    # account-currency value of 1 pip for 1.0 lot on this instrument
    pip_size: float,             # price distance representing 1 pip on this instrument
) -> float:
    if config.lot_type == "FIXED":
        return _round_to_step(config.fixed_lot, config.lot_step)

    if stop_loss_distance <= 0 or pip_value_per_lot <= 0 or pip_size <= 0:
        # Can't size safely without real distances — fail to minimum lot
        # rather than guessing, since guessing here risks over-leveraging.
        return config.min_lot

    risk_amount = balance * (config.risk_per_trade_pct / 100)
    sl_pips = stop_loss_distance / pip_size
    lot = risk_amount / (sl_pips * pip_value_per_lot)

    lot = max(config.min_lot, min(lot, config.max_lot))
    return _round_to_step(lot, config.lot_step)
