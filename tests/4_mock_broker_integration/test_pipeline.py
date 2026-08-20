"""Tier 4: full main.py pipeline against MockBrokerAdapter. No credentials, no network."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend", "src"))

from main import TradingOrchestrator
from brokers.mockAdapter import MockBrokerAdapter


def test_pipeline_runs_without_error_live_disabled():
    orchestrator = TradingOrchestrator(broker=MockBrokerAdapter())
    orchestrator.config["live_trading_enabled"] = False
    result = orchestrator.run_cycle()
    assert result["status"] in ("REJECTED", "APPROVED_NOT_EXECUTED")


def test_live_disabled_never_calls_broker_place_order():
    broker = MockBrokerAdapter()
    orchestrator = TradingOrchestrator(broker=broker)
    orchestrator.config["live_trading_enabled"] = False
    orchestrator.brain.config.min_confidence_to_trade = 1  # let anything through
    orchestrator.run_cycle()
    # even with a trivially low bar, no live order should be placed
    assert len(broker.get_positions()) == 0


def test_live_enabled_with_low_bar_executes_on_mock():
    broker = MockBrokerAdapter()
    orchestrator = TradingOrchestrator(broker=broker)
    orchestrator.config["live_trading_enabled"] = True
    orchestrator.brain.config.min_confidence_to_trade = 1
    result = orchestrator.run_cycle()
    assert result["status"] == "EXECUTED"
    # RANGING regime routes through straddleEngine and lands in pending
    # orders (buy-stop/sell-stop); other regimes route through the AI
    # Brain and land in open positions (market order). Either is a valid
    # EXECUTED outcome — this test checks something actually got placed,
    # not which of the two paths fired on this particular synthetic seed.
    assert len(broker.get_positions()) + len(broker.get_pending_orders()) >= 1


def test_default_orchestrator_uses_mock_broker():
    orchestrator = TradingOrchestrator()
    assert isinstance(orchestrator.broker, MockBrokerAdapter)


def test_config_live_trading_disabled_by_default():
    orchestrator = TradingOrchestrator()
    assert orchestrator.config.get("live_trading_enabled") is False


def _ranging_candle_dicts(seed=3, n=120):
    import random
    import time
    rnd = random.Random(seed)
    candles = []
    price = 1.10000
    now = int(time.time())
    interval = 900  # M15
    for i in range(n):
        o = price
        c = 1.10000 + rnd.uniform(-0.0010, 0.0010)
        h = max(o, c) + rnd.uniform(0, 0.0002)
        l = min(o, c) - rnd.uniform(0, 0.0002)
        timestamp = now - (n - i) * interval
        candles.append({"timestamp": timestamp, "open": o, "high": h, "low": l, "close": c, "volume": rnd.uniform(800, 1200)})
        price = c
    return candles


def test_straddle_two_sided_places_both_pending_orders():
    broker = MockBrokerAdapter()
    candles = _ranging_candle_dicts()
    broker.get_market_data = lambda symbol, tf, limit=200: candles

    orchestrator = TradingOrchestrator(broker=broker)
    orchestrator.config["live_trading_enabled"] = True
    result = orchestrator.run_cycle()

    assert result["status"] == "EXECUTED"
    pending = broker.get_pending_orders()
    assert len(pending) == 2
    sides = {p["side"] for p in pending}
    assert sides == {"BUY", "SELL"}


def test_straddle_directional_places_single_pending_order():
    broker = MockBrokerAdapter()
    orchestrator = TradingOrchestrator(broker=broker)
    orchestrator.config["live_trading_enabled"] = True
    candle_objs = orchestrator._candles_from_broker("EURUSD")

    class FakeMTF:
        alignment_score = 80.0
        dominant_direction = "SELL"

    result = orchestrator._try_straddle("EURUSD", candle_objs, FakeMTF(), atr_val=0.0006)

    assert result["status"] == "EXECUTED"
    pending = broker.get_pending_orders()
    assert len(pending) == 1
    assert pending[0]["side"] == "SELL"


def test_stale_market_data_blocks_trade_even_with_trivial_confidence_bar():
    """This is the actual point of marketData.py + dataValidator.py: stale
    data must block a trade before the engines even run, regardless of how
    low the confidence bar is set or whether live trading is enabled."""
    broker = MockBrokerAdapter()
    orchestrator = TradingOrchestrator(broker=broker)
    orchestrator.config["live_trading_enabled"] = True
    orchestrator.brain.config.min_confidence_to_trade = 1

    stale_candles = [
        {"timestamp": 1000000 + i, "open": 1.1, "high": 1.101, "low": 1.099, "close": 1.1005, "volume": 1000}
        for i in range(120)
    ]
    broker.get_market_data = lambda symbol, tf, limit=200: stale_candles

    result = orchestrator.run_cycle()
    assert result["status"] == "REJECTED"
    assert "Market data validation failed" in result["risk"]
    assert len(broker.get_positions()) == 0
    assert len(broker.get_pending_orders()) == 0


if __name__ == "__main__":
    import inspect
    tests = [f for name, f in list(globals().items()) if name.startswith("test_") and inspect.isfunction(f)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS: {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed")
