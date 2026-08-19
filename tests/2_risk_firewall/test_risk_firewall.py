"""Tier 2: Risk Firewall. No credentials, no network."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend", "src"))

from engines.aiBrain import AIBrain, MarketSnapshot, MarketRegime, Direction
from risk import riskFirewall


def _approved_decision():
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
    return AIBrain().evaluate(snap)


def _healthy_account():
    return riskFirewall.AccountState(
        balance=10000, equity=10100, daily_pnl=100, current_drawdown_pct=1.0,
        open_trade_count=0, spread_pips=1.0, max_allowed_spread_pips=3.0,
    )


def test_high_confidence_trade_approved_on_healthy_account():
    decision = _approved_decision()
    assert decision.direction in (Direction.BUY, Direction.SELL)
    result = riskFirewall.check(decision, _healthy_account())
    assert result.verdict == riskFirewall.RiskVerdict.APPROVED


def test_daily_loss_limit_blocks_even_high_confidence():
    decision = _approved_decision()
    account = _healthy_account()
    account.daily_pnl = -500  # 5% loss on 10k balance, default limit is 3%
    result = riskFirewall.check(decision, account)
    assert result.verdict == riskFirewall.RiskVerdict.BLOCKED
    assert any("Daily loss" in r for r in result.reasons)


def test_max_drawdown_blocks_trade():
    decision = _approved_decision()
    account = _healthy_account()
    account.current_drawdown_pct = 15.0  # default limit is 10%
    result = riskFirewall.check(decision, account)
    assert result.verdict == riskFirewall.RiskVerdict.BLOCKED


def test_spread_too_high_blocks_trade():
    decision = _approved_decision()
    account = _healthy_account()
    account.spread_pips = 10.0
    result = riskFirewall.check(decision, account)
    assert result.verdict == riskFirewall.RiskVerdict.BLOCKED


def test_max_open_trades_blocks_trade():
    decision = _approved_decision()
    account = _healthy_account()
    account.open_trade_count = 5  # default max is 3
    result = riskFirewall.check(decision, account)
    assert result.verdict == riskFirewall.RiskVerdict.BLOCKED


def test_duplicate_symbol_blocks_trade():
    decision = _approved_decision()
    account = _healthy_account()
    account.open_symbols = ["EURUSD"]
    result = riskFirewall.check(decision, account, symbol="EURUSD")
    assert result.verdict == riskFirewall.RiskVerdict.BLOCKED


def test_no_trade_decision_never_reaches_risk_check_as_a_trade():
    from engines.aiBrain import AIDecision
    no_trade = AIDecision(
        direction=Direction.NO_TRADE, confidence=0, market_regime=MarketRegime.WEAK,
        setup_type="N/A", suggested_risk_category="NONE",
    )
    result = riskFirewall.check(no_trade, _healthy_account())
    assert result.verdict == riskFirewall.RiskVerdict.BLOCKED


if __name__ == "__main__":
    import inspect
    tests = [f for name, f in list(globals().items()) if name.startswith("test_") and inspect.isfunction(f)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS: {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed")
