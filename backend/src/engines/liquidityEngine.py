"""
liquidityEngine.py — Phase 1

Detects buy-side/sell-side liquidity levels (recent swing high/low) and
whether the current close has swept through one of them. Feeds
aiBrain.MarketSnapshot.liquidity_swept.
"""

from dataclasses import dataclass
from typing import List

from .common import Candle


@dataclass
class LiquidityResult:
    buy_side_liquidity: float   # recent swing high
    sell_side_liquidity: float  # recent swing low
    liquidity_swept: bool
    swept_side: str             # "BUY_SIDE" | "SELL_SIDE" | "NONE"


def analyze(candles: List[Candle], lookback: int = 20) -> LiquidityResult:
    if len(candles) < lookback + 1:
        raise ValueError(f"Need at least {lookback + 1} candles, got {len(candles)}")

    # Exclude the current candle from the level calculation so we're
    # checking whether the CURRENT candle swept a PRIOR level, not
    # including itself in its own reference range.
    reference = candles[-(lookback + 1):-1]
    buy_side = max(c.high for c in reference)
    sell_side = min(c.low for c in reference)

    current = candles[-1]
    swept_buy = current.high > buy_side
    swept_sell = current.low < sell_side

    if swept_buy and not swept_sell:
        swept_side = "BUY_SIDE"
    elif swept_sell and not swept_buy:
        swept_side = "SELL_SIDE"
    elif swept_buy and swept_sell:
        swept_side = "BOTH"
    else:
        swept_side = "NONE"

    return LiquidityResult(
        buy_side_liquidity=buy_side,
        sell_side_liquidity=sell_side,
        liquidity_swept=(swept_side != "NONE"),
        swept_side=swept_side,
    )
