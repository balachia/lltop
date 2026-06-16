"""TDD: /api/metrics ring buffer → per-model rollup."""

from __future__ import annotations

from lltop.aggregator import ModelStats, rollup
from lltop.client import ActivityLogEntry


def _entry(
    id: int,
    model: str,
    *,
    inp: int = 100,
    out: int = 50,
    cache: int = 0,
    tps: float = 90.0,
    dur: int = 1000,
    status: int = 200,
    ts: str = "2026-05-24T10:00:00+08:00",
) -> ActivityLogEntry:
    return ActivityLogEntry(
        id=id,
        timestamp=ts,
        model=model,
        req_path="/v1/chat/completions",
        status_code=status,
        input_tokens=inp,
        output_tokens=out,
        cache_tokens=cache,
        prompt_per_second=1000.0,
        tokens_per_second=tps,
        duration_ms=dur,
    )


# ---- empty / trivial ------------------------------------------------------


def test_rollup_empty_returns_empty():
    assert rollup([]) == {}


def test_rollup_single_entry():
    stats = rollup([_entry(0, "m1", inp=100, out=50, tps=80.0, dur=500)])
    assert set(stats) == {"m1"}
    s = stats["m1"]
    assert isinstance(s, ModelStats)
    assert s.req_count == 1
    assert s.total_input_tokens == 100
    assert s.total_output_tokens == 50
    assert s.avg_tokens_per_second == 80.0
    assert s.avg_duration_ms == 500.0
    assert s.success_rate == 1.0


# ---- aggregation ----------------------------------------------------------


def test_rollup_sums_tokens_same_model():
    stats = rollup(
        [
            _entry(0, "m1", inp=100, out=50, cache=10),
            _entry(1, "m1", inp=200, out=70, cache=5),
        ]
    )
    s = stats["m1"]
    assert s.req_count == 2
    assert s.total_input_tokens == 300
    assert s.total_output_tokens == 120
    assert s.total_cache_tokens == 15


def test_rollup_groups_distinct_models():
    stats = rollup([_entry(0, "m1"), _entry(1, "m2"), _entry(2, "m1")])
    assert stats["m1"].req_count == 2
    assert stats["m2"].req_count == 1


def test_avg_tokens_per_second_excludes_zero_output():
    """Entries with no decoded output skew the decode-speed average; exclude them."""
    stats = rollup(
        [
            _entry(0, "m1", out=50, tps=100.0),
            _entry(1, "m1", out=0, tps=0.0),  # e.g. a cache-only / empty completion
        ]
    )
    assert stats["m1"].avg_tokens_per_second == 100.0
    assert stats["m1"].req_count == 2  # still counted as a request


def test_avg_tokens_per_second_zero_when_all_empty():
    stats = rollup([_entry(0, "m1", out=0, tps=0.0)])
    assert stats["m1"].avg_tokens_per_second == 0.0


def test_success_rate_mixed():
    stats = rollup(
        [
            _entry(0, "m1", status=200),
            _entry(1, "m1", status=500),
            _entry(2, "m1", status=200),
            _entry(3, "m1", status=404),
        ]
    )
    assert stats["m1"].success_rate == 0.5


def test_last_seen_is_latest_timestamp():
    stats = rollup(
        [
            _entry(0, "m1", ts="2026-05-24T10:00:00+08:00"),
            _entry(1, "m1", ts="2026-05-24T14:30:00+08:00"),
            _entry(2, "m1", ts="2026-05-24T12:00:00+08:00"),
        ]
    )
    assert stats["m1"].last_seen == "2026-05-24T14:30:00+08:00"


# ---- against real fixture -------------------------------------------------


def test_rollup_real_fixture(fx_api_metrics_populated):
    entries = [ActivityLogEntry.from_json(d) for d in fx_api_metrics_populated]
    stats = rollup(entries)
    assert set(stats) == {"gemma4-e4b", "gemma4-31b", "gemma4-26b-a4b"}
    assert stats["gemma4-e4b"].req_count == 11
    assert stats["gemma4-31b"].req_count == 10
    assert stats["gemma4-26b-a4b"].req_count == 6
    # all 200s in this capture
    assert all(s.success_rate == 1.0 for s in stats.values())
    # decode speed should be a sane positive number
    assert all(s.avg_tokens_per_second > 0 for s in stats.values())
