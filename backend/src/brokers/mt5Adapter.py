"""
mt5Adapter.py — MetaTrader 5 broker adapter.

STATUS: NOT YET IMPLEMENTED / NOT VERIFIED.

Auth (confirmed from MetaTrader5 Python package docs, not guessed):
    mt5.initialize(login=<account_number>, password=<password>, server=<broker_server_name>)
    This is genuinely login+password+server — MT5 is the one broker
    protocol here where that pattern is actually correct, not assumed.

Real deployment constraint worth being upfront about: the official
`MetaTrader5` Python package talks to a locally running MT5 terminal
process — it is NOT a pure network client. That means "backend" for MT5
realistically means a Windows host (or a Wine-based Linux setup) with the
MT5 terminal installed and logged in, which is a meaningfully different
deployment shape than the Deriv WebSocket adapter. This should be decided
before writing the real implementation, not discovered after.
"""

from typing import Any, Dict, List, Optional

from .baseAdapter import (
    AccountInfo, AuthField, AuthFieldType, BaseBrokerAdapter, BrokerCapabilities,
)


class MT5Adapter(BaseBrokerAdapter):

    @classmethod
    def get_auth_schema(cls) -> List[AuthField]:
        return [
            AuthField(name="login", label="Account number", field_type=AuthFieldType.TEXT, required=True),
            AuthField(name="password", label="Password", field_type=AuthFieldType.PASSWORD, required=True),
            AuthField(
                name="server", label="Server",
                field_type=AuthFieldType.TEXT, required=True,
                help_text="Broker's MT5 server name, e.g. 'BrokerName-Live' or 'BrokerName-Demo' — found in your MT5 terminal login screen.",
            ),
        ]

    @classmethod
    def get_capabilities(cls) -> BrokerCapabilities:
        return BrokerCapabilities(verified=False)

    def __init__(self):
        raise NotImplementedError(
            "MT5Adapter is not implemented yet. Requires the MetaTrader5 "
            "Python package and a running, logged-in MT5 terminal — "
            "Windows or a Wine bridge, not a pure network call. Test on a "
            "demo account before use. Use MockBrokerAdapter for pipeline testing."
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
