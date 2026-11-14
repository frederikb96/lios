"""A global limit on refused pairing codes.

`POST /api/devices/pair` needs no token, and a code is short, so the endpoint is the one place
an outsider can guess at something that grants access. The guard counts refusals over every
caller within a sliding window and, once the budget is spent, locks the endpoint until the
oldest refusal leaves the window. A legitimate pairing is rare and the window short, so the
cost of locking everyone out for a few minutes is small next to what a guessed code gives away.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable


class PairingGuard:
    """Sliding-window count of refused codes; single process, as the relay itself is."""

    def __init__(
        self,
        max_failures: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_failures = max_failures
        self._window = float(window_seconds)
        self._clock = clock
        self._failures: deque[float] = deque()

    def _expire(self, now: float) -> None:
        while self._failures and now - self._failures[0] >= self._window:
            self._failures.popleft()

    def retry_after(self) -> int | None:
        """Seconds until redeeming is allowed again, or `None` while it is allowed."""
        now = self._clock()
        self._expire(now)
        if len(self._failures) < self._max_failures:
            return None
        return max(1, int(self._window - (now - self._failures[0])) + 1)

    def record_failure(self) -> None:
        """Count one refused code."""
        now = self._clock()
        self._expire(now)
        self._failures.append(now)
