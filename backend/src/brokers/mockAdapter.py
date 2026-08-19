"""
mockAdapter.py — in-memory paper-trading adapter implementing the full
BaseBrokerAdapter interface. No network calls, no real credentials.
This is the only adapter that can honestly claim get_capabilities().verified
= True on its own, since there's no external API to fail against —
everything else needs real broker testing first (see baseAdapter.py docstring).
"""

import itertools
import random
from typing import Any, Dict, List, Optional

from .baseAdapter import (
    AccountInfo, AuthField, AuthFieldType, BaseBrokerAdapter, BrokerCapabilities,
)


class MockBrokerAdapter(BaseBrokerAdapter):

    @classmethod
    def get_auth_schema(cls) -> List[AuthField]:
        return [
            AuthField(
                name="account_label", label="Account label (any name)",
                field_type=AuthFieldType.TEXT, required=False,
                help_text="Purely cosmetic — mock adapter needs no real credentials.",
            ),
        ]

    @classmethod
    def get_capabilities(cls) -> BrokerCapabilities:
        return BrokerCapabilities(
            supports_market_orders=True,
            supports_limit_orders=True,
            supports_stop_orders=True,
            supports_stop_loss=True,
            supports_take_profit=True,
            supports_trailing_stop=True,
            supports_partial_close=True,
            supports_hedging=True,
            netting_only=False,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            min_order_size=0.01,
            max_order_size=100.0,
            supported_symbols=["EURUSD", "GBPUSD", "BTCUSD"],
            supported_timeframes=["M1", "M5", "M15", "H1", "H4"],
            verified=True,
        )

    def __init__(self, starting_balance: float = 10000.0):
        self._connected = False
        self.balance = starting_balance
        self.equity = starting_balance
        self._id_counter = itertools.count(1)
        self.open_positions: Dict[str, dict] = {}
        self.pending_orders: Dict[str, dict] = {}
        self._rnd = random.Random(1)

    def connect(self, credentials: Dict[str, Any]) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> bool:
        self._connected = False
        return True

    def heartbeat(self) -> bool:
        return self._connected

    def reconnect(self) -> bool:
        return self.connect({})

    def synchronize_account(self) -> Dict[str, Any]:
        return {"positions": self.get_positions(), "orders": self.get_pending_orders()}

    def get_account_info(self) -> AccountInfo:
        return AccountInfo(
            balance=self.balance, equity=self.equity, currency="USD",
            leverage=100.0, account_id="MOCK-0001", is_demo=True,
        )

    def get_balance(self) -> float:
        return self.balance

    def get_price(self, symbol: str) -> Dict[str, float]:
        base = 1.10000
        spread = 0.00012
        return {"bid": base, "ask": base + spread}

    def get_market_data(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, float]]:
        candles = []
        price = 1.10000
        for i in range(limit):
            o = price
            c = o + self._rnd.uniform(-0.0006, 0.0006)
            h = max(o, c) + self._rnd.uniform(0, 0.0004)
            l = min(o, c) - self._rnd.uniform(0, 0.0003)
            vol = self._rnd.uniform(700, 1300)
            candles.append({"timestamp": i, "open": o, "high": h, "low": l, "close": c, "volume": vol})
            price = c
        return candles

    def get_positions(self) -> List[Dict[str, Any]]:
        return [{"id": k, **v} for k, v in self.open_positions.items()]

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        return [{"id": k, **v} for k, v in self.pending_orders.items()]

    def place_market_order(self, symbol, side, size, sl=None, tp=None) -> str:
        order_id = f"MOCK-POS-{next(self._id_counter)}"
        self.open_positions[order_id] = {"symbol": symbol, "side": side, "size": size, "sl": sl, "tp": tp}
        return order_id

    def place_pending_order(self, symbol, side, size, price, order_kind, sl=None, tp=None) -> str:
        order_id = f"MOCK-ORD-{next(self._id_counter)}"
        self.pending_orders[order_id] = {
            "symbol": symbol, "side": side, "size": size, "price": price,
            "order_kind": order_kind, "sl": sl, "tp": tp,
        }
        return order_id

    def modify_position(self, position_id, sl=None, tp=None) -> bool:
        pos = self.open_positions.get(position_id)
        if not pos:
            return False
        if sl is not None:
            pos["sl"] = sl
        if tp is not None:
            pos["tp"] = tp
        return True

    def modify_order(self, order_id, price=None, sl=None, tp=None) -> bool:
        order = self.pending_orders.get(order_id)
        if not order:
            return False
        if price is not None:
            order["price"] = price
        if sl is not None:
            order["sl"] = sl
        if tp is not None:
            order["tp"] = tp
        return True

    def close_position(self, position_id, size=None) -> bool:
        pos = self.open_positions.get(position_id)
        if not pos:
            return False
        if size is None or size >= pos["size"]:
            del self.open_positions[position_id]
        else:
            pos["size"] -= size
        return True

    def cancel_order(self, order_id) -> bool:
        return self.pending_orders.pop(order_id, None) is not None

    def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        ids = [oid for oid, o in self.pending_orders.items() if symbol is None or o["symbol"] == symbol]
        for oid in ids:
            del self.pending_orders[oid]
        return len(ids)
