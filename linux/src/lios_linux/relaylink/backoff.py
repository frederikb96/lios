"""Exponential backoff with jitter for reconnecting to `/api/stream`.

Per the relay's own reconnect contract (`lios_relay.api.stream` module docstring): 1s, 2s, 4s,
... capped at 60s, with jitter, and never a reason to stop reconnecting -- a server-initiated
close is treated identically to a network error.
"""

from __future__ import annotations

import random

#: The reconnect delay never exceeds this many seconds, however many attempts have failed.
MAX_DELAY_SECONDS = 60.0

#: The first attempt's delay, before any exponential growth.
BASE_DELAY_SECONDS = 1.0


def next_delay(attempt: int, *, rng: random.Random | None = None) -> float:
    """The delay before reconnect attempt number `attempt` (0-indexed: 0 is the first retry).

    Jitter is a uniform random factor in `[0.5, 1.5)` applied to the capped exponential value,
    so many clients reconnecting after the same relay restart do not all retry in lockstep.

    Raises:
        ValueError: `attempt` is negative.
    """
    if attempt < 0:
        raise ValueError(f"attempt must be >= 0, got {attempt}")
    rng = rng or random.Random()
    uncapped = BASE_DELAY_SECONDS * float(2**attempt)
    capped = min(uncapped, MAX_DELAY_SECONDS)
    jitter = rng.uniform(0.5, 1.5)
    return float(capped * jitter)
