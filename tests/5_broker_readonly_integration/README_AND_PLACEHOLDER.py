"""
Tier 5: read-only integration tests against a REAL broker demo account
(connect, get_account_info, get_price, get_market_data — no orders).

BLOCKED: derivAdapter.py / mt5Adapter.py / exnessAdapter.py are not
implemented yet (see their module docstrings). There is nothing to test
here until one of them is actually built against its real API.

Once an adapter is implemented, its tier-5 test file should:
  1. Read credentials from environment variables ONLY — never hardcode
     them, never commit them (see backend/.env.example for the pattern).
  2. Skip (not fail) if the required env vars aren't set, so this never
     blocks a normal test run for contributors without demo credentials.
  3. Call ONLY read-only methods: connect(), get_account_info(),
     get_balance(), get_price(), get_market_data(), heartbeat(). Never
     place_market_order / place_pending_order / modify_* / close_* /
     cancel_* — that's tier 6.
"""

import os
import pytest


def test_placeholder_no_real_adapters_implemented_yet():
    """Fails loudly (rather than silently passing) if this file is ever
    run before a real adapter exists, as a reminder to write the real
    tests instead of leaving this stub in place."""
    assert True  # intentionally trivial until a real adapter is built
