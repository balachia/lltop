"""TDD: pure row builders for the dashboard tables."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from llouie.aggregator import ModelStats
from llouie.client import Model, RunningModel
from llouie.state import build_snapshot
from llouie.tui.rows import inventory_rows, usage_rows

_TZ8 = timezone(timedelta(hours=8))


def _model(name: str) -> Model:
    return Model(id=name, created=0, owned_by="llama-swap")


def _running(name: str, port: int, ttl: int = 600) -> RunningModel:
    return RunningModel(
        model=name, state="ready", proxy=f"http://localhost:{port}",
        ttl=ttl, cmd=f"/bin/llama-server --port {port}", port=port,
    )


def _stats(name: str, req_count: int, tps: float = 90.0) -> ModelStats:
    return ModelStats(
        model=name, req_count=req_count, total_input_tokens=1500,
        total_output_tokens=800, total_cache_tokens=0,
        avg_tokens_per_second=tps, avg_duration_ms=1000.0,
        success_rate=1.0, last_seen="2026-05-24T14:30:05+08:00",
    )


# ---- inventory_rows -------------------------------------------------------


def test_inventory_rows_one_loaded_one_not():
    snap = build_snapshot(
        [_model("m1"), _model("m2")],
        [_running("m1", 5801)],  # ttl 600
        {"m1": 9_834_592},
        {"m1": _stats("m1", 3)},  # last_seen 14:30:05
        {"m1": "coders"},
    )
    now = datetime(2026, 5, 24, 14, 35, 5, tzinfo=_TZ8)  # 5min after last_seen
    rows = inventory_rows(snap, now=now)
    assert len(rows) == 2
    # loaded first
    name, status, group, size, ram, unload_eta = rows[0]
    assert name == "m1"
    assert "loaded" in status.lower() or "●" in status
    assert group == "coders"
    assert ram == "9.4G"
    # 600s ttl - 300s elapsed = 300s remaining
    assert unload_eta == "5m0s/10m0s"


def test_inventory_rows_shows_disk_size():
    snap = build_snapshot(
        [_model("m1")], [], {}, {}, {}, disk_sizes={"m1": 20_761_804}  # ~19.8G
    )
    name, status, group, size, ram, unload_eta = inventory_rows(snap)[0]
    assert size == "19.8G"  # nominal cost-to-load, shown even though unloaded
    assert ram == "-"  # not loaded → no RSS


def test_inventory_rows_disk_size_dash_when_unresolved():
    snap = build_snapshot([_model("m1")], [], {}, {}, {})
    assert inventory_rows(snap)[0][3] == "-"


def test_inventory_rows_loaded_without_stats_shows_question():
    snap = build_snapshot(
        [_model("m1")], [_running("m1", 5801)], {"m1": 100}, {}, {}
    )
    unload_eta = inventory_rows(snap)[0][5]
    assert unload_eta == "?/10m0s"


def test_inventory_rows_overdue_eta_shows_question():
    """Loaded model whose only signal (stale metrics) predates its ttl → '?'."""
    snap = build_snapshot(
        [_model("m1")], [_running("m1", 5801)], {"m1": 100}, {"m1": _stats("m1", 1)}, {}
    )
    now = datetime(2026, 5, 24, 23, 0, 0, tzinfo=_TZ8)  # hours after last_seen
    assert inventory_rows(snap, now=now)[0][5] == "?/10m0s"


def test_inventory_rows_loaded_since_rescues_eta():
    """Stale metrics but llouie saw it load recently → sane countdown, not '?'."""
    snap = build_snapshot(
        [_model("m1")], [_running("m1", 5801)], {"m1": 100}, {"m1": _stats("m1", 1)}, {}
    )
    now = datetime(2026, 5, 24, 23, 0, 0, tzinfo=_TZ8)
    loaded_since = {"m1": now - timedelta(minutes=2)}  # observed 2min ago, ttl 600
    assert inventory_rows(snap, now=now, loaded_since=loaded_since)[0][5] == "8m0s/10m0s"


def test_inventory_rows_pinned_shows_pinned_not_countdown():
    snap = build_snapshot(
        [_model("m1")], [_running("m1", 5801)], {"m1": 100},
        {"m1": _stats("m1", 3)}, {}, pinned={"m1"},
    )
    assert inventory_rows(snap)[0][5] == "pinned"


def test_inventory_rows_loading_status_optimistic():
    """A model in the loading set (not yet loaded) shows a transient status."""
    snap = build_snapshot([_model("m1"), _model("m2")], [], {}, {}, {})
    rows = inventory_rows(snap, loading={"m2"})
    by_name = {r[0]: r for r in rows}
    assert "loading" in by_name["m2"][1].lower()
    assert by_name["m1"][1] == "idle"


def test_inventory_rows_loaded_beats_loading_marker():
    """If the snapshot already shows the model loaded, loaded status wins."""
    snap = build_snapshot(
        [_model("m1")], [_running("m1", 5801)], {"m1": 100}, {}, {}
    )
    status = inventory_rows(snap, loading={"m1"})[0][1]
    assert "loaded" in status.lower()


def test_inventory_rows_unloaded_shows_dashes():
    snap = build_snapshot([_model("m2")], [], {}, {}, {})
    name, status, group, size, ram, unload_eta = inventory_rows(snap)[0]
    assert name == "m2"
    assert size == "-"
    assert ram == "-"
    assert unload_eta == "-"
    assert group == "-"


# ---- usage_rows -----------------------------------------------------------


def test_usage_rows_only_models_with_activity():
    snap = build_snapshot(
        [_model("m1"), _model("m2")],
        [],
        {},
        {"m1": _stats("m1", 5)},  # only m1 has stats
        {},
    )
    rows = usage_rows(snap)
    assert len(rows) == 1
    assert rows[0][0] == "m1"


def test_usage_rows_sorted_by_req_count_desc():
    snap = build_snapshot(
        [_model("m1"), _model("m2"), _model("m3")],
        [],
        {},
        {"m1": _stats("m1", 3), "m2": _stats("m2", 11), "m3": _stats("m3", 7)},
        {},
    )
    names = [r[0] for r in usage_rows(snap)]
    assert names == ["m2", "m3", "m1"]


def test_usage_rows_formats_counts_and_tps():
    snap = build_snapshot(
        [_model("m1")], [], {}, {"m1": _stats("m1", 1234, tps=91.305)}, {}
    )
    name, reqs, intok, outtok, tps, last_seen = usage_rows(snap)[0]
    assert reqs == "1.2k"
    assert intok == "1.5k"
    assert outtok == "800"
    assert tps == "91 t/s"
    assert last_seen == "14:30:05"


def test_usage_rows_empty_when_no_activity():
    snap = build_snapshot([_model("m1")], [], {}, {}, {})
    assert usage_rows(snap) == []
