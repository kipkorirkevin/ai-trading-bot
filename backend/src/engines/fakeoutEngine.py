"""
fakeoutEngine.py — Phase 2 (spec section 6, critical component)

The system must NOT assume "breakout = valid trade." This module combines
evidence from the other Phase 1/2 engines into a single Fakeout Probability
(0-100), which aiBrain.py uses as a continuous confidence penalty (not a
hard veto — per spec section 9, this is probabilistic, not guaranteed).

Deliberately takes already-computed results from momentumEngine,
volumeEngine, and exhaustionEngine as inputs rather than recomputing them,
so there's a single source of truth per factor and the pipeline order
(momentum -> volume -> exhaustion -> fakeout) matches the spec's engine
stack in section 2.
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional

from .common import Candle
from .momentumEngine import MomentumResult
from .volumeEngine import VolumeResult
from .exhaustionEngine import ExhaustionResult

Direction = Literal["BUY", "SELL"]
RetestStatus = Literal["PASSED", "FAILED", "PENDING", "N/A"]


@dataclass
class FakeoutInputs:
    liquidity_swept: bool
    close_outside_range: bool
    retest_status: RetestStatus
    mtf_alignment_score: float       # 0-100, from mtfEngine
    momentum: MomentumResult
    volume: VolumeResult
    exhaustion: ExhaustionResult
    return_inside_range: bool = False   # price closed back inside the range post-breakout


@dataclass
class FakeoutResult:
    probability: float               # 0-100, higher = more likely fake
    verdict: str                     # "LOW" | "MEDIUM" | "HIGH"
    reasons: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Fakeout Probability: {self.probability:.0f} ({self.verdict})"]
        lines += [f"  - {r}" for r in self.reasons]
        return "\n".join(lines)


# Weights sum to 100. Not assumed optimal — must be backtested (spec section 10).
_WEIGHTS = {
    "no_sweep": 15,
    "no_close_outside": 15,
    "retest_failed": 20,
    "weak_mtf": 15,
    "weak_momentum": 15,
    "no_volume_confirm": 10,
    "exhaustion": 15,
    "returned_inside_range": 20,
}


def analyze(inputs: FakeoutInputs, momentum_required: float = 0.65, mtf_threshold: float = 60.0) -> FakeoutResult:
    score = 0.0
    reasons: List[str] = []

    if not inputs.liquidity_swept:
        score += _WEIGHTS["no_sweep"]
        reasons.append("No liquidity sweep preceded the breakout")

    if not inputs.close_outside_range:
        score += _WEIGHTS["no_close_outside"]
        reasons.append("Price has not closed outside the range")

    if inputs.retest_status == "FAILED":
        score += _WEIGHTS["retest_failed"]
        reasons.append("Retest failed")
    elif inputs.retest_status == "PENDING":
        score += _WEIGHTS["retest_failed"] * 0.4
        reasons.append("Retest still pending — partial uncertainty")

    if inputs.mtf_alignment_score < mtf_threshold:
        score += _WEIGHTS["weak_mtf"]
        reasons.append(
            f"MTF alignment {inputs.mtf_alignment_score:.0f} below {mtf_threshold:.0f} threshold"
        )

    if inputs.momentum.score < momentum_required:
        score += _WEIGHTS["weak_momentum"]
        reasons.append(
            f"Momentum {inputs.momentum.score:.2f} below required {momentum_required:.2f}"
        )

    if inputs.volume.confirmed is False:
        score += _WEIGHTS["no_volume_confirm"]
        reasons.append("Volume did not confirm the breakout")

    if inputs.exhaustion.exhaustion_detected:
        score += _WEIGHTS["exhaustion"]
        reasons.append("Exhaustion signals present: " + "; ".join(inputs.exhaustion.reasons))

    if inputs.return_inside_range:
        score += _WEIGHTS["returned_inside_range"]
        reasons.append("Price returned inside the original range post-breakout")

    probability = max(0.0, min(100.0, score))

    if probability >= 65:
        verdict = "HIGH"
    elif probability >= 35:
        verdict = "MEDIUM"
    else:
        verdict = "LOW"

    if not reasons:
        reasons.append("No fakeout risk factors detected")

    return FakeoutResult(probability=probability, verdict=verdict, reasons=reasons)
