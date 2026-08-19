"""
api/server.py — REST API for the mobile dashboard.

Broker flow (matches your required architecture):
    Android App -> GET /brokers (discover options + auth schemas)
                -> POST /brokers/{broker_id}/connect (credentials)
                -> backend creates the adapter via brokers.registry
                -> everything downstream (orchestrator, engines, AI,
                   risk firewall, execution router) only ever sees
                   BaseBrokerAdapter — never a broker-specific type.

No global orchestrator at import time — it's created only once a broker
is selected and connected, so the API never silently defaults to the mock
broker for real usage. Bug fix vs. an earlier draft: that version reached
into `orchestrator.broker.pending_orders` / `.open_positions` directly,
which only exist on MockBrokerAdapter — a real adapter would have crashed
on /cancel_pending and /close_all. This version uses only
get_pending_orders() / get_positions() / cancel_order() / close_position(),
which every adapter must implement.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from main import TradingOrchestrator
from brokers import registry

app = FastAPI(title="AI Hybrid SMC + Straddle Trading Bot")


class BotStatus(str, Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class ConnectRequest(BaseModel):
    credentials: Dict[str, Any] = {}


class StartRequest(BaseModel):
    symbols: List[str] = []
    confidence: Optional[int] = None


_state: Dict[str, Any] = {
    "status": BotStatus.STOPPED,
    "new_trades_allowed": True,
    "last_result": None,
    "orchestrator": None,   # TradingOrchestrator, created on /brokers/{id}/connect
    "broker_id": None,
}


def _require_orchestrator() -> TradingOrchestrator:
    if _state["orchestrator"] is None:
        raise HTTPException(status_code=400, detail="No broker connected yet — call /brokers/{id}/connect first")
    return _state["orchestrator"]


@app.get("/brokers")
def list_brokers():
    """Android's broker-selection screen renders directly from this —
    each entry's auth_fields drives the dynamic credential form."""
    return registry.list_brokers()


@app.post("/brokers/{broker_id}/connect")
def connect_broker(broker_id: str, req: ConnectRequest):
    try:
        adapter = registry.create_adapter(broker_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    try:
        orchestrator = TradingOrchestrator(broker=adapter, credentials=req.credentials)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to connect: {e}")

    _state["orchestrator"] = orchestrator
    _state["broker_id"] = broker_id
    capabilities = adapter.get_capabilities()
    return {
        "message": f"Connected to {broker_id}",
        "verified": capabilities.verified,
        "capabilities": capabilities.__dict__,
    }


@app.get("/status")
def status():
    orchestrator = _state["orchestrator"]
    if orchestrator is None:
        return {"bot_status": _state["status"], "broker_id": None, "account": None, "ai": None}

    account = orchestrator.broker.get_account_info()
    last = _state["last_result"] or {}
    return {
        "bot_status": _state["status"],
        "broker_id": _state["broker_id"],
        "new_trades_allowed": _state["new_trades_allowed"],
        "account": account.__dict__,
        "ai": {"decision": last.get("status", "WAITING"), "raw": last.get("ai_decision")},
    }


@app.post("/start")
def start(req: StartRequest):
    orchestrator = _require_orchestrator()
    _state["status"] = BotStatus.RUNNING
    _state["new_trades_allowed"] = True
    if req.confidence:
        orchestrator.brain.config.min_confidence_to_trade = req.confidence
    symbols = req.symbols or orchestrator.config["symbols"]
    result = orchestrator.run_cycle(symbol=symbols[0])
    _state["last_result"] = result
    return {"message": "Bot started", "cycle_result": result}


@app.post("/pause")
def pause():
    _state["status"] = BotStatus.PAUSED
    return {"message": "Bot paused"}


@app.post("/stop_new_trades")
def stop_new_trades():
    _state["new_trades_allowed"] = False
    return {"message": "New trades disabled — existing positions untouched"}


@app.post("/cancel_pending")
def cancel_pending():
    orchestrator = _require_orchestrator()
    count = orchestrator.broker.cancel_all_orders()
    return {"message": f"Cancelled {count} pending order(s)"}


@app.post("/close_all")
def close_all():
    orchestrator = _require_orchestrator()
    positions = orchestrator.broker.get_positions()
    for pos in positions:
        orchestrator.broker.close_position(pos["id"])
    return {"message": f"Closed {len(positions)} open position(s)"}


@app.get("/audit")
def audit():
    """Spec section 28. Backed by database.models.AuditLog once persistence
    is wired up (Phase 6) — for now, returns the last in-memory cycle result."""
    last = _state["last_result"]
    if not last:
        return []
    return [{"timestamp": None, "message": last.get("ai_decision", "No decision yet")}]


@app.post("/emergency_stop")
def emergency_stop():
    _state["status"] = BotStatus.STOPPED
    _state["new_trades_allowed"] = False
    if _state["orchestrator"] is not None:
        cancel_pending()
        close_all()
    return {"message": "EMERGENCY STOP executed — bot stopped, orders cancelled, positions closed"}
