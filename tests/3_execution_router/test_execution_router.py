"""Tier 3: Execution Router. No credentials, no network."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend", "src"))

from trading import executionRouter
from brokers.baseAdapter import BrokerCapabilities
from brokers.mockAdapter import MockBrokerAdapter


def test_unverified_broker_always_rejected():
    caps = BrokerCapabilities(verified=False, supports_stop_loss=True, min_lot=0.01, max_lot=10, lot_step=0.01)
    reason = executionRouter._check_capabilities(caps, "EURUSD", 0.1, "SMC_DIRECTIONAL", 1.05, 1.15)
    assert reason is not None
    assert "unverified" in reason.lower()


def test_lot_below_minimum_rejected():
    caps = BrokerCapabilities(verified=True, min_lot=0.1, max_lot=10, lot_step=0.01, supports_stop_loss=True)
    reason = executionRouter._check_capabilities(caps, "EURUSD", 0.01, "SMC_DIRECTIONAL", None, None)
    assert reason is not None
    assert "outside broker's allowed range" in reason


def test_lot_above_maximum_rejected():
    caps = BrokerCapabilities(verified=True, min_lot=0.01, max_lot=1.0, lot_step=0.01)
    reason = executionRouter._check_capabilities(caps, "EURUSD", 5.0, "SMC_DIRECTIONAL", None, None)
    assert reason is not None


def test_symbol_not_supported_rejected():
    caps = BrokerCapabilities(verified=True, min_lot=0.01, max_lot=10, lot_step=0.01, supported_symbols=["BTCUSD"])
    reason = executionRouter._check_capabilities(caps, "EURUSD", 0.1, "SMC_DIRECTIONAL", None, None)
    assert reason is not None
    assert "not in broker's supported symbol list" in reason


def test_sl_requested_but_unsupported_rejected():
    caps = BrokerCapabilities(verified=True, min_lot=0.01, max_lot=10, lot_step=0.01, supports_stop_loss=False)
    reason = executionRouter._check_capabilities(caps, "EURUSD", 0.1, "SMC_DIRECTIONAL", 1.05, None)
    assert reason is not None
    assert "stop-loss" in reason.lower()


def test_straddle_requires_hedging_support():
    caps = BrokerCapabilities(
        verified=True, min_lot=0.01, max_lot=10, lot_step=0.01,
        supports_stop_orders=True, supports_hedging=False,
    )
    reason = executionRouter._check_capabilities(caps, "EURUSD", 0.1, "STRADDLE", None, None)
    assert reason is not None
    assert "hedging" in reason.lower()


def test_clean_order_passes_capability_check():
    caps = BrokerCapabilities(
        verified=True, min_lot=0.01, max_lot=10, lot_step=0.01,
        supports_stop_loss=True, supports_take_profit=True,
        supported_symbols=["EURUSD"],
    )
    reason = executionRouter._check_capabilities(caps, "EURUSD", 0.1, "SMC_DIRECTIONAL", 1.05, 1.15)
    assert reason is None


def test_execute_against_mock_adapter_succeeds():
    broker = MockBrokerAdapter()
    broker.connect({})
    result = executionRouter.execute(
        broker, symbol="EURUSD", direction="BUY", lot=0.1,
        price=1.10000, sl=1.09500, tp=1.10500, setup_type="SMC_DIRECTIONAL",
    )
    assert result.success is True
    assert len(result.order_ids) == 1
    assert len(broker.get_positions()) == 1


if __name__ == "__main__":
    import inspect
    tests = [f for name, f in list(globals().items()) if name.startswith("test_") and inspect.isfunction(f)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS: {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed")
