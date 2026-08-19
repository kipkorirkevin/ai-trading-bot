"""
executionRouter.py — Phase 4

Routes an approved, sized, SL/TP-computed trade to the broker, using only
BaseBrokerAdapter's actual interface (place_market_order /
place_pending_order — not a nonexistent generic place_order).

Checks the broker's declared capabilities BEFORE sending anything. If the
broker can't do what the trade needs (no SL support, straddle requested
but hedging unsupported, lot size outside min/max, symbol not in its
supported list), the order is rejected here with an explicit reason —
never silently dropped or silently sent anyway.

STRADDLE / STRADDLE_DIRECTIONAL now take explicit buy_trigger/sell_trigger
and per-side SL/TP — these come from straddleEngine.py's range detection
and tradeManager's structure-based SL calc, not a guessed percentage
buffer off current price. The old straddle_buffer_pct fallback still
exists for callers (and tests) that don't have those computed yet.
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional

from brokers.baseAdapter import BaseBrokerAdapter, BrokerCapabilities

SetupType = Literal["STRADDLE", "STRADDLE_DIRECTIONAL", "BREAKOUT", "SMC_DIRECTIONAL"]


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
            "Broker adapter capabilities are unverified — this broker has not "
            "been tested against a real account yet. Refusing to execute until verified."
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

    if setup_type in ("STRADDLE", "STRADDLE_DIRECTIONAL") and not caps.supports_stop_orders:
        return "Straddle requires stop orders — broker does not support them"

    if setup_type == "STRADDLE" and not caps.supports_hedging:
        return "Two-sided straddle requires holding opposing orders — broker does not support hedging"

    return None


def execute(
    broker: BaseBrokerAdapter,
    symbol: str,
    direction: str,       # "BUY" | "SELL" — used for BREAKOUT/SMC_DIRECTIONAL and as the priority side fallback
    lot: float,
    price: float,
    sl: Optional[float],
    tp: Optional[float],
    setup_type: SetupType,
    straddle_buffer_pct: float = 0.005,
    buy_trigger: Optional[float] = None,
    sell_trigger: Optional[float] = None,
    buy_sl: Optional[float] = None,
    sell_sl: Optional[float] = None,
    buy_tp: Optional[float] = None,
    sell_tp: Optional[float] = None,
    directional_side: Optional[str] = None,
) -> ExecutionResult:
    caps = broker.get_capabilities()
    # For capability checking on straddles, use whichever side's SL/TP is
    # set as the representative sample — both sides get the same support
    # requirement from the broker either way.
    check_sl = sl if setup_type not in ("STRADDLE", "STRADDLE_DIRECTIONAL") else (buy_sl or sell_sl or sl)
    check_tp = tp if setup_type not in ("STRADDLE", "STRADDLE_DIRECTIONAL") else (buy_tp or sell_tp or tp)
    rejection = _check_capabilities(caps, symbol, lot, setup_type, check_sl, check_tp)
    if rejection:
        return ExecutionResult(success=False, detail="Order rejected by capability check", rejected_reason=rejection)

    if setup_type == "STRADDLE":
        buy_price = buy_trigger if buy_trigger is not None else price * (1 + straddle_buffer_pct)
        sell_price = sell_trigger if sell_trigger is not None else price * (1 - straddle_buffer_pct)
        b_sl = buy_sl if buy_sl is not None else sl
        s_sl = sell_sl if sell_sl is not None else sl
        b_tp = buy_tp if buy_tp is not None else tp
        s_tp = sell_tp if sell_tp is not None else tp
        buy_id = broker.place_pending_order(symbol, "BUY", lot, buy_price, "buy_stop", sl=b_sl, tp=b_tp)
        sell_id = broker.place_pending_order(symbol, "SELL", lot, sell_price, "sell_stop", sl=s_sl, tp=s_tp)
        return ExecutionResult(
            success=True,
            detail=f"Straddle placed: buy-stop @ {buy_price:.5f} (SL {b_sl}), sell-stop @ {sell_price:.5f} (SL {s_sl})",
            order_ids=[buy_id, sell_id],
        )

    if setup_type == "STRADDLE_DIRECTIONAL":
        side = directional_side or direction
        if side == "BUY":
            trigger = buy_trigger if buy_trigger is not None else price * (1 + straddle_buffer_pct)
            side_sl = buy_sl if buy_sl is not None else sl
            side_tp = buy_tp if buy_tp is not None else tp
            order_kind = "buy_stop"
        else:
            trigger = sell_trigger if sell_trigger is not None else price * (1 - straddle_buffer_pct)
            side_sl = sell_sl if sell_sl is not None else sl
            side_tp = sell_tp if sell_tp is not None else tp
            order_kind = "sell_stop"
        order_id = broker.place_pending_order(symbol, side, lot, trigger, order_kind, sl=side_sl, tp=side_tp)
        return ExecutionResult(
            success=True,
            detail=f"Directional straddle: {side} pending @ {trigger:.5f} (SL {side_sl} / TP {side_tp})",
            order_ids=[order_id],
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
