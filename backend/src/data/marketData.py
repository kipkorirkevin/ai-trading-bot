"""
marketData.py — Phase 1 (Market Data Engine)

Sits between any BaseBrokerAdapter and the strategy engines. Broker-
agnostic by construction — takes a BaseBrokerAdapter instance and never
imports a specific broker. Responsibilities:

    1. Fetch candles for multiple timeframes in one call (H4/H1/M15/M5/M1),
       replacing the ad-hoc single-timeframe fetch main.py used to do
       manually.
    2. Short-TTL caching so a burst of engine calls within the same cycle
       doesn't hit the broker N times for the same data.
    3. Run every fetch through dataValidator.py and surface the result —
       callers (main.py) use this to actually populate
       riskFirewall.AccountState.market_data_stale, which was previously
       always hardcoded False.

This module does NOT know how to open a websocket or poll a terminal —
that's each broker adapter's job (spec section 31's connection
monitoring/heartbeat/reconnect lives in the adapter, e.g. via
websocketManager.py's generic helper). This module only consumes
adapter.get_market_data() and adapter.heartbeat().
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "engines"))
from common import Candle  # noqa: E402

sys.path.append(os.path.dirname(__file__))
from dataValidator import ValidationResult, validate  # noqa: E402

from brokers.baseAdapter import BaseBrokerAdapter


@dataclass
class FetchResult:
    candles: List[Candle]
    validation: ValidationResult
    from_cache: bool


class MarketDataEngine:
    def __init__(self, broker: BaseBrokerAdapter, cache_ttl_seconds: float = 5.0):
        self.broker = broker
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Dict[Tuple[str, str, int], Tuple[float, List[Candle]]] = {}

    def _fetch_raw(self, symbol: str, timeframe: str, limit: int) -> Tuple[List[Candle], bool]:
        cache_key = (symbol, timeframe, limit)
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached is not None and (now - cached[0]) < self.cache_ttl_seconds:
            return cached[1], True

        raw = self.broker.get_market_data(symbol, timeframe, limit)
        candles = [
            Candle(
                timestamp=c["timestamp"], open=c["open"], high=c["high"],
                low=c["low"], close=c["close"], volume=c.get("volume", 0.0),
            )
            for c in raw
        ]
        self._cache[cache_key] = (now, candles)
        return candles, False

    def get_candles(
        self, symbol: str, timeframe: str, limit: int = 120, run_validation: bool = True,
    ) -> FetchResult:
        candles, from_cache = self._fetch_raw(symbol, timeframe, limit)
        validation = (
            validate(candles, timeframe=timeframe) if run_validation
            else ValidationResult(is_valid=True)
        )
        return FetchResult(candles=candles, validation=validation, from_cache=from_cache)

    def get_multi_timeframe(
        self, symbol: str, timeframe_map: Dict[str, str], limit: int = 120,
    ) -> Dict[str, FetchResult]:
        """
        Args:
            timeframe_map: e.g. {"h4": "H4", "h1": "H1", "m15": "M15",
                                  "m5": "M5", "m1": "M1"} — matches
                                  config.json's "timeframes" block.
        Returns one FetchResult per label in timeframe_map.
        """
        return {label: self.get_candles(symbol, tf, limit) for label, tf in timeframe_map.items()}

    def any_stale_or_invalid(self, results: Dict[str, FetchResult]) -> Tuple[bool, List[str]]:
        """Convenience for main.py: checks a multi-timeframe fetch and
        returns (should_block, reasons) for feeding into
        riskFirewall.AccountState.market_data_stale."""
        reasons = []
        for label, result in results.items():
            if not result.validation.is_valid:
                reasons.append(f"{label}: {'; '.join(result.validation.issues)}")
        return (len(reasons) > 0, reasons)

    def clear_cache(self):
        self._cache.clear()
