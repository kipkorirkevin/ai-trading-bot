"""
models.py — Phase 6+ database schema

Two tables: TradeLog (every executed trade, for backtesting/performance
review) and AuditLog (every decision — including rejections — per spec
section 28's requirement that every decision be logged, not just executed
trades).
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()


class TradeLog(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    side = Column(String)          # BUY | SELL
    entry = Column(Float)
    exit = Column(Float, nullable=True)
    sl = Column(Float)
    tp = Column(Float)
    lot = Column(Float)
    pnl = Column(Float, nullable=True)
    r_multiple = Column(Float, nullable=True)
    confidence = Column(Float)
    setup_type = Column(String)
    decision_reason = Column(String)
    opened_at = Column(DateTime, default=datetime.datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audits"

    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    status = Column(String)        # EXECUTED | REJECTED | NO_TRADE
    ai_confidence = Column(Float, nullable=True)
    ai_direction = Column(String, nullable=True)
    market_regime = Column(String, nullable=True)
    reason = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
