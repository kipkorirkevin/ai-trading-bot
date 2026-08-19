"""Tier 1: core strategy engines. No credentials, no network."""

import sys
import os
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend", "src"))

from engines.common import Candle
from engines import smcEngine, liquidityEngine, momentumEngine, volumeEngine, exhaustionEngine, mtfEngine, straddleEngine
from engines.aiBrain import AIBrain, MarketSnapshot, MarketRegime, Direction


def _trending_candles(n=120, seed=1, drift=0.0006):
    rnd = random.Random(seed)
    candles, price = [], 1.10000
    for i in range(n):
        o = price
        c = o + rnd.uniform(-0.0003, 0.0005) + drift
        h = max(o, c) + rnd.uniform(0, 0.0003)
        l = min(o, c) - rnd.uniform(0, 0.0002)
        candles.append(Candle(timestamp=i, open=o, high=h, low=l, close=c, volume=rnd.uniform(800, 1500)))
        price = c
    return candles


def test_smc_bias_matches_trend_direction():
    candles = _trending_candles(drift=0.0008)
    result = smcEngine.analyze(candles)
    assert result.bias in ("BUY", "SELL", "NEUTRAL")
    # strong upward drift should not produce a SELL bias
    assert result.bias != "SELL"


def test_liquidity_result_has_valid_levels():
    candles = _trending_candles()
    result = liquidityEngine.analyze(candles)
    assert result.sell_side_liquidity <= result.buy_side_liquidity
    assert result.swept_side in ("BUY_SIDE", "SELL_SIDE", "BOTH", "NONE")


def test_momentum_score_bounded():
    candles = _trending_candles()
    result = momentumEngine.analyze(candles, direction="BUY")
    assert 0.0 <= result.score <= 1.0


def test_volume_returns_none_when_data_unreliable():
    candles = [
        Candle(timestamp=i, open=1.1, high=1.101, low=1.099, close=1.1005, volume=0.0)
        for i in range(30)
    ]
    result = volumeEngine.analyze(candles)
    assert result.confirmed is None  # must not silently become False


def test_exhaustion_result_is_boolean():
    candles = _trending_candles()
    result = exhaustionEngine.analyze(candles, direction="BUY")
    assert isinstance(result.exhaustion_detected, bool)


def test_mtf_alignment_full_agreement_scores_100():
    candles = _trending_candles(drift=0.001)
    result = mtfEngine.analyze({"H4": candles, "H1": candles, "M15": candles, "M5": candles, "M1": candles})
    # identical series across all timeframes -> identical bias -> full alignment
    assert result.alignment_score == 100.0 or result.dominant_direction == "NEUTRAL"


def test_ai_brain_never_forces_a_trade_on_weak_evidence():
    """Spec section 34: the AI must be able to say NO TRADE even after a breakout."""
    snap = MarketSnapshot(
        symbol="EURUSD", h4_bias="BUY", h1_bias="SELL", m15_structure="NEUTRAL",
        m5_structure="BUY", m1_setup="BUY",
        liquidity_swept=False, bos_confirmed=False, choch_confirmed=False,
        order_block_present=False, fvg_present=False, displacement_present=False,
        breakout_detected=True, retest_status="FAILED",
        momentum_score=0.2, momentum_required=0.65, volume_confirmed=False,
        fakeout_probability=80.0, exhaustion_detected=True,
        market_regime=MarketRegime.WEAK, session_active=True, spread_ok=True, atr_ok=True,
    )
    decision = AIBrain().evaluate(snap)
    assert decision.direction in (Direction.NO_TRADE, Direction.WAIT)


def test_ai_brain_approves_clean_high_confidence_setup():
    snap = MarketSnapshot(
        symbol="EURUSD", h4_bias="BUY", h1_bias="BUY", m15_structure="BUY",
        m5_structure="BUY", m1_setup="BUY",
        liquidity_swept=True, bos_confirmed=True, choch_confirmed=False,
        order_block_present=True, fvg_present=True, displacement_present=True,
        breakout_detected=True, retest_status="PASSED",
        momentum_score=0.75, momentum_required=0.65, volume_confirmed=True,
        fakeout_probability=15.0, exhaustion_detected=False,
        market_regime=MarketRegime.TRENDING, session_active=True, spread_ok=True, atr_ok=True,
    )
    decision = AIBrain().evaluate(snap)
    assert decision.direction == Direction.BUY
    assert decision.confidence >= 75


def _ranging_candles(n=60, seed=5):
    rnd = random.Random(seed)
    candles, price = [], 1.10000
    for i in range(n):
        o = price
        c = 1.10000 + rnd.uniform(-0.0012, 0.0012)
        h = max(o, c) + rnd.uniform(0, 0.0002)
        l = min(o, c) - rnd.uniform(0, 0.0002)
        candles.append(Candle(timestamp=i, open=o, high=h, low=l, close=c, volume=rnd.uniform(800, 1200)))
        price = c
    return candles


def test_straddle_detects_range_as_ranging():
    candles = _ranging_candles()
    info = straddleEngine.detect_range(candles, lookback=20)
    assert info.is_ranging is True


def test_straddle_rejects_trending_market():
    candles = _trending_candles(drift=0.0009)
    result = straddleEngine.analyze(candles, mtf_alignment_score=90, mtf_dominant_direction="BUY")
    assert result.valid is False
    assert result.setup_type == "NONE"


def test_straddle_two_sided_on_weak_alignment():
    candles = _ranging_candles()
    result = straddleEngine.analyze(candles, mtf_alignment_score=40, mtf_dominant_direction="BUY")
    assert result.valid is True
    assert result.setup_type == "TWO_SIDED"
    assert result.priority_side is None
    assert result.sell_trigger < result.buy_trigger


def test_straddle_directional_on_strong_alignment():
    candles = _ranging_candles()
    result = straddleEngine.analyze(candles, mtf_alignment_score=80, mtf_dominant_direction="SELL")
    assert result.valid is True
    assert result.setup_type == "DIRECTIONAL"
    assert result.priority_side == "SELL"


def test_straddle_rejects_abnormal_spread():
    candles = _ranging_candles()
    result = straddleEngine.analyze(candles, mtf_alignment_score=80, mtf_dominant_direction="BUY", spread_ok=False)
    assert result.valid is False


def test_straddle_opposite_side_helper():
    assert straddleEngine.opposite_side("BUY") == "SELL"
    assert straddleEngine.opposite_side("SELL") == "BUY"


if __name__ == "__main__":
    # Manual runner for environments without pytest installed.
    import inspect
    tests = [f for name, f in list(globals().items()) if name.startswith("test_") and inspect.isfunction(f)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS: {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed")
