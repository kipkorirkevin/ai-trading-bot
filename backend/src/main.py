"""
main.py — Trading Orchestrator

Broker-agnostic by construction: this file imports BaseBrokerAdapter's
interface only, never a specific broker. Which broker is active is
decided by whoever constructs TradingOrchestrator (api/server.py, driven
by the Android app's broker selection) via brokers.registry.create_adapter().

Pipeline order matches spec section 2:
    market data -> SMC -> Liquidity -> Fakeout -> Momentum -> Volume ->
    Exhaustion -> MTF -> Regime -> CRT -> AI Brain -> Risk Firewall ->
    Execution -> Trade Manager -> Database

Two trade paths, chosen by market regime (spec section 7):
    RANGING  -> straddleEngine (two-sided or directional straddle),
                gated by riskFirewall.check_setup()
    other    -> AI Brain directional decision,
                gated by riskFirewall.check()
If regime is RANGING but straddleEngine finds no valid range (its own
volatility-ratio thresholds reject it), this falls through to the normal
AI Brain path rather than forcing a straddle that doesn't actually exist.
"""

import json
from pathlib import Path
from typing import Optional

from engines.common import Candle, atr as atr_fn
from engines import (
    smcEngine, liquidityEngine, momentumEngine, volumeEngine,
    exhaustionEngine, mtfEngine, fakeoutEngine, regimeEngine, crtEngine, straddleEngine,
)
from engines.aiBrain import AIBrain, BrainConfig, MarketSnapshot, MarketRegime
from risk import riskFirewall
from risk.positionSizer import PositionSizerConfig, calculate as size_position
from trading import tradeManager, executionRouter
from brokers.baseAdapter import BaseBrokerAdapter
from brokers.mockAdapter import MockBrokerAdapter
from data.marketData import MarketDataEngine

CONFIG_PATH = Path(__file__).parent / "config" / "config.json"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


class TradingOrchestrator:
    def __init__(self, broker: Optional[BaseBrokerAdapter] = None, credentials: Optional[dict] = None):
        self.config = load_config()
        self.broker = broker or MockBrokerAdapter()
        self.broker.connect(credentials or {})

        self.brain = AIBrain(BrainConfig(
            min_confidence_to_trade=self.config["ai_brain"]["min_confidence_to_trade"],
        ))
        self.risk_config = riskFirewall.RiskConfig(**self.config["risk"])
        self.sizer_config = PositionSizerConfig(**self.config["position_sizer"])
        self.trade_config = tradeManager.TradeManagerConfig(**self.config["trade_management"])
        self.market_data = MarketDataEngine(self.broker)

        self._prior_bias = "NEUTRAL"
        self._last_data_issues: list = []   # populated each run_cycle, read by _account_state

    def _candles_from_broker(self, symbol: str, timeframe: str = "M15", limit: int = 120) -> list:
        """Thin wrapper kept for callers that just want candles without
        caring about validation (e.g. ad-hoc scripts/tests). run_cycle()
        itself uses self.market_data directly so it can see validation
        results and feed them into the Risk Firewall."""
        result = self.market_data.get_candles(symbol, timeframe, limit, run_validation=False)
        return result.candles

    def _account_state(self, data_stale: bool = False) -> riskFirewall.AccountState:
        account = self.broker.get_account_info()
        return riskFirewall.AccountState(
            balance=account.balance, equity=account.equity, daily_pnl=0.0,
            current_drawdown_pct=0.0, open_trade_count=len(self.broker.get_positions()),
            spread_pips=1.0, max_allowed_spread_pips=3.0,
            market_data_stale=data_stale,
        )

    def _try_straddle(self, symbol: str, candles: list, mtf, atr_val: float) -> Optional[dict]:
        """Returns a result dict if a straddle setup was found and acted on
        (approved/rejected/executed), or None if there's no valid straddle
        setup here and the caller should fall through to the AI Brain path."""
        setup = straddleEngine.analyze(
            candles, mtf_alignment_score=mtf.alignment_score,
            mtf_dominant_direction=mtf.dominant_direction, spread_ok=True,
        )
        if not setup.valid:
            return None

        account = self.broker.get_account_info()
        account_state = self._account_state(data_stale=bool(self._last_data_issues))
        risk_result = riskFirewall.check_setup(account_state, self.risk_config, symbol=symbol)

        if risk_result.verdict != riskFirewall.RiskVerdict.APPROVED:
            return {"status": "REJECTED", "straddle_setup": setup.reasons, "risk": risk_result.summary()}

        extra_buffer = atr_val * 0.2
        buy_sl = setup.range_low - extra_buffer
        sell_sl = setup.range_high + extra_buffer
        buy_risk = setup.buy_trigger - buy_sl
        sell_risk = sell_sl - setup.sell_trigger
        tp_mult = self.trade_config.tp_r_multiples[0] if self.trade_config.tp_r_multiples else 1.0
        buy_tp = setup.buy_trigger + buy_risk * tp_mult
        sell_tp = setup.sell_trigger - sell_risk * tp_mult

        lot = size_position(
            self.sizer_config, balance=account.balance,
            stop_loss_distance=max(buy_risk, sell_risk), pip_value_per_lot=10.0, pip_size=0.0001,
        )

        would_place = {
            "setup_type": setup.setup_type, "priority_side": setup.priority_side,
            "buy_trigger": setup.buy_trigger, "sell_trigger": setup.sell_trigger,
            "buy_sl": buy_sl, "sell_sl": sell_sl, "buy_tp": buy_tp, "sell_tp": sell_tp, "lot": lot,
        }

        if not self.config.get("live_trading_enabled", False):
            return {
                "status": "APPROVED_NOT_EXECUTED", "straddle_setup": setup.reasons,
                "risk": risk_result.summary(),
                "note": "live_trading_enabled is False in config.json — no order sent",
                "would_place": would_place,
            }

        if setup.setup_type == "TWO_SIDED":
            exec_result = executionRouter.execute(
                self.broker, symbol=symbol, direction="BUY", lot=lot, price=candles[-1].close,
                sl=None, tp=None, setup_type="STRADDLE",
                buy_trigger=setup.buy_trigger, sell_trigger=setup.sell_trigger,
                buy_sl=buy_sl, sell_sl=sell_sl, buy_tp=buy_tp, sell_tp=sell_tp,
            )
        else:  # DIRECTIONAL
            exec_result = executionRouter.execute(
                self.broker, symbol=symbol, direction=setup.priority_side, lot=lot, price=candles[-1].close,
                sl=None, tp=None, setup_type="STRADDLE_DIRECTIONAL", directional_side=setup.priority_side,
                buy_trigger=setup.buy_trigger, sell_trigger=setup.sell_trigger,
                buy_sl=buy_sl, sell_sl=sell_sl, buy_tp=buy_tp, sell_tp=sell_tp,
            )

        if not exec_result.success:
            return {
                "status": "EXECUTION_BLOCKED", "straddle_setup": setup.reasons,
                "risk": risk_result.summary(), "rejected_reason": exec_result.rejected_reason,
            }

        return {
            "status": "EXECUTED", "straddle_setup": setup.reasons, "risk": risk_result.summary(),
            "execution": exec_result.detail, "position": would_place,
        }

    def run_cycle(self, symbol: str = None) -> dict:
        symbol = symbol or self.config["symbols"][0]

        fetch = self.market_data.get_candles(symbol, "M15", limit=120, run_validation=True)
        candles = fetch.candles
        self._last_data_issues = [] if fetch.validation.is_valid else fetch.validation.issues

        if not fetch.validation.is_valid:
            # Market data unreliable/stale — spec section 15 explicit block
            # condition. Don't even bother running the engines on bad data.
            account_state = self._account_state(data_stale=True)
            blocked = riskFirewall.RiskCheckResult(
                verdict=riskFirewall.RiskVerdict.BLOCKED,
                reasons=["Market data validation failed: " + "; ".join(fetch.validation.issues)],
            )
            return {"status": "REJECTED", "ai_decision": None, "risk": blocked.summary()}

        smc = smcEngine.analyze(candles)
        liquidity = liquidityEngine.analyze(candles)
        momentum = momentumEngine.analyze(candles, direction=smc.bias if smc.bias != "NEUTRAL" else "BUY")
        volume = volumeEngine.analyze(candles)
        exhaustion = exhaustionEngine.analyze(candles, direction=smc.bias if smc.bias != "NEUTRAL" else "BUY")

        mtf = mtfEngine.analyze({"H4": candles, "H1": candles, "M15": candles, "M5": candles, "M1": candles})

        fakeout_inputs = fakeoutEngine.FakeoutInputs(
            liquidity_swept=liquidity.liquidity_swept,
            close_outside_range=(candles[-1].close > smc.recent_high or candles[-1].close < smc.recent_low),
            retest_status="PASSED" if momentum.consistency_component > 0.6 else "PENDING",
            mtf_alignment_score=mtf.alignment_score,
            momentum=momentum, volume=volume, exhaustion=exhaustion,
        )
        fakeout = fakeoutEngine.analyze(fakeout_inputs)

        crt = crtEngine.analyze(candles)
        crt_signal_mapped = {"BUY_REVERSAL": "BUY", "SELL_REVERSAL": "SELL"}.get(crt.signal)

        reversal_confirmed = smc.choch_confirmed and smc.bias != self._prior_bias and smc.bias != "NEUTRAL"
        regime = regimeEngine.analyze(
            candles, momentum_score=momentum.score, fakeout_probability=fakeout.probability,
            prior_bias=self._prior_bias, current_bias=smc.bias, reversal_confirmed=reversal_confirmed,
        )
        self._prior_bias = smc.bias

        atr_val = atr_fn(candles, period=14)

        # RANGING regime tries the straddle path first — spec section 7:
        # "Prefer range/straddle logic and avoid forcing directional trades."
        if regime.regime == "RANGING":
            straddle_result = self._try_straddle(symbol, candles, mtf, atr_val)
            if straddle_result is not None:
                return straddle_result
            # else: no valid range found despite RANGING classification — fall through

        snapshot = MarketSnapshot(
            symbol=symbol,
            h4_bias=smc.bias, h1_bias=smc.bias, m15_structure=smc.bias,
            m5_structure=smc.bias, m1_setup=smc.bias,
            liquidity_swept=liquidity.liquidity_swept,
            bos_confirmed=smc.bos_confirmed, choch_confirmed=smc.choch_confirmed,
            order_block_present=smc.order_block_present, fvg_present=smc.fvg_present,
            displacement_present=smc.displacement_present,
            breakout_detected=fakeout_inputs.close_outside_range,
            retest_status=fakeout_inputs.retest_status,
            momentum_score=momentum.score, momentum_required=0.65,
            volume_confirmed=volume.confirmed,
            fakeout_probability=fakeout.probability,
            exhaustion_detected=exhaustion.exhaustion_detected,
            market_regime=MarketRegime(regime.regime),
            session_active=True, spread_ok=True, atr_ok=True,
            crt_signal=crt_signal_mapped,
            crt_confidence=crt.confidence if crt_signal_mapped else None,
        )

        decision = self.brain.evaluate(snapshot)

        account = self.broker.get_account_info()
        account_state = self._account_state(data_stale=bool(self._last_data_issues))
        risk_result = riskFirewall.check(decision, account_state, self.risk_config, symbol=symbol)

        if risk_result.verdict != riskFirewall.RiskVerdict.APPROVED:
            return {"status": "REJECTED", "ai_decision": decision.summary(), "risk": risk_result.summary()}

        position = tradeManager.set_initial_sl_tp(
            self.trade_config, entry=candles[-1].close, direction=decision.direction.value, atr_value=atr_val,
        )
        lot = size_position(
            self.sizer_config, balance=account.balance,
            stop_loss_distance=abs(position.entry - position.sl), pip_value_per_lot=10.0, pip_size=0.0001,
        )

        if not self.config.get("live_trading_enabled", False):
            return {
                "status": "APPROVED_NOT_EXECUTED",
                "ai_decision": decision.summary(), "risk": risk_result.summary(),
                "note": "live_trading_enabled is False in config.json — no order sent",
                "would_place": {
                    "symbol": symbol, "direction": decision.direction.value, "lot": lot,
                    "entry": position.entry, "sl": position.sl, "tp_levels": position.tp_levels,
                },
            }

        exec_result = executionRouter.execute(
            self.broker, symbol=symbol, direction=decision.direction.value, lot=lot,
            price=position.entry, sl=position.sl, tp=position.tp_levels[0], setup_type="SMC_DIRECTIONAL",
        )
        if not exec_result.success:
            return {
                "status": "EXECUTION_BLOCKED", "ai_decision": decision.summary(),
                "risk": risk_result.summary(), "rejected_reason": exec_result.rejected_reason,
            }

        return {
            "status": "EXECUTED", "ai_decision": decision.summary(), "risk": risk_result.summary(),
            "execution": exec_result.detail,
            "position": {"entry": position.entry, "sl": position.sl, "tp_levels": position.tp_levels, "lot": lot},
        }


if __name__ == "__main__":
    orchestrator = TradingOrchestrator()  # defaults to MockBrokerAdapter
    result = orchestrator.run_cycle()
    print(json.dumps(result, indent=2, default=str))
