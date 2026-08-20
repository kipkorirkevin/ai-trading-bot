"""
websocketManager.py — Phase 1 (spec section 31: connection monitoring,
heartbeat, automatic reconnect, crash recovery)

Deliberately generic — contains ZERO Deriv/MT5/Exness-specific protocol
code. This is a reusable retry/backoff/heartbeat state machine that any
broker adapter with a persistent connection (a Deriv websocket, an MT5
terminal handle, anything) can wrap around its own connect/heartbeat
calls, instead of every adapter reimplementing exponential backoff from
scratch. The name reflects the most likely first user (a websocket-based
adapter) but nothing here assumes websockets specifically.

Usage pattern for a future real adapter:

    manager = ReconnectingConnectionManager(
        connect_fn=self._raw_connect,
        heartbeat_fn=self._raw_heartbeat,
        on_reconnect=self._resync_after_reconnect,
    )
    manager.connect()
    ...
    if not manager.heartbeat():
        manager.reconnect_with_backoff()
"""

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class ConnectionEvent:
    timestamp: float
    event: str    # "connected" | "disconnected" | "reconnect_attempt" | "reconnect_failed" | "reconnected"
    detail: str = ""


class ReconnectingConnectionManager:
    def __init__(
        self,
        connect_fn: Callable[[], None],
        heartbeat_fn: Callable[[], bool],
        on_reconnect: Optional[Callable[[], None]] = None,
        base_backoff_seconds: float = 1.0,
        backoff_factor: float = 2.0,
        max_backoff_seconds: float = 60.0,
    ):
        self.connect_fn = connect_fn
        self.heartbeat_fn = heartbeat_fn
        self.on_reconnect = on_reconnect
        self.base_backoff_seconds = base_backoff_seconds
        self.backoff_factor = backoff_factor
        self.max_backoff_seconds = max_backoff_seconds

        self.is_connected = False
        self.consecutive_failures = 0
        self.history: List[ConnectionEvent] = []

    def _log(self, event: str, detail: str = ""):
        self.history.append(ConnectionEvent(timestamp=time.time(), event=event, detail=detail))

    def compute_backoff(self, attempt: int) -> float:
        return min(self.max_backoff_seconds, self.base_backoff_seconds * (self.backoff_factor ** attempt))

    def connect(self) -> bool:
        try:
            self.connect_fn()
            self.is_connected = True
            self.consecutive_failures = 0
            self._log("connected")
            return True
        except Exception as e:
            self.is_connected = False
            self.consecutive_failures += 1
            self._log("disconnected", detail=str(e))
            return False

    def heartbeat(self) -> bool:
        """Call periodically. Returns False if the connection has died —
        caller should then call reconnect_with_backoff()."""
        if not self.is_connected:
            return False
        try:
            ok = self.heartbeat_fn()
        except Exception as e:
            ok = False
            self._log("disconnected", detail=f"heartbeat exception: {e}")
        if not ok:
            self.is_connected = False
            self._log("disconnected", detail="heartbeat returned False")
        return ok

    def reconnect_with_backoff(
        self, max_attempts: int = 5, sleep_fn: Callable[[float], None] = time.sleep,
    ) -> bool:
        for attempt in range(max_attempts):
            self._log("reconnect_attempt", detail=f"attempt {attempt + 1}/{max_attempts}")
            if self.connect():
                self._log("reconnected")
                if self.on_reconnect:
                    self.on_reconnect()
                return True
            delay = self.compute_backoff(attempt)
            self._log("reconnect_failed", detail=f"retrying in {delay:.1f}s")
            sleep_fn(delay)
        return False
