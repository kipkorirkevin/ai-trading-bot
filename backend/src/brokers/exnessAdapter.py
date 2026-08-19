"""
exnessAdapter.py — Exness broker adapter.

STATUS: NOT YET IMPLEMENTED / NOT VERIFIED.

Important finding from actual research (not assumed): Exness does not
expose a separate REST/WebSocket trading API for retail order execution.
Their own "API" documentation is for Partners/IBs (affiliate dashboard
data, email+password auth) — not for placing trades. Retail trading with
Exness is done through MetaTrader 4/5 using Exness-issued MT5 login
credentials, exactly the same protocol as mt5Adapter.py.

So this adapter is deliberately thin: it reuses MT5Adapter's connection
logic with Exness's MT5 servers, rather than inventing a distinct
"Exness API" that doesn't exist for trade execution. If that changes (a
real Exness trading API ships), this file should be rewritten against it
directly instead of wrapping MT5Adapter.
"""

from typing import Any, Dict, List, Optional

from .baseAdapter import (
    AccountInfo, AuthField, AuthFieldType, BaseBrokerAdapter, BrokerCapabilities,
)
from .mt5Adapter import MT5Adapter


class ExnessAdapter(BaseBrokerAdapter):

    @classmethod
    def get_auth_schema(cls) -> List[AuthField]:
        # Same shape as MT5 — this is not a coincidence, see module docstring.
        return [
            AuthField(name="login", label="Account number", field_type=AuthFieldType.TEXT, required=True),
            AuthField(name="password", label="Password", field_type=AuthFieldType.PASSWORD, required=True),
            AuthField(
                name="server", label="Server",
                field_type=AuthFieldType.SELECT, required=True,
                options=["Exness-MT5Real", "Exness-MT5Trial"],
                help_text="Exact server list depends on your Exness account region/type — "
                           "verify current names in your MT5 terminal before hardcoding.",
            ),
        ]

    @classmethod
    def get_capabilities(cls) -> BrokerCapabilities:
        return BrokerCapabilities(verified=False)

    def __init__(self):
        raise NotImplementedError(
            "ExnessAdapter is not implemented yet. Exness trade execution "
            "goes through the MT5 protocol (see module docstring) — this "
            "should delegate to a tested MT5Adapter once that exists, not "
            "be built independently. Use MockBrokerAdapter for pipeline testing."
        )

    def connect(self, credentials: Dict[str, Any]) -> bool: ...
    def disconnect(self) -> bool: ...
    def heartbeat(self) -> bool: ...
    def reconnect(self) -> bool: ...
    def synchronize_account(self) -> Dict[str, Any]: ...
    def get_account_info(self) -> AccountInfo: ...
    def get_balance(self) -> float: ...
    def get_price(self, symbol: str) -> Dict[str, float]: ...
    def get_market_data(self, symbol, timeframe, limit=200) -> List[Dict[str, float]]: ...
    def get_positions(self) -> List[Dict[str, Any]]: ...
    def get_pending_orders(self) -> List[Dict[str, Any]]: ...
    def place_market_order(self, symbol, side, size, sl=None, tp=None) -> str: ...
    def place_pending_order(self, symbol, side, size, price, order_kind, sl=None, tp=None) -> str: ...
    def modify_position(self, position_id, sl=None, tp=None) -> bool: ...
    def modify_order(self, order_id, price=None, sl=None, tp=None) -> bool: ...
    def close_position(self, position_id, size=None) -> bool: ...
    def cancel_order(self, order_id) -> bool: ...
    def cancel_all_orders(self, symbol=None) -> int: ...
