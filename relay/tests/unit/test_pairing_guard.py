"""The pairing guard: a sliding window over refused codes, shared by every caller."""

from __future__ import annotations

from lios_relay.pairing_guard import PairingGuard


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_until_the_budget_is_spent() -> None:
    clock = _Clock()
    guard = PairingGuard(3, 300, clock)
    for _ in range(2):
        guard.record_failure()
        assert guard.retry_after() is None
    guard.record_failure()
    assert guard.retry_after() is not None


def test_retry_after_counts_down_to_the_oldest_refusal_leaving() -> None:
    clock = _Clock()
    guard = PairingGuard(2, 300, clock)
    guard.record_failure()
    clock.now += 100
    guard.record_failure()
    assert guard.retry_after() == 201
    clock.now += 150
    assert guard.retry_after() == 51


def test_unlocks_when_the_window_has_passed() -> None:
    clock = _Clock()
    guard = PairingGuard(2, 300, clock)
    guard.record_failure()
    guard.record_failure()
    assert guard.retry_after() is not None
    clock.now += 300
    assert guard.retry_after() is None


def test_a_locked_guard_does_not_grow_with_every_probe() -> None:
    clock = _Clock()
    guard = PairingGuard(2, 300, clock)
    for _ in range(5):
        guard.record_failure()
    clock.now += 299
    assert guard.retry_after() is not None
    clock.now += 2
    assert guard.retry_after() is None
