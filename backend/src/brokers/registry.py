"""
registry.py — single source of truth mapping a broker_id to its adapter
class. Adding a new broker later means: write NewBrokerAdapter(BaseBrokerAdapter),
add one line here. Nothing else in the app changes — no engine, no risk
firewall, no execution router, no Android screen needs to know a new
broker exists beyond fetching this list from the API.
"""

from typing import Dict, Type

from .baseAdapter import BaseBrokerAdapter
from .mockAdapter import MockBrokerAdapter
from .derivAdapter import DerivAdapter
from .mt5Adapter import MT5Adapter
from .exnessAdapter import ExnessAdapter

BROKER_REGISTRY: Dict[str, Type[BaseBrokerAdapter]] = {
    "mock": MockBrokerAdapter,
    "deriv": DerivAdapter,
    "mt5": MT5Adapter,
    "exness": ExnessAdapter,
}

BROKER_DISPLAY_NAMES: Dict[str, str] = {
    "mock": "Paper Trading (Mock)",
    "deriv": "Deriv",
    "mt5": "MetaTrader 5",
    "exness": "Exness",
}


def list_brokers() -> list:
    """Returns the catalog the Android app renders on the broker selection
    screen: id, display name, whether it's actually verified/usable yet,
    and its auth field schema for building the dynamic credential form."""
    out = []
    for broker_id, adapter_cls in BROKER_REGISTRY.items():
        try:
            capabilities = adapter_cls.get_capabilities()
            auth_schema = adapter_cls.get_auth_schema()
        except Exception:
            capabilities = None
            auth_schema = []
        out.append({
            "id": broker_id,
            "name": BROKER_DISPLAY_NAMES.get(broker_id, broker_id),
            "verified": bool(capabilities and capabilities.verified),
            "auth_fields": [
                {
                    "name": f.name, "label": f.label, "type": f.field_type.value,
                    "required": f.required, "options": f.options, "help_text": f.help_text,
                }
                for f in auth_schema
            ],
        })
    return out


def create_adapter(broker_id: str) -> BaseBrokerAdapter:
    if broker_id not in BROKER_REGISTRY:
        raise ValueError(f"Unknown broker_id: {broker_id}")
    return BROKER_REGISTRY[broker_id]()
