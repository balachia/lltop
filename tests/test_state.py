"""TDD: compose client + ps + config into a Snapshot."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from llouie.aggregator import ModelStats
from llouie.client import Model, RunningModel
from llouie.state import (
    LoadObserver,
    ModelView,
    Snapshot,
    build_snapshot,
    load_groups,
    load_pinned,
    unload_eta_seconds,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _model(name: str) -> Model:
    return Model(id=name, created=0, owned_by="llama-swap")


def _running(name: str, port: int, ttl: int = 600) -> RunningModel:
    return RunningModel(
        model=name,
        state="ready",
        proxy=f"http://localhost:{port}",
        ttl=ttl,
        cmd=f"/bin/llama-server --port {port}",
        port=port,
    )


def _stats(name: str, req_count: int = 5) -> ModelStats:
    return ModelStats(
        model=name,
        req_count=req_count,
        total_input_tokens=1000,
        total_output_tokens=500,
        total_cache_tokens=0,
        avg_tokens_per_second=90.0,
        avg_duration_ms=1000.0,
        success_rate=1.0,
        last_seen="2026-05-24T14:00:00+08:00",
    )


# ---- load_groups ----------------------------------------------------------


def test_load_groups_maps_members():
    groups = load_groups(FIXTURES / "config_with_groups.yaml")
    assert groups["gemma4-26b-a4b"] == "coders"
    assert groups["qwen3-coder-next"] == "coders"
    assert groups["gemma4-31b"] == "heavy"
    assert groups["mistral-medium-3.5"] == "heavy"


def test_load_groups_ungrouped_model_absent():
    groups = load_groups(FIXTURES / "config_with_groups.yaml")
    assert "gemma4-e4b" not in groups


def test_load_groups_no_groups_section_returns_empty(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("models:\n  m1:\n    cmd: foo\n")
    assert load_groups(cfg) == {}


# ---- load_pinned ----------------------------------------------------------


def test_load_pinned_finds_persistent_members():
    pinned = load_pinned(FIXTURES / "config_pinned.yaml")
    assert pinned == {"gemma4-e4b"}


def test_load_pinned_excludes_non_persistent_groups():
    pinned = load_pinned(FIXTURES / "config_pinned.yaml")
    assert "gemma4-31b" not in pinned  # in a swap group, not persistent


def test_load_pinned_empty_when_no_persistent(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("groups:\n  g:\n    swap: true\n    members: [m1]\n")
    assert load_pinned(cfg) == set()


# ---- build_snapshot -------------------------------------------------------


def test_build_snapshot_all_unloaded():
    configured = [_model("m1"), _model("m2")]
    snap = build_snapshot(configured, [], {}, {}, {})
    assert isinstance(snap, Snapshot)
    assert len(snap.models) == 2
    assert all(isinstance(v, ModelView) for v in snap.models)
    assert all(v.status == "unloaded" for v in snap.models)
    assert all(v.rss_kb is None for v in snap.models)
    assert all(v.ttl is None for v in snap.models)


def test_build_snapshot_one_loaded():
    configured = [_model("m1"), _model("m2")]
    running = [_running("m1", 5801, ttl=600)]
    rss = {"m1": 9_000_000}
    snap = build_snapshot(configured, running, rss, {}, {})
    m1 = next(v for v in snap.models if v.name == "m1")
    m2 = next(v for v in snap.models if v.name == "m2")
    assert m1.status == "loaded"
    assert m1.rss_kb == 9_000_000
    assert m1.ttl == 600
    assert m2.status == "unloaded"
    assert m2.rss_kb is None


def test_build_snapshot_attaches_group():
    snap = build_snapshot([_model("m1")], [], {}, {}, {"m1": "coders"})
    assert snap.models[0].group == "coders"


def test_build_snapshot_marks_pinned():
    snap = build_snapshot(
        [_model("m1"), _model("m2")], [], {}, {}, {}, pinned={"m1"}
    )
    by_name = {v.name: v for v in snap.models}
    assert by_name["m1"].pinned is True
    assert by_name["m2"].pinned is False


def test_build_snapshot_attaches_stats():
    snap = build_snapshot([_model("m1")], [], {}, {"m1": _stats("m1", 7)}, {})
    assert snap.models[0].stats is not None
    assert snap.models[0].stats.req_count == 7


def test_build_snapshot_loaded_sorted_first():
    configured = [_model("alpha"), _model("beta"), _model("gamma")]
    running = [_running("gamma", 5801)]
    snap = build_snapshot(configured, running, {"gamma": 100}, {}, {})
    # loaded models come first, then alphabetical
    assert snap.models[0].name == "gamma"
    assert snap.models[0].status == "loaded"
    assert [v.name for v in snap.models[1:]] == ["alpha", "beta"]


def test_snapshot_loaded_count_and_total_rss():
    configured = [_model("m1"), _model("m2"), _model("m3")]
    running = [_running("m1", 5801), _running("m2", 5802)]
    rss = {"m1": 9_000_000, "m2": 18_000_000}
    snap = build_snapshot(configured, running, rss, {}, {})
    assert snap.loaded_count == 2
    assert snap.total_rss_kb == 27_000_000


def test_snapshot_total_rss_zero_when_idle():
    snap = build_snapshot([_model("m1")], [], {}, {}, {})
    assert snap.total_rss_kb == 0
    assert snap.loaded_count == 0


# ---- unload_eta_seconds ---------------------------------------------------

_NOW = datetime(2026, 5, 24, 14, 35, 0, tzinfo=timezone(timedelta(hours=8)))


def test_eta_basic_countdown():
    # ttl 600s, last request 2min ago → ~480s remaining
    last = "2026-05-24T14:33:00+08:00"
    assert unload_eta_seconds(600, last, _NOW) == 480


def test_eta_negative_when_overdue():
    # last logged request 20min ago, ttl only 600s → proxy says overdue.
    # Return the signed value (negative) so the caller can treat it as "stale".
    last = "2026-05-24T14:15:00+08:00"  # 20min before _NOW
    assert unload_eta_seconds(600, last, _NOW) == -600


def test_eta_none_when_ttl_missing():
    assert unload_eta_seconds(None, "2026-05-24T14:33:00+08:00", _NOW) is None


def test_eta_none_when_last_seen_missing():
    assert unload_eta_seconds(600, None, _NOW) is None


def test_eta_none_when_last_seen_naive():
    """A timezone-naive timestamp can't be reasoned about; ignore it."""
    assert unload_eta_seconds(600, "2026-05-24T14:33:00", _NOW) is None


def test_eta_uses_loaded_since_when_no_metrics():
    """Health-probe load: no logged request, but llouie saw it load 1min ago."""
    loaded_since = _NOW - timedelta(minutes=1)
    assert unload_eta_seconds(600, None, _NOW, loaded_since=loaded_since) == 540


def test_eta_takes_max_of_request_and_load_time():
    # last request 18min ago (overdue), but observed loaded 2min ago → use load time
    last = "2026-05-24T14:17:00+08:00"
    loaded_since = _NOW - timedelta(minutes=2)
    assert unload_eta_seconds(600, last, _NOW, loaded_since=loaded_since) == 480


def test_eta_prefers_request_when_more_recent_than_load():
    # observed loaded 5min ago, but a request came in 1min ago → use the request
    last = "2026-05-24T14:34:00+08:00"  # 1min before _NOW
    loaded_since = _NOW - timedelta(minutes=5)
    assert unload_eta_seconds(600, last, _NOW, loaded_since=loaded_since) == 540


# ---- LoadObserver ---------------------------------------------------------


def test_observer_records_first_seen():
    obs = LoadObserver()
    t0 = _NOW
    obs.observe({"m1"}, t0)
    assert obs.since["m1"] == t0


def test_observer_keeps_original_load_time_across_refreshes():
    obs = LoadObserver()
    t0 = _NOW
    obs.observe({"m1"}, t0)
    obs.observe({"m1"}, t0 + timedelta(seconds=30))  # still loaded later
    assert obs.since["m1"] == t0  # floor unchanged


def test_observer_drops_unloaded_model():
    obs = LoadObserver()
    obs.observe({"m1"}, _NOW)
    obs.observe(set(), _NOW + timedelta(seconds=5))  # m1 gone
    assert "m1" not in obs.since


def test_observer_reload_resets_floor():
    obs = LoadObserver()
    obs.observe({"m1"}, _NOW)
    obs.observe(set(), _NOW + timedelta(seconds=5))  # unloaded
    t2 = _NOW + timedelta(seconds=10)
    obs.observe({"m1"}, t2)  # reloaded
    assert obs.since["m1"] == t2
