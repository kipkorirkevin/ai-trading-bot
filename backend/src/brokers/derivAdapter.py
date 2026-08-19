"""
derivAdapter.py — Deriv broker adapter.

STATUS: NOT YET IMPLEMENTED / NOT VERIFIED. get_capabilities().verified is
False and must stay False until connect() and at least one real order
round-trip have been tested against Deriv's actual API on a demo account.

Auth (confirmed from developers.deriv.com, not guessed):
    Deriv's WebSocket API (wss://) supports two auth approaches:
      - Personal Access Token (PAT): user generates a token in their Deriv
        account (Security & Limits > API token) and pastes it in. Simplest
        for a native/mobile app since there's no browser redirect.
      - OAuth 2.0: browser-based consent flow, returns a short-lived
        access token. Better UX for account-linking flows but needs an
        in-app browser/redirect handler.
    Either way, the token is sent to the `authorize` WebSocket call —
    Deriv does NOT use username+password for API access.

An earlier draft of this project called `ccxt.binance(...)` inside a class
named DerivAdapter — that connects to Binance, not Deriv, and was never
actually correct. Nothing from that draft is reused here.

Real implementation needs: the `websockets` library (or `python-deriv-api`
if still maintained — verify current status before depending on it), a
Deriv app_id (register at api.deriv.com), and mapping Deriv's contract-based
options/CFD model onto this adapter's position/order interface, which is
nontrivial since Deriv's trading model (contracts, not classic positions)
doesn't map 1:1 onto MT5-style positions.
"""

from typing import Any, Dict, List, Optional

from .baseAdapter import (
    AccountInfo, AuthField, AuthFieldType, BaseBrokerAdapter, BrokerCapabilities,
)


class DerivAdapter(BaseBrokerAdapter):

    @classmethod
    def get_auth_schema(cls) -> List[AuthField]:
        return [
            AuthField(
                name="auth_method", label="Authentication method",
                field_type=AuthFieldType.SELECT, required=True,
                options=["Personal Access Token", "OAuth 2.0"],
            ),
            AuthField(
                name="api_token", label="API Token",
                field_type=AuthFieldType.PASSWORD, required=True,
                help_text="Generate at Deriv account \u2192 Security & Limits \u2192 API token. "
                           "Required for Personal Access Token method.",
            ),
            AuthField(
                name="app_id", label="App ID",
                field_type=AuthFieldType.TEXT, required=True,
                help_text="Your registered Deriv app_id from api.deriv.com.",
            ),
        ]

    @classmethod
    def get_capabilities(cls) -> BrokerCapabilities:
        # Documented-but-UNVERIFIED placeholder — do not trust for sizing
        # decisions until confirmed against Deriv's actual contract specs.
        return BrokerCapabilities(verified=False)

    def __init__(self):
        raise NotImplementedError(
            "DerivAdapter is not implemented yet. Build against the real "
            "Deriv WebSocket API (developers.deriv.com) and test on a demo "
            "account before use. Use MockBrokerAdapter for pipeline testing."
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
