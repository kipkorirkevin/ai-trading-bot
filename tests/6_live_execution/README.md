# Tier 6: live broker execution tests

**Do not automate this tier. Do not add it to CI. Do not add a pytest
file here that runs by default.**

This tier means placing real orders (even tiny ones, even on symbols
chosen to minimize risk) against a real broker connection. That requires,
every single time, before running anything in this directory:

1. A real, tested, `verified=True` broker adapter (tiers 1-5 all passing
   for that broker first).
2. `live_trading_enabled: true` explicitly set in `config.json` — never
   left on by default, and reverted to `false` immediately after the
   test run.
3. Explicit human authorization for that specific run — not a standing
   approval, not a config flag checked once. Someone needs to decide
   "yes, place a real order, right now" every time this tier runs.
4. A demo/paper account wherever the broker offers one, tried first.
   Real-money execution testing only after demo testing has already
   passed, and only with position sizes small enough that a total loss
   is a non-event.

When you're ready to build this tier, the guard to write first is a
CLI flag or environment variable that does not exist yet by design —
e.g. requiring `--i-understand-this-places-real-orders` on the command
line, checked before a single test in this directory is allowed to
collect. Write that guard before you write the first live-order test,
not after.
