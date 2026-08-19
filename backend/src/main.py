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
"""

import json
from pathlib import Path
from typing import Optional

from engines.common import Candle, atr as atr_fn
from engines import (
    smcEngine, liquidityEngine, momentumEngine, volumeEngine,
    exhaustionEngine, mtfEngine, fakeoutEngine, regimeEngine, crtEngine,
)
from engines.aiBrain import AIBrain, BrainConfig, MarketSnapshot, MarketRegime
from risk import riskFirewall
from risk.positionSizer import PositionSizerConfig, calculate as size_position
from trading import tradeManager, executionRouter
from brokers.baseAdapter import BaseBrokerAdapter
from brokers.mockAdapter import MockBrokerAdapter

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

        self._prior_bias = "NEUTRAL"

    def _candles_from_broker(self, symbol: str, timeframe: str = "M15", limit: int = 120) -> list:
        raw = self.broker.get_market_data(symbol, timeframe, limit)
        return [
            Candle(
                timestamp=c["timestamp"], open=c["open"], high=c["high"],
                low=c["low"], close=c["close"], volume=c.get("volume", 0.0),
            )
            for c in raw
        ]

    def run_cycle(self, symbol: str = None) -> dict:
        symbol = symbol or self.config["symbols"][0]
        candles = self._candles_from_broker(symbol)

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
        account_state = riskFirewall.AccountState(
            balance=account.balance, equity=account.equity, daily_pnl=0.0,
            current_drawdown_pct=0.0, open_trade_count=len(self.broker.get_positions()),
            spread_pips=1.0, max_allowed_spread_pips=3.0,
        )
        risk_result = riskFirewall.check(decision, account_state, self.risk_config, symbol=symbol)

        if risk_result.verdict != riskFirewall.RiskVerdict.APPROVED:
            return {"status": "REJECTED", "ai_decision": decision.summary(), "risk": risk_result.summary()}

        atr_val = atr_fn(candles, period=14)
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
