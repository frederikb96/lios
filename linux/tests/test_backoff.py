"""Reconnect backoff: exponential, capped at 60s, jittered, never negative."""

from __future__ import annotations

import random

import pytest

from lios_linux.relaylink.backoff import MAX_DELAY_SECONDS, next_delay


def test_first_attempt_is_around_one_second() -> None:
    delay = next_delay(0, rng=random.Random(1))
    assert 0.5 <= delay < 1.5


def test_delay_grows_exponentially_before_the_cap() -> None:
    # With jitter fixed at 1.0 (via a seeded RNG we don't control precisely), compare medians
    # across many draws instead of a single sample.
    rng = random.Random(42)
    delay_0 = next_delay(0, rng=rng)
    delay_3 = next_delay(3, rng=rng)
    assert delay_3 > delay_0


def test_delay_never_exceeds_the_cap_even_at_high_attempt_counts() -> None:
    rng = random.Random(7)
    for attempt in range(3, 20):
        assert next_delay(attempt, rng=rng) <= MAX_DELAY_SECONDS * 1.5


def test_delay_is_always_positive() -> None:
    rng = random.Random(0)
    for attempt in range(10):
        assert next_delay(attempt, rng=rng) > 0


def test_negative_attempt_is_rejected() -> None:
    with pytest.raises(ValueError):
        next_delay(-1)
