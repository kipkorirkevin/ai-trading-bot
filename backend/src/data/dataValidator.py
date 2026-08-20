"""
dataValidator.py — Phase 1 (Market Data Engine)

Spec section 31: "market data unreliable" is one of the explicit Risk
Firewall block conditions (spec section 15). This module is what actually
produces that signal — before this existed, riskFirewall.AccountState.market_data_stale
was always hardcoded False in main.py, meaning that protection was wired
but never actually connected to anything real. This closes that gap.

Checks performed on a candle series:
    - non-monotonic or duplicate timestamps
    - gaps larger than expected for the timeframe (missing candles)
    - invalid OHLC relationships (high < low, high/low not bracketing open/close)
    - non-finite or non-positive prices
    - staleness (latest candle too old relative to the current time and timeframe)
"""

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "engines"))
from common import Candle, TIMEFRAME_SECONDS  # noqa: E402


@dataclass
class ValidationResult:
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    duplicate_count: int = 0
    gap_count: int = 0
    invalid_ohlc_count: int = 0
    is_stale: bool = False
    latest_age_seconds: Optional[float] = None


def _valid_ohlc(c: Candle) -> bool:
    if any(not math.isfinite(v) for v in (c.open, c.high, c.low, c.close)):
        return False
    if c.open <= 0 or c.high <= 0 or c.low <= 0 or c.close <= 0:
        return False
    if c.high < c.low:
        return False
    if c.high < c.open or c.high < c.close:
        return False
    if c.low > c.open or c.low > c.close:
        return False
    return True


def validate(
    candles: List[Candle],
    timeframe: Optional[str] = None,
    gap_tolerance_multiplier: float = 1.5,
    staleness_multiplier: float = 3.0,
    now: Optional[float] = None,
) -> ValidationResult:
    """
    Args:
        candles: series to validate, oldest first (matches engines.common convention).
        timeframe: e.g. "M15" — enables gap and staleness checks against the
                   expected candle interval. Without it, only structural
                   checks (duplicates, invalid OHLC) run.
        gap_tolerance_multiplier: a gap is flagged if the time between
                   consecutive candles exceeds interval * this multiplier.
        staleness_multiplier: data is considered stale if the newest
                   candle is older than interval * this multiplier.
        now: injectable current time for testing; defaults to time.time().
    """
    issues: List[str] = []
    if not candles:
        return ValidationResult(is_valid=False, issues=["No candles provided"], is_stale=True)

    now = now if now is not None else time.time()
    interval = TIMEFRAME_SECONDS.get(timeframe) if timeframe else None

    seen_timestamps = set()
    duplicate_count = 0
    invalid_ohlc_count = 0
    gap_count = 0

    prev_ts = None
    for c in candles:
        if c.timestamp in seen_timestamps:
            duplicate_count += 1
        seen_timestamps.add(c.timestamp)

        if not _valid_ohlc(c):
            invalid_ohlc_count += 1

        if prev_ts is not None:
            if c.timestamp <= prev_ts:
                issues.append(f"Non-monotonic timestamp at index (prev={prev_ts}, cur={c.timestamp})")
            elif interval is not None and (c.timestamp - prev_ts) > interval * gap_tolerance_multiplier:
                gap_count += 1
        prev_ts = c.timestamp

    if duplicate_count:
        issues.append(f"{duplicate_count} duplicate timestamp(s)")
    if invalid_ohlc_count:
        issues.append(f"{invalid_ohlc_count} candle(s) with invalid OHLC relationships")
    if gap_count:
        issues.append(f"{gap_count} gap(s) larger than {gap_tolerance_multiplier}x the expected interval")

    latest_age = now - candles[-1].timestamp
    stale = False
    if interval is not None:
        stale = latest_age > interval * staleness_multiplier
        if stale:
            issues.append(
                f"Latest candle is {latest_age:.0f}s old, exceeding staleness threshold "
                f"of {interval * staleness_multiplier:.0f}s for {timeframe}"
            )

    is_valid = (
        duplicate_count == 0 and invalid_ohlc_count == 0 and not stale
        and not any("Non-monotonic" in i for i in issues)
    )

    return ValidationResult(
        is_valid=is_valid, issues=issues, duplicate_count=duplicate_count,
        gap_count=gap_count, invalid_ohlc_count=invalid_ohlc_count,
        is_stale=stale, latest_age_seconds=latest_age,
    )
