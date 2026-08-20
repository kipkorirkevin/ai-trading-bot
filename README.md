# AI Hybrid SMC + Straddle Trading Bot — Multi-Broker Architecture

## Architecture

```
Android App
  -> Broker Selection (GET /brokers)
  -> Account Authentication (dynamic form per broker's auth schema)
  -> POST /brokers/{id}/connect
  -> Backend creates the adapter via brokers/registry.py
  -> BaseBrokerAdapter (broker-agnostic interface)
  -> Strategy Engines (SMC, Liquidity, Momentum, Volume, Exhaustion, MTF, Fakeout, Regime, CRT)
  -> AI Decision Brain
  -> Risk Firewall
  -> Execution Router (checks broker capabilities before every order)
  -> Selected Broker Adapter
```

Every layer above the broker adapters is 100% broker-agnostic. No engine,
the AI Brain, the Risk Firewall, or Android screens contain Deriv/MT5/
Exness-specific code. Add a new broker by writing one new
`XyzAdapter(BaseBrokerAdapter)` and adding one line to
`brokers/registry.py` — nothing else changes.

## Broker status

| Broker | Auth method (confirmed, not guessed) | Status |
|---|---|---|
| Mock (paper trading) | none | **Verified — safe to use now** |
| Deriv | Personal Access Token or OAuth2, over WebSocket | Not implemented |
| MetaTrader 5 | account number + password + server, via local MT5 terminal | Not implemented |
| Exness | Same as MT5 — Exness has no separate trading API; retail execution goes through MT4/MT5 with Exness-issued credentials | Not implemented |

`brokers/baseAdapter.py`'s `BrokerCapabilities.verified` flag is checked
by `executionRouter.py` on every single order — an unverified broker
cannot execute a trade no matter how confident the AI is. This is
enforced in code (see `tests/3_execution_router/`), not just documented.

## Live trading safety

`backend/src/config/config.json` → `"live_trading_enabled": false` by
default. `main.py` checks this explicitly before calling the execution
router — see `tests/4_mock_broker_integration/test_config_live_trading_disabled_by_default`.

## Testing

Six tiers — see `tests/README.md` for the full breakdown. Tiers 1-4 need
no credentials and no network; run them anytime:

```bash
cd backend/src
python3 ../../tests/1_core_strategy/test_engines.py
python3 ../../tests/2_risk_firewall/test_risk_firewall.py
python3 ../../tests/3_execution_router/test_execution_router.py
python3 ../../tests/4_mock_broker_integration/test_pipeline.py
```

(Or `pip install pytest` and run them as a normal pytest suite — they're
written in standard pytest style, just also runnable directly.)

Tiers 5 (read-only broker integration) and 6 (live execution) are gated
behind real credentials and explicit human authorization — see their
READMEs before touching them.

## Run the backend locally

```bash
cd backend
pip install -r requirements.txt
cd src
python3 main.py                              # single pipeline cycle, mock broker
uvicorn api.server:app --host 0.0.0.0 --port 8000   # full API, run from backend/src
```

## Push to GitHub

```bash
git add .
git commit -m "describe what changed"
git push
```

## What's still not built

- `marketData.py` / `websocketManager.py` — real live data feed (currently
  `MockBrokerAdapter.get_market_data()` generates synthetic candles)
- `straddleEngine.py` — range/breakout detection (spec section 5)
- Any real broker adapter's actual API calls (all three are honest
  `NotImplementedError` stubs with correct auth schemas — see each file)
- Database persistence (`database/models.py` schema exists, nothing writes to it yet)
- Backtesting (`backtest/` still stubs)

## Straddle engine (spec section 5) — now implemented

`engines/straddleEngine.py` detects consolidation ranges (calibrated
against measured width-to-ATR ratios, not guessed numbers — see the
module docstring) and produces a TWO_SIDED or DIRECTIONAL straddle setup.
`main.py` routes RANGING-regime cycles through this path automatically,
gated by `riskFirewall.check_setup()` and `executionRouter`'s capability
checks exactly like the AI Brain's directional path — same protections,
different entry logic. Falls through to the normal AI Brain path if
straddleEngine finds no valid range despite the RANGING classification.

## Market Data Engine (spec section 2/31) — now implemented

`data/marketData.py` is a broker-agnostic layer over any `BaseBrokerAdapter`:
multi-timeframe fetching in one call, short-TTL caching, and every fetch
run through `data/dataValidator.py` (gap/duplicate/invalid-OHLC/staleness
checks). This closes a real gap: `riskFirewall.AccountState.market_data_stale`
previously was hardcoded `False` in `main.py` and never actually connected
to anything — now a stale or corrupt candle series blocks a trade before
the engines even run, regardless of AI confidence or `live_trading_enabled`
(see `tests/4_mock_broker_integration/test_stale_market_data_blocks_trade_even_with_trivial_confidence_bar`).

`data/websocketManager.py` is a generic reconnect/backoff/heartbeat state
machine (spec section 31) — broker-agnostic, no Deriv/MT5-specific code.
Any future adapter with a persistent connection wraps this instead of
reimplementing exponential backoff from scratch.

Honest limitation: `MockBrokerAdapter` still generates synthetic candles
underneath this layer — there's no real live feed until a real broker
adapter (Deriv or MT5) is implemented and plugged in. This is the
infrastructure that becomes live the moment that happens; it was built
now because it exercises the exact same interface a real adapter will
use, and the stale-data protection is real today even with mock data.
