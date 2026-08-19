"""
aiBrain.py — AI Decision Brain

Role in the pipeline (per spec section 8 & 21):
    Deterministic engines (SMC, Straddle, Liquidity, Fakeout, Momentum, Volume,
    Regime, MTF, CRT) all feed structured evidence into this module.

    This module does NOT:
      - talk to the broker
      - calculate SL/TP/BE/trailing (that's tradeManager.py)
      - have final trade authority (that's riskFirewall.py)

    This module DOES:
      - combine evidence into a single confidence score (0-100)
      - classify direction (BUY / SELL / WAIT / NO_TRADE)
      - explain *why* in plain language
      - state what would invalidate the setup

    Design principle (spec section 9 & 34): this is a probability engine,
    not a price predictor. It never claims to know the future — it says
    "given the current evidence, this setup has X% confidence of behaving
    as expected", and it must be willing to output WAIT or NO_TRADE even
    after a breakout has occurred.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"
    NO_TRADE = "NO_TRADE"


class MarketRegime(str, Enum):
    TRENDING = "TRENDING"
    WEAK = "WEAK"
    REVERSAL = "REVERSAL"
    RANGING = "RANGING"


# ---------------------------------------------------------------------------
# INPUT: structured evidence handed to the AI Brain by the deterministic
# engines. Nothing in here is opinion — it's all measured/detected facts.
# ---------------------------------------------------------------------------
@dataclass
class MarketSnapshot:
    symbol: str

    # Multi-timeframe bias, each: "BUY" | "SELL" | "NEUTRAL"
    h4_bias: str
    h1_bias: str
    m15_structure: str
    m5_structure: str
    m1_setup: str

    # SMC / liquidity evidence
    liquidity_swept: bool
    bos_confirmed: bool
    choch_confirmed: bool
    order_block_present: bool
    fvg_present: bool
    displacement_present: bool

    # Straddle/breakout evidence
    breakout_detected: bool
    retest_status: str          # "PASSED" | "FAILED" | "PENDING" | "N/A"

    # Strength confirmation
    momentum_score: float       # normalized 0.0 - 1.0
    momentum_required: float    # configurable threshold, e.g. 0.65
    volume_confirmed: Optional[bool]  # None if instrument has no reliable volume data

    # Protection layer
    fakeout_probability: float  # 0-100
    exhaustion_detected: bool

    # Regime + context
    market_regime: MarketRegime
    session_active: bool
    spread_ok: bool
    atr_ok: bool                # volatility within acceptable band

    # Optional confirmation module (spec section 11)
    crt_signal: Optional[str] = None       # "BUY" | "SELL" | None
    crt_confidence: Optional[float] = None # 0-100

    # Account/context awareness (spec section 8)
    current_account_risk_ok: bool = True
    recent_performance_note: str = ""


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------
@dataclass
class AIDecision:
    direction: Direction
    confidence: float                  # 0-100
    market_regime: MarketRegime
    setup_type: str
    suggested_risk_category: str       # "LOW" | "STANDARD" | "REDUCED" | "NONE"
    explanation: list = field(default_factory=list)
    invalidating_conditions: list = field(default_factory=list)
    factor_breakdown: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            "AI ANALYSIS",
            f"Symbol Regime: {self.market_regime.value}",
            f"Setup: {self.setup_type}",
            f"Direction: {self.direction.value}",
            f"Confidence: {self.confidence:.0f}/100",
            f"Suggested Risk Category: {self.suggested_risk_category}",
            "",
            "Reasoning:",
        ]
        lines += [f"  - {e}" for e in self.explanation]
        if self.invalidating_conditions:
            lines.append("")
            lines.append("Invalidating conditions:")
            lines += [f"  - {c}" for c in self.invalidating_conditions]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CONFIGURABLE WEIGHTS
# Nothing here is assumed optimal — per spec section 10, these MUST be
# backtested and tuned on out-of-sample data before live use. Defaults
# below are placeholders to get the pipeline running end-to-end.
# ---------------------------------------------------------------------------
@dataclass
class BrainConfig:
    min_confidence_to_trade: float = 75.0

    weight_mtf_alignment: float = 20.0
    weight_liquidity_sweep: float = 12.0
    weight_bos_choch: float = 12.0
    weight_ob_fvg: float = 10.0
    weight_displacement: float = 8.0
    weight_retest: float = 10.0
    weight_momentum: float = 12.0
    weight_volume: float = 6.0
    weight_fakeout_penalty: float = 20.0   # subtracted, scaled by fakeout %
    weight_exhaustion_penalty: float = 10.0
    weight_crt_confirmation: float = 8.0

    # hard gates — if any of these fail, decision is forced regardless of score
    require_session_active: bool = True
    require_spread_ok: bool = True
    require_atr_ok: bool = True


class AIBrain:
    def __init__(self, config: Optional[BrainConfig] = None):
        self.config = config or BrainConfig()

    # -----------------------------------------------------------------
    def evaluate(self, snap: MarketSnapshot) -> AIDecision:
        explanation: list = []
        invalidating: list = []
        breakdown: dict = {}

        # ---- Hard gates: these bypass scoring entirely -----------------
        gate_block = self._check_hard_gates(snap, explanation)
        if gate_block:
            return AIDecision(
                direction=Direction.NO_TRADE,
                confidence=0.0,
                market_regime=snap.market_regime,
                setup_type="N/A",
                suggested_risk_category="NONE",
                explanation=explanation,
                invalidating_conditions=invalidating,
                factor_breakdown=breakdown,
            )

        # ---- Regime gate: REVERSAL/WEAK regimes get defensive treatment
        if snap.market_regime == MarketRegime.REVERSAL:
            explanation.append(
                "Market regime is REVERSAL/INVALIDATED — original setup context "
                "is compromised regardless of individual factor scores."
            )
            return AIDecision(
                direction=Direction.NO_TRADE,
                confidence=0.0,
                market_regime=snap.market_regime,
                setup_type="Invalidated",
                suggested_risk_category="NONE",
                explanation=explanation,
                invalidating_conditions=["Opposite BOS/CHoCH or liquidity reversal detected"],
                factor_breakdown=breakdown,
            )

        # ---- Directional bias from MTF -----------------------------------
        proposed_direction = self._infer_direction(snap, explanation)

        # ---- Score accumulation -------------------------------------------
        score = 0.0
        cfg = self.config

        mtf_score = self._score_mtf_alignment(snap, proposed_direction)
        score += mtf_score * cfg.weight_mtf_alignment / 100
        breakdown["mtf_alignment"] = mtf_score
        explanation.append(f"MTF alignment score: {mtf_score:.0f}/100")

        if snap.liquidity_swept:
            score += cfg.weight_liquidity_sweep
            explanation.append("Liquidity sweep confirmed (+)")
        breakdown["liquidity_swept"] = snap.liquidity_swept

        if snap.bos_confirmed or snap.choch_confirmed:
            score += cfg.weight_bos_choch
            explanation.append("BOS/CHoCH confirmed (+)")
        breakdown["bos_choch"] = snap.bos_confirmed or snap.choch_confirmed

        if snap.order_block_present or snap.fvg_present:
            score += cfg.weight_ob_fvg
            explanation.append("Order Block / FVG present (+)")
        breakdown["ob_fvg"] = snap.order_block_present or snap.fvg_present

        if snap.displacement_present:
            score += cfg.weight_displacement
            explanation.append("Displacement present (+)")
        breakdown["displacement"] = snap.displacement_present

        if snap.retest_status == "PASSED":
            score += cfg.weight_retest
            explanation.append("Retest passed (+)")
        elif snap.retest_status == "FAILED":
            score -= cfg.weight_retest
            explanation.append("Retest failed (-)")
            invalidating.append("Retest failure — breakout may be false")
        breakdown["retest_status"] = snap.retest_status

        if snap.momentum_score >= snap.momentum_required:
            score += cfg.weight_momentum
            explanation.append(
                f"Momentum {snap.momentum_score:.2f} >= required "
                f"{snap.momentum_required:.2f} (+)"
            )
        else:
            score -= cfg.weight_momentum
            explanation.append(
                f"Momentum {snap.momentum_score:.2f} < required "
                f"{snap.momentum_required:.2f} (-)"
            )
            invalidating.append(
                f"Momentum below threshold ({snap.momentum_score:.2f} < "
                f"{snap.momentum_required:.2f})"
            )
        breakdown["momentum"] = snap.momentum_score

        if snap.volume_confirmed is True:
            score += cfg.weight_volume
            explanation.append("Volume confirmed (+)")
        elif snap.volume_confirmed is False:
            score -= cfg.weight_volume
            explanation.append("Volume not confirmed (-)")
        else:
            explanation.append("Volume data unreliable for this instrument — skipped")
        breakdown["volume_confirmed"] = snap.volume_confirmed

        # Fakeout probability acts as a penalty, scaled continuously
        fakeout_penalty = (snap.fakeout_probability / 100) * cfg.weight_fakeout_penalty
        score -= fakeout_penalty
        breakdown["fakeout_probability"] = snap.fakeout_probability
        explanation.append(
            f"Fakeout probability {snap.fakeout_probability:.0f}% "
            f"(-{fakeout_penalty:.1f} pts)"
        )
        if snap.fakeout_probability >= 65:
            invalidating.append(
                f"High fakeout probability ({snap.fakeout_probability:.0f}%)"
            )

        if snap.exhaustion_detected:
            score -= cfg.weight_exhaustion_penalty
            explanation.append("Exhaustion detected (-)")
            invalidating.append("Exhaustion signals present")
        breakdown["exhaustion"] = snap.exhaustion_detected

        if snap.crt_signal is not None and snap.crt_confidence is not None:
            if snap.crt_signal == proposed_direction.value:
                crt_boost = (snap.crt_confidence / 100) * cfg.weight_crt_confirmation
                score += crt_boost
                explanation.append(
                    f"CRT reversal module agrees with direction "
                    f"({snap.crt_confidence:.0f}% conf) (+{crt_boost:.1f})"
                )
            else:
                explanation.append(
                    "CRT reversal module disagrees with proposed direction — "
                    "informational only, no penalty applied"
                )
        breakdown["crt"] = {
            "signal": snap.crt_signal,
            "confidence": snap.crt_confidence,
        }

        confidence = max(0.0, min(100.0, score))

        # ---- Regime-aware risk category ------------------------------------
        if snap.market_regime == MarketRegime.WEAK:
            suggested_risk = "REDUCED"
            explanation.append(
                "Regime is WEAK/UNCERTAIN — defensive management, risk category reduced"
            )
        elif snap.market_regime == MarketRegime.RANGING:
            suggested_risk = "STANDARD"
        elif snap.market_regime == MarketRegime.TRENDING:
            suggested_risk = "STANDARD"
        else:
            suggested_risk = "NONE"

        # ---- Final decision ---------------------------------------------
        if proposed_direction == Direction.WAIT:
            final_direction = Direction.WAIT
        elif confidence >= cfg.min_confidence_to_trade:
            final_direction = proposed_direction
        elif confidence >= cfg.min_confidence_to_trade - 15:
            final_direction = Direction.WAIT
            explanation.append(
                f"Confidence {confidence:.0f} below minimum "
                f"{cfg.min_confidence_to_trade:.0f} but close — WAIT for further confirmation"
            )
        else:
            final_direction = Direction.NO_TRADE
            explanation.append(
                f"Confidence {confidence:.0f} well below minimum "
                f"{cfg.min_confidence_to_trade:.0f} — NO TRADE"
            )

        setup_type = self._describe_setup(snap)

        return AIDecision(
            direction=final_direction,
            confidence=confidence,
            market_regime=snap.market_regime,
            setup_type=setup_type,
            suggested_risk_category=suggested_risk if final_direction in
                (Direction.BUY, Direction.SELL) else "NONE",
            explanation=explanation,
            invalidating_conditions=invalidating,
            factor_breakdown=breakdown,
        )

    # -----------------------------------------------------------------
    def _check_hard_gates(self, snap: MarketSnapshot, explanation: list) -> bool:
        """Returns True if a hard gate blocks trading entirely."""
        cfg = self.config
        blocked = False

        if cfg.require_session_active and not snap.session_active:
            explanation.append("Session filter: current session not enabled — blocked")
            blocked = True
        if cfg.require_spread_ok and not snap.spread_ok:
            explanation.append("Spread outside acceptable range — blocked")
            blocked = True
        if cfg.require_atr_ok and not snap.atr_ok:
            explanation.append("Volatility (ATR) outside acceptable band — blocked")
            blocked = True
        if not snap.current_account_risk_ok:
            explanation.append("Account risk state disallows new trades — blocked")
            blocked = True

        return blocked

    # -----------------------------------------------------------------
    def _infer_direction(self, snap: MarketSnapshot, explanation: list) -> Direction:
        """
        Determine the proposed direction from HTF bias + entry setup.
        This is a proposal only — final direction is decided in evaluate()
        after scoring.
        """
        biases = [snap.h4_bias, snap.h1_bias, snap.m15_structure]
        buys = biases.count("BUY")
        sells = biases.count("SELL")

        if snap.m1_setup not in ("BUY", "SELL"):
            explanation.append("No clear M1 setup — WAIT")
            return Direction.WAIT

        if buys > sells and snap.m1_setup == "BUY":
            return Direction.BUY
        if sells > buys and snap.m1_setup == "SELL":
            return Direction.SELL

        explanation.append(
            "Higher-timeframe bias conflicts with entry-timeframe setup — WAIT"
        )
        return Direction.WAIT

    # -----------------------------------------------------------------
    def _score_mtf_alignment(self, snap: MarketSnapshot, direction: Direction) -> float:
        if direction not in (Direction.BUY, Direction.SELL):
            return 0.0
        biases = [snap.h4_bias, snap.h1_bias, snap.m15_structure, snap.m5_structure, snap.m1_setup]
        matches = sum(1 for b in biases if b == direction.value)
        return (matches / len(biases)) * 100

    # -----------------------------------------------------------------
    def _describe_setup(self, snap: MarketSnapshot) -> str:
        parts = []
        if snap.breakout_detected:
            parts.append("Breakout")
        if snap.liquidity_swept:
            parts.append("Liquidity Sweep")
        if snap.bos_confirmed:
            parts.append("BOS")
        if snap.choch_confirmed:
            parts.append("CHoCH")
        if snap.fvg_present:
            parts.append("FVG")
        if not parts:
            return "SMC context only"
        return "SMC + " + " + ".join(parts)


# ---------------------------------------------------------------------------
# Example usage / smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    snapshot = MarketSnapshot(
        symbol="EURUSD",
        h4_bias="BUY",
        h1_bias="BUY",
        m15_structure="BUY",
        m5_structure="BUY",
        m1_setup="BUY",
        liquidity_swept=True,
        bos_confirmed=True,
        choch_confirmed=False,
        order_block_present=True,
        fvg_present=True,
        displacement_present=True,
        breakout_detected=True,
        retest_status="PASSED",
        momentum_score=0.71,
        momentum_required=0.65,
        volume_confirmed=True,
        fakeout_probability=18.0,
        exhaustion_detected=False,
        market_regime=MarketRegime.TRENDING,
        session_active=True,
        spread_ok=True,
        atr_ok=True,
        crt_signal="BUY",
        crt_confidence=70.0,
    )

    brain = AIBrain()
    decision = brain.evaluate(snapshot)
    print(decision.summary())
