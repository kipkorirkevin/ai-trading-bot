"""
executionRouter.py — Phase 4

Routes an approved, sized, SL/TP-computed trade to the broker, using only
BaseBrokerAdapter's actual interface (place_market_order /
place_pending_order — not a nonexistent generic place_order).

Per your instruction: this checks the broker's declared capabilities
BEFORE sending anything. If the broker can't do what the trade needs
(no SL support, straddle requested but hedging unsupported, lot size
outside min/max, symbol not in its supported list), the order is
rejected here with an explicit reason — never silently dropped or
silently sent anyway.
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional

from brokers.baseAdapter import BaseBrokerAdapter, BrokerCapabilities

SetupType = Literal["STRADDLE", "BREAKOUT", "SMC_DIRECTIONAL"]


@dataclass
class ExecutionResult:
    success: bool
    detail: str
    order_ids: List[str] = field(default_factory=list)
    rejected_reason: Optional[str] = None


def _check_capabilities(
    caps: BrokerCapabilities, symbol: str, lot: float, setup_type: SetupType,
    sl: Optional[float], tp: Optional[float],
) -> Optional[str]:
    """Returns a rejection reason string, or None if the order is capability-clean."""
    if not caps.verified:
        return (
            f"Broker adapter capabilities are unverified — this broker has not "
            f"been tested against a real account yet. Refusing to execute until verified."
        )

    if caps.supported_symbols and symbol not in caps.supported_symbols:
        return f"Symbol {symbol} not in broker's supported symbol list"

    if lot < caps.min_lot or lot > caps.max_lot:
        return f"Lot size {lot} outside broker's allowed range [{caps.min_lot}, {caps.max_lot}]"

    if caps.lot_step > 0:
        steps = round(lot / caps.lot_step)
        if abs(lot - steps * caps.lot_step) > 1e-9:
            return f"Lot size {lot} does not align to broker's lot step {caps.lot_step}"

    if sl is not None and not caps.supports_stop_loss:
        return "Broker does not support server-side stop-loss on this instrument"

    if tp is not None and not caps.supports_take_profit:
        return "Broker does not support server-side take-profit on this instrument"

    if setup_type == "STRADDLE" and not caps.supports_hedging:
        return "Straddle requires holding opposing orders — broker does not support hedging"

    if setup_type == "STRADDLE" and not caps.supports_stop_orders:
        return "Straddle requires stop orders — broker does not support them"

    return None


def execute(
    broker: BaseBrokerAdapter,
    symbol: str,
    direction: str,       # "BUY" | "SELL"
    lot: float,
    price: float,
    sl: Optional[float],
    tp: Optional[float],
    setup_type: SetupType,
    straddle_buffer_pct: float = 0.005,
) -> ExecutionResult:
    caps = broker.get_capabilities()
    rejection = _check_capabilities(caps, symbol, lot, setup_type, sl, tp)
    if rejection:
        return ExecutionResult(success=False, detail="Order rejected by capability check", rejected_reason=rejection)

    if setup_type == "STRADDLE":
        buy_price = price * (1 + straddle_buffer_pct)
        sell_price = price * (1 - straddle_buffer_pct)
        buy_id = broker.place_pending_order(symbol, "BUY", lot, buy_price, "buy_stop", sl=sl, tp=tp)
        sell_id = broker.place_pending_order(symbol, "SELL", lot, sell_price, "sell_stop", sl=sl, tp=tp)
        return ExecutionResult(
            success=True,
            detail=f"Straddle placed: buy-stop @ {buy_price:.5f}, sell-stop @ {sell_price:.5f}",
            order_ids=[buy_id, sell_id],
        )

    # BREAKOUT / SMC_DIRECTIONAL: single directional market order.
    order_id = broker.place_market_order(symbol, direction, lot, sl=sl, tp=tp)
    return ExecutionResult(
        success=True,
        detail=f"{direction} {symbol} {lot} lots @ ~{price:.5f} (SL {sl} / TP {tp})",
        order_ids=[order_id],
    )


def cancel_opposite_side(broker: BaseBrokerAdapter, order_id_to_cancel: str) -> bool:
    """Call when one side of a straddle triggers — cancel the other pending order."""
    return broker.cancel_order(order_id_to_cancel)
