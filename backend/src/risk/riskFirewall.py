"""
riskFirewall.py — Phase 4 (spec section 15, final authority)

Even if AI Confidence = 95/100, the trade must be rejected here if any hard
risk condition is violated. Nothing downstream (execution, trade manager)
may bypass this. This module takes the AI Brain's decision plus live
account state and returns an explicit APPROVE/BLOCK verdict with the exact
reason — never a silent pass-through.

Consumes engines.aiBrain.AIDecision as input so the pipeline is:
    ... engines ... -> aiBrain.evaluate() -> riskFirewall.check() -> execution
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "engines"))
from aiBrain import AIDecision, Direction  # noqa: E402


class RiskVerdict(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"


@dataclass
class AccountState:
    balance: float
    equity: float
    daily_pnl: float                 # in account currency, negative = loss
    current_drawdown_pct: float       # 0-100
    open_trade_count: int
    open_symbols: List[str] = field(default_factory=list)  # symbols with an open position
    pending_symbols: List[str] = field(default_factory=list)  # symbols with a pending order
    spread_pips: float = 0.0
    max_allowed_spread_pips: float = 3.0
    session_enabled: bool = True
    market_data_stale: bool = False
    broker_connection_ok: bool = True
    consecutive_losses: int = 0


@dataclass
class RiskConfig:
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_drawdown_pct: float = 10.0
    max_open_trades: int = 3
    max_consecutive_losses: int = 4          # pause after this many losses in a row
    require_confirmation_for_new_symbol: bool = False


@dataclass
class RiskCheckResult:
    verdict: RiskVerdict
    reasons: List[str] = field(default_factory=list)
    approved_direction: Optional[Direction] = None
    approved_risk_pct: Optional[float] = None

    def summary(self) -> str:
        lines = [f"TRADE {self.verdict.value}"]
        lines += [f"  Reason: {r}" for r in self.reasons]
        return "\n".join(lines)


def check(
    decision: AIDecision,
    account: AccountState,
    config: Optional[RiskConfig] = None,
    symbol: str = "",
) -> RiskCheckResult:
    config = config or RiskConfig()
    reasons: List[str] = []

    # A WAIT/NO_TRADE decision from the AI Brain never reaches the firewall
    # as a trade attempt — but make it explicit and safe if it does.
    if decision.direction not in (Direction.BUY, Direction.SELL):
        return RiskCheckResult(
            verdict=RiskVerdict.BLOCKED,
            reasons=[f"AI decision was {decision.direction.value}, not a trade signal"],
        )

    daily_loss_pct = (
        (-account.daily_pnl / account.balance) * 100 if account.balance > 0 else 0.0
    )
    if account.daily_pnl < 0 and daily_loss_pct >= config.max_daily_loss_pct:
        reasons.append(
            f"Daily loss limit reached ({daily_loss_pct:.2f}% >= {config.max_daily_loss_pct:.2f}%)"
        )

    if account.current_drawdown_pct >= config.max_drawdown_pct:
        reasons.append(
            f"Maximum drawdown reached ({account.current_drawdown_pct:.2f}% >= "
            f"{config.max_drawdown_pct:.2f}%)"
        )

    if account.spread_pips > account.max_allowed_spread_pips:
        reasons.append(
            f"Spread too high ({account.spread_pips:.1f} > {account.max_allowed_spread_pips:.1f} pips)"
        )

    if account.open_trade_count >= config.max_open_trades:
        reasons.append(
            f"Maximum open trades reached ({account.open_trade_count} >= {config.max_open_trades})"
        )

    if not account.session_enabled:
        reasons.append("Trading session is disabled in current configuration")

    if account.consecutive_losses >= config.max_consecutive_losses:
        reasons.append(
            f"Consecutive loss protection triggered ({account.consecutive_losses} losses in a row)"
        )

    if symbol and (symbol in account.open_symbols or symbol in account.pending_symbols):
        reasons.append(f"Duplicate position/order detected for {symbol}")

    if not account.broker_connection_ok:
        reasons.append("Broker execution problem — connection not healthy")

    if account.market_data_stale:
        reasons.append("Market data unreliable/stale — required confirmation missing")

    if reasons:
        return RiskCheckResult(verdict=RiskVerdict.BLOCKED, reasons=reasons)

    # All gates passed — approve, but the firewall (not the AI) has final
    # say on risk sizing category too, capped by config regardless of what
    # the AI suggested.
    risk_pct = min(config.max_risk_per_trade_pct, config.max_risk_per_trade_pct)
    if decision.suggested_risk_category == "REDUCED":
        risk_pct = risk_pct * 0.5

    return RiskCheckResult(
        verdict=RiskVerdict.APPROVED,
        reasons=["All risk checks passed"],
        approved_direction=decision.direction,
        approved_risk_pct=risk_pct,
    )
