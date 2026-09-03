"""`format_timestamp`: local time, relative for anything recent, absolute otherwise."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from lios_linux.ui.timestamps import format_timestamp

_NOW = datetime(2026, 9, 3, 20, 35, 51, tzinfo=UTC)


@pytest.fixture
def berlin_local_time() -> Iterator[None]:
    """Pins the system's local timezone so `astimezone()` has something other than UTC to
    convert to -- otherwise a CI runner whose own timezone happens to be UTC would let a
    conversion bug through unnoticed."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Berlin"
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = previous
        time.tzset()


def test_a_moment_ago_reads_as_just_now() -> None:
    created_at = _NOW - timedelta(seconds=5)
    assert format_timestamp(created_at, now=_NOW) == "Just now"


def test_a_future_timestamp_reads_as_just_now() -> None:
    """Clock skew or network latency putting `created_at` a hair after `now` must not crash
    or print a negative duration."""
    created_at = _NOW + timedelta(seconds=2)
    assert format_timestamp(created_at, now=_NOW) == "Just now"


def test_singular_minute() -> None:
    created_at = _NOW - timedelta(minutes=1, seconds=5)
    assert format_timestamp(created_at, now=_NOW) == "1 minute ago"


def test_plural_minutes() -> None:
    created_at = _NOW - timedelta(minutes=5)
    assert format_timestamp(created_at, now=_NOW) == "5 minutes ago"


def test_just_under_an_hour_is_still_relative() -> None:
    created_at = _NOW - timedelta(minutes=59)
    assert format_timestamp(created_at, now=_NOW) == "59 minutes ago"


def test_over_an_hour_same_day_is_a_local_clock_time() -> None:
    created_at = _NOW - timedelta(hours=2)
    assert format_timestamp(created_at, now=_NOW) == created_at.astimezone().strftime("%H:%M")


def test_a_prior_day_is_a_local_date_and_time() -> None:
    created_at = _NOW - timedelta(days=3)
    expected = created_at.astimezone().strftime("%Y-%m-%d %H:%M")
    assert format_timestamp(created_at, now=_NOW) == expected


def test_utc_is_converted_to_local_time_not_left_as_is(berlin_local_time: None) -> None:
    """A relay timestamp recorded in UTC must not be rendered as if it already were the
    system's local time -- this is exactly the bug this module fixes. Berlin is UTC+2 on this
    date, so `18:35` UTC must read `20:35`, not `18:35`."""
    created_at = datetime(2026, 9, 3, 18, 35, 51, tzinfo=UTC)
    now = datetime(2026, 9, 3, 21, 0, 0, tzinfo=UTC)
    assert format_timestamp(created_at, now=now) == "20:35"
