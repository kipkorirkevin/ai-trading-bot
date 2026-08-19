"""
baseAdapter.py — abstract broker interface + capability discovery.

Every broker adapter (Deriv, MT5, Exness-via-MT5, mock, future brokers)
implements this interface so strategy engines, aiBrain, riskFirewall,
positionSizer, tradeManager, and executionRouter never contain
broker-specific code. This is the ONLY place broker differences are
allowed to live.

Two things every adapter must provide beyond the trading calls:

1. get_auth_schema() (classmethod) — describes what credential fields
   the Android app should render for this broker. The mobile app calls
   GET /brokers to get these schemas and builds the login form
   dynamically; it never hardcodes "login + password" as a universal
   assumption, because that's false (Deriv uses a token, not a password).

2. get_capabilities() — describes what this broker/account actually
   supports (order types, SL/TP, trailing, hedging, lot limits, symbols,
   timeframes). executionRouter.py MUST check these before sending any
   order — sending a trailing-stop instruction to a broker that doesn't
   support server-side trailing stops is a silent-failure bug waiting
   to happen.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AuthFieldType(str, Enum):
    TEXT = "text"
    PASSWORD = "password"
    SELECT = "select"


@dataclass
class AuthField:
    name: str                       # key used in the credentials dict passed to connect()
    label: str                      # shown in the Android UI
    field_type: AuthFieldType
    required: bool = True
    options: Optional[List[str]] = None   # for SELECT fields (e.g. server list)
    help_text: str = ""


@dataclass
class BrokerCapabilities:
    supports_market_orders: bool = False
    supports_limit_orders: bool = False
    supports_stop_orders: bool = False
    supports_stop_loss: bool = False
    supports_take_profit: bool = False
    supports_trailing_stop: bool = False       # server-side trailing, not client-simulated
    supports_partial_close: bool = False
    supports_hedging: bool = False             # can hold BUY and SELL on the same symbol at once
    netting_only: bool = False                 # opposite of hedging — opposite orders net against each other
    min_lot: float = 0.0
    max_lot: float = 0.0
    lot_step: float = 0.0
    min_order_size: float = 0.0
    max_order_size: float = 0.0
    supported_symbols: List[str] = field(default_factory=list)
    supported_timeframes: List[str] = field(default_factory=list)
    verified: bool = False   # True only once actually tested against the live broker API — see class docstring


@dataclass
class AccountInfo:
    balance: float
    equity: float
    currency: str
    leverage: Optional[float] = None
    account_id: Optional[str] = None
    is_demo: bool = True


class BaseBrokerAdapter(ABC):
    """
    IMPORTANT: an adapter is not "supported" just because this class
    exists. It's supported once connect(), get_market_data(), and
    place_market_order() have been implemented AND tested against that
    broker's real API (paper/demo account is fine — untested is not).
    Until then, capabilities().verified stays False and the UI/README
    must say so.
    """

    # ---- credential schema for dynamic Android UI --------------------
    @classmethod
    @abstractmethod
    def get_auth_schema(cls) -> List[AuthField]:
        """Returns the exact fields this broker needs. No universal
        login+password assumption — each adapter states its own truth."""
        ...

    @classmethod
    @abstractmethod
    def get_capabilities(cls) -> BrokerCapabilities:
        """Static/documented capabilities. Adapters may also expose a
        per-instance refine step (e.g. querying live symbol specs) via
        get_live_capabilities() once connected, if the broker supports it."""
        ...

    # ---- lifecycle -----------------------------------------------------
    @abstractmethod
    def connect(self, credentials: Dict[str, Any]) -> bool: ...

    @abstractmethod
    def disconnect(self) -> bool: ...

    @abstractmethod
    def heartbeat(self) -> bool:
        """Lightweight liveness check. Spec section 31: connection
        monitoring is mandatory."""
        ...

    @abstractmethod
    def reconnect(self) -> bool: ...

    @abstractmethod
    def synchronize_account(self) -> Dict[str, Any]:
        """Reconcile local state against the broker's actual open
        positions/orders after a reconnect — spec section 31: order
        synchronization, duplicate-order prevention, crash recovery."""
        ...

    # ---- account / market data ------------------------------------------
    @abstractmethod
    def get_account_info(self) -> AccountInfo: ...

    @abstractmethod
    def get_balance(self) -> float: ...

    @abstractmethod
    def get_price(self, symbol: str) -> Dict[str, float]:
        """Returns at least {'bid': ..., 'ask': ...}."""
        ...

    @abstractmethod
    def get_market_data(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, float]]:
        """Returns OHLCV candles as dicts — caller (marketData.py) converts
        to engines.common.Candle so this layer stays broker-agnostic."""
        ...

    # ---- positions / orders ------------------------------------------
    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def get_pending_orders(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def place_market_order(
        self, symbol: str, side: str, size: float,
        sl: Optional[float] = None, tp: Optional[float] = None,
    ) -> str:
        """Returns an order/position id."""
        ...

    @abstractmethod
    def place_pending_order(
        self, symbol: str, side: str, size: float, price: float, order_kind: str,
        sl: Optional[float] = None, tp: Optional[float] = None,
    ) -> str:
        """order_kind e.g. 'buy_stop' | 'sell_stop' | 'buy_limit' | 'sell_limit'."""
        ...

    @abstractmethod
    def modify_position(
        self, position_id: str, sl: Optional[float] = None, tp: Optional[float] = None,
    ) -> bool: ...

    @abstractmethod
    def modify_order(
        self, order_id: str, price: Optional[float] = None,
        sl: Optional[float] = None, tp: Optional[float] = None,
    ) -> bool: ...

    @abstractmethod
    def close_position(self, position_id: str, size: Optional[float] = None) -> bool:
        """size=None closes the full position; a value enables partial close
        (only valid if capabilities().supports_partial_close is True)."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """Returns the number of orders cancelled."""
        ...
