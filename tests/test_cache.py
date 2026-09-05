"""Tests for the element-set TTL cache.

Time is injected rather than slept through, so these run instantly and
deterministically.
"""

from __future__ import annotations

from src.cache import TTLCache


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _cache(clock: Clock, *, ttl: float = 10.0, max_entries: int = 8) -> TTLCache:
    return TTLCache(ttl_seconds=ttl, max_entries=max_entries, clock=clock)


def test_a_fresh_entry_is_returned() -> None:
    cache = _cache(Clock())
    cache.set("41838:30", ["record"])
    assert cache.get("41838:30") == ["record"]


def test_a_missing_key_is_none() -> None:
    assert _cache(Clock()).get("nothing") is None


def test_an_expired_entry_is_dropped_not_served() -> None:
    clock = Clock()
    cache = _cache(clock)
    cache.set("41838:30", ["record"])
    clock.advance(10.5)
    assert cache.get("41838:30") is None
    assert len(cache) == 0


def test_an_entry_survives_right_up_to_its_ttl() -> None:
    clock = Clock()
    cache = _cache(clock)
    cache.set("41838:30", ["record"])
    clock.advance(10.0)
    assert cache.get("41838:30") == ["record"]


def test_the_oldest_entry_is_evicted_when_full() -> None:
    cache = _cache(Clock(), max_entries=2)
    for key in ("a", "b", "c"):
        cache.set(key, key)
    assert cache.get("a") is None
    assert cache.get("c") == "c"
    assert len(cache) == 2


def test_re_setting_a_key_refreshes_it_rather_than_duplicating_it() -> None:
    clock = Clock()
    cache = _cache(clock, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    clock.advance(5.0)
    cache.set("a", 3)
    cache.set("c", 4)
    # "b" was the oldest by then, so "a" survives with its new value.
    assert cache.get("a") == 3
    assert cache.get("b") is None
