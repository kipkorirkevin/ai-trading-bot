# Test tiers

Run tiers 1-4 freely and often — no credentials, no network, no risk.
Tiers 5-6 touch real broker infrastructure and are gated accordingly.

| Tier | Directory | What it tests | Needs |
|---|---|---|---|
| 1 | `1_core_strategy/` | SMC, liquidity, momentum, volume, exhaustion, MTF, fakeout, regime, CRT, AI Brain — pure functions on synthetic candles | nothing |
| 2 | `2_risk_firewall/` | riskFirewall.check() gates: daily loss, drawdown, spread, max trades, duplicates, session, consecutive losses | nothing |
| 3 | `3_execution_router/` | executionRouter capability checks — verified/unverified brokers, lot bounds, SL/TP support, straddle/hedging requirements | nothing |
| 4 | `4_mock_broker_integration/` | Full main.py pipeline against MockBrokerAdapter, both `live_trading_enabled` true and false | nothing |
| 5 | `5_broker_readonly_integration/` | Real connect() + get_account_info()/get_price()/get_market_data() against a **demo** account — no orders placed | real demo credentials, network |
| 6 | `6_live_execution/` | Real order placement | explicit human sign-off per run — never automated, never in CI |

## Running

```bash
cd backend/src
python3 -m pytest ../../tests/1_core_strategy ../../tests/2_risk_firewall \
                   ../../tests/3_execution_router ../../tests/4_mock_broker_integration -v
```

Tiers 5 and 6 are intentionally NOT wired into a single "run everything"
command. Tier 5 requires you to export real demo credentials as
environment variables and run its file directly; tier 6 requires reading
`6_live_execution/README.md` first and passing an explicit
`--i-understand-this-places-real-orders` flag that does not exist yet by
design — build that guard before this tier's tests do anything but skip.
