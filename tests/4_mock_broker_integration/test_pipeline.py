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
    assert len(broker.get_positions()) == 1


def test_default_orchestrator_uses_mock_broker():
    orchestrator = TradingOrchestrator()
    assert isinstance(orchestrator.broker, MockBrokerAdapter)


def test_config_live_trading_disabled_by_default():
    orchestrator = TradingOrchestrator()
    assert orchestrator.config.get("live_trading_enabled") is False


if __name__ == "__main__":
    import inspect
    tests = [f for name, f in list(globals().items()) if name.startswith("test_") and inspect.isfunction(f)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS: {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed")
