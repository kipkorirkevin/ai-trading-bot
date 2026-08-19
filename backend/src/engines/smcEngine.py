"""
smcEngine.py — Phase 1

Real BOS/CHoCH/FVG/Order Block detection on the shared Candle type
(common.py), replacing the earlier NotImplementedError stub.

Field names in SMCResult are chosen to map 1:1 onto
engines.aiBrain.MarketSnapshot (bos_confirmed, choch_confirmed,
order_block_present, fvg_present, displacement_present) so wiring this
into the AI Brain is a direct assignment, no translation layer needed.
"""

from dataclasses import dataclass, field
from typing import List, Literal

from .common import Candle

Bias = Literal["BUY", "SELL", "NEUTRAL"]


@dataclass
class FVG:
    kind: Literal["BULLISH", "BEARISH"]
    low: float
    high: float
    index: int


@dataclass
class OrderBlock:
    kind: Literal["BULLISH", "BEARISH"]
    high: float
    low: float
    index: int


@dataclass
class SMCResult:
    bias: Bias
    bos_confirmed: bool
    choch_confirmed: bool
    displacement_present: bool
    fvgs: List[FVG] = field(default_factory=list)
    order_blocks: List[OrderBlock] = field(default_factory=list)
    recent_high: float = 0.0
    recent_low: float = 0.0

    @property
    def fvg_present(self) -> bool:
        return len(self.fvgs) > 0

    @property
    def order_block_present(self) -> bool:
        return len(self.order_blocks) > 0


def _identify_bos(candles: List[Candle]) -> str:
    """BOS = higher high AND higher low than the prior candle (or the reverse)."""
    if len(candles) < 2:
        return "NONE"
    a, b = candles[-2], candles[-1]
    if b.high > a.high and b.low > a.low:
        return "UP"
    if b.high < a.high and b.low < a.low:
        return "DOWN"
    return "NONE"


def _identify_choch(candles: List[Candle]) -> str:
    """
    CHoCH = a shift in which extreme is advancing. Bug fixed vs the pasted
    version: compares to a swing 3 candles back, not overlapping BOS logic.
    """
    if len(candles) < 4:
        return "NONE"
    recent = candles[-4:]
    if recent[-1].low > recent[0].low and recent[-1].high > recent[-2].high:
        return "UP"
    if recent[-1].high < recent[0].high and recent[-1].low < recent[-2].low:
        return "DOWN"
    return "NONE"


def _find_fvgs(candles: List[Candle], min_gap_pct: float = 0.0005, max_results: int = 5) -> List[FVG]:
    fvgs = []
    for i in range(2, len(candles)):
        c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
        if c3.low > c1.high:
            gap_pct = (c3.low - c1.high) / c1.high if c1.high else 0
            if gap_pct >= min_gap_pct:
                fvgs.append(FVG(kind="BULLISH", low=c1.high, high=c3.low, index=i))
        elif c3.high < c1.low:
            gap_pct = (c1.low - c3.high) / c1.low if c1.low else 0
            if gap_pct >= min_gap_pct:
                fvgs.append(FVG(kind="BEARISH", low=c3.high, high=c1.low, index=i))
    return fvgs[-max_results:]


def _find_order_blocks(candles: List[Candle], max_results: int = 5) -> List[OrderBlock]:
    """
    An order block is the last down-candle before a strong up-move (bullish OB)
    or the last up-candle before a strong down-move (bearish OB), where the
    follow-through move is at least 2x the OB candle's own body.
    """
    blocks = []
    for i in range(3, len(candles) - 1):
        origin = candles[i - 3]
        followthrough = candles[i]
        origin_body = origin.close - origin.open
        followthrough_body = followthrough.close - followthrough.open

        if origin_body < 0 and followthrough_body > abs(origin_body) * 2:
            blocks.append(OrderBlock(kind="BULLISH", high=origin.high, low=origin.low, index=i - 3))
        elif origin_body > 0 and followthrough_body < -abs(origin_body) * 2:
            blocks.append(OrderBlock(kind="BEARISH", high=origin.high, low=origin.low, index=i - 3))
    return blocks[-max_results:]


def _displacement_present(candles: List[Candle], lookback: int = 5, body_multiplier: float = 1.8) -> bool:
    window = candles[-lookback:]
    if len(window) < 2:
        return False
    bodies = [abs(c.close - c.open) for c in window[:-1]]
    avg_body = sum(bodies) / len(bodies) if bodies else 0
    latest_body = abs(window[-1].close - window[-1].open)
    return avg_body > 0 and latest_body >= avg_body * body_multiplier


def analyze(candles: List[Candle]) -> SMCResult:
    if len(candles) < 10:
        raise ValueError("Need at least 10 candles for SMC analysis")

    bos = _identify_bos(candles)
    choch = _identify_choch(candles)

    if bos == "UP" or choch == "UP":
        bias: Bias = "BUY"
    elif bos == "DOWN" or choch == "DOWN":
        bias = "SELL"
    else:
        bias = "NEUTRAL"

    highs = [c.high for c in candles[-20:]]
    lows = [c.low for c in candles[-20:]]

    return SMCResult(
        bias=bias,
        bos_confirmed=(bos != "NONE"),
        choch_confirmed=(choch != "NONE"),
        displacement_present=_displacement_present(candles),
        fvgs=_find_fvgs(candles),
        order_blocks=_find_order_blocks(candles),
        recent_high=max(highs),
        recent_low=min(lows),
    )
