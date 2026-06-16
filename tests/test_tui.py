"""Smoke tests: the dashboard app boots and populates tables from a Snapshot."""

from __future__ import annotations

import asyncio

from llouie.aggregator import ModelStats
from llouie.client import Model, RunningModel
from llouie.state import Snapshot, build_snapshot
from llouie.tui.app import DashboardApp, resolved_layout
from llouie.tui.logtail import LogTail
from textual.widgets import DataTable


# ---- responsive layout (pure breakpoint) ----------------------------------


def test_resolved_layout_auto_wide_when_broad():
    assert resolved_layout(140, "auto") == "wide"


def test_resolved_layout_auto_narrow_when_slim():
    assert resolved_layout(70, "auto") == "narrow"


def test_resolved_layout_forced_modes_ignore_width():
    assert resolved_layout(40, "wide") == "wide"
    assert resolved_layout(300, "narrow") == "narrow"


def _model(name: str) -> Model:
    return Model(id=name, created=0, owned_by="llama-swap")


def _running(name: str, port: int) -> RunningModel:
    return RunningModel(
        model=name, state="ready", proxy=f"http://localhost:{port}",
        ttl=600, cmd=f"/bin/llama-server --port {port}", port=port,
    )


def _stats(name: str, req_count: int) -> ModelStats:
    return ModelStats(
        model=name, req_count=req_count, total_input_tokens=1000,
        total_output_tokens=500, total_cache_tokens=0, avg_tokens_per_second=90.0,
        avg_duration_ms=1000.0, success_rate=1.0,
        last_seen="2026-05-24T14:00:00+08:00",
    )


def _sample_snapshot() -> Snapshot:
    return build_snapshot(
        [_model("m1"), _model("m2"), _model("m3")],
        [_running("m1", 5801)],
        {"m1": 9_834_592},
        {"m1": _stats("m1", 7), "m2": _stats("m2", 3)},
        {"m1": "coders"},
    )


def _provider_for(snap: Snapshot):
    async def _p() -> Snapshot:
        return snap

    return _p


async def test_app_boots_no_crash():
    app = DashboardApp(_provider_for(_sample_snapshot()), refresh_interval=0, stream_logs=False)
    async with app.run_test():
        pass


async def test_inventory_table_populated():
    snap = _sample_snapshot()
    app = DashboardApp(_provider_for(snap), refresh_interval=0, stream_logs=False)
    async with app.run_test():
        inv = app.query_one("#inventory", DataTable)
        assert inv.row_count == 3


async def test_usage_table_only_models_with_activity():
    snap = _sample_snapshot()
    app = DashboardApp(_provider_for(snap), refresh_interval=0, stream_logs=False)
    async with app.run_test():
        usage = app.query_one("#usage", DataTable)
        assert usage.row_count == 2  # m1 and m2 have stats, m3 doesn't


async def test_summary_reflects_loaded_count():
    snap = _sample_snapshot()
    app = DashboardApp(_provider_for(snap), refresh_interval=0, stream_logs=False)
    async with app.run_test():
        assert "1/3 loaded" in app.summary_text
        assert "9.4G" in app.summary_text


async def test_refresh_action_repopulates():
    snap = _sample_snapshot()
    app = DashboardApp(_provider_for(snap), refresh_interval=0, stream_logs=False)
    async with app.run_test() as pilot:
        await pilot.press("r")
        inv = app.query_one("#inventory", DataTable)
        assert inv.row_count == 3  # not doubled


async def test_unload_key_calls_unloader_with_selected_model():
    snap = _sample_snapshot()  # m1 loaded, sorted first → cursor row 0
    calls: list[str] = []

    async def _unloader(model: str) -> None:
        calls.append(model)

    app = DashboardApp(
        _provider_for(snap), refresh_interval=0, stream_logs=False, unloader=_unloader
    )
    async with app.run_test() as pilot:
        await pilot.press("u")
        assert calls == ["m1"]


async def test_unload_key_noop_without_unloader():
    snap = _sample_snapshot()
    app = DashboardApp(_provider_for(snap), refresh_interval=0, stream_logs=False)
    async with app.run_test() as pilot:
        await pilot.press("u")  # no unloader → must not crash


async def test_unload_failure_surfaced():
    snap = _sample_snapshot()

    async def _boom(model: str) -> None:
        raise ConnectionError("nope")

    app = DashboardApp(
        _provider_for(snap), refresh_interval=0, stream_logs=False, unloader=_boom
    )
    async with app.run_test() as pilot:
        await pilot.press("u")
        assert "unload failed" in app.summary_text.lower()


async def test_load_key_calls_loader_with_selected_model():
    snap = _sample_snapshot()  # rows: m1(loaded), m2(idle), m3(idle)
    calls: list[str] = []

    async def _loader(model: str) -> None:
        calls.append(model)

    app = DashboardApp(
        _provider_for(snap), refresh_interval=0, stream_logs=False, loader=_loader
    )
    async with app.run_test() as pilot:
        # move cursor to an idle model (row 1 = m2) then load it
        app.query_one("#inventory", DataTable).move_cursor(row=1)
        await pilot.press("l")
        await app.workers.wait_for_complete()
        assert calls == ["m2"]


async def test_load_shows_loading_status_before_completion():
    snap = _sample_snapshot()  # rows: m1(loaded), m2(idle), m3(idle)
    gate = asyncio.Event()

    async def _loader(model: str) -> None:
        await gate.wait()  # block so the optimistic state is observable

    app = DashboardApp(
        _provider_for(snap), refresh_interval=0, stream_logs=False, loader=_loader
    )
    async with app.run_test() as pilot:
        inv = app.query_one("#inventory", DataTable)
        inv.move_cursor(row=1)  # m2 (idle)
        await pilot.press("l")
        # worker is blocked in the loader; m2's status should read "loading"
        status = str(inv.get_cell_at((1, 1)))
        assert "loading" in status.lower()
        gate.set()
        await app.workers.wait_for_complete()


async def test_load_key_noop_without_loader():
    snap = _sample_snapshot()
    app = DashboardApp(_provider_for(snap), refresh_interval=0, stream_logs=False)
    async with app.run_test() as pilot:
        await pilot.press("l")  # no loader → must not crash


async def test_load_failure_surfaced():
    snap = _sample_snapshot()

    async def _boom(model: str) -> None:
        raise ConnectionError("cold load failed")

    app = DashboardApp(
        _provider_for(snap), refresh_interval=0, stream_logs=False, loader=_boom
    )
    async with app.run_test() as pilot:
        await pilot.press("l")
        await app.workers.wait_for_complete()
        assert "load failed" in app.summary_text.lower()


async def test_cursor_preserved_across_refresh():
    snap = _sample_snapshot()  # rows: m1(loaded), m2, m3
    app = DashboardApp(_provider_for(snap), refresh_interval=0, stream_logs=False)
    async with app.run_test() as pilot:
        inv = app.query_one("#inventory", DataTable)
        inv.move_cursor(row=1)  # select m2
        assert str(inv.get_cell_at((inv.cursor_row, 0))) == "m2"
        await pilot.press("r")  # refresh re-renders the table
        assert str(inv.get_cell_at((inv.cursor_row, 0))) == "m2"


async def test_cursor_follows_model_when_order_changes():
    """If the selected model moves rows (e.g. it loads and sorts to top), the
    cursor should follow it by name, not stay on a stale index."""
    initial = _sample_snapshot()  # m1 loaded; m2,m3 idle
    # after refresh, m3 is now loaded too → sort order changes
    reordered = build_snapshot(
        [_model("m1"), _model("m2"), _model("m3")],
        [_running("m1", 5801), _running("m3", 5803)],
        {"m1": 9_000_000, "m3": 5_000_000},
        {},
        {},
    )
    snaps = iter([initial, reordered])

    async def _provider() -> Snapshot:
        return next(snaps)

    app = DashboardApp(_provider, refresh_interval=0, stream_logs=False)
    async with app.run_test() as pilot:
        inv = app.query_one("#inventory", DataTable)
        # select m2 (idle, row 1 in initial: m1,m2,m3)
        inv.move_cursor(row=1)
        assert str(inv.get_cell_at((inv.cursor_row, 0))) == "m2"
        await pilot.press("r")  # now m1,m3 loaded-first → m2 shifts to row 2
        assert str(inv.get_cell_at((inv.cursor_row, 0))) == "m2"


async def test_layout_narrow_class_when_terminal_slim():
    app = DashboardApp(_provider_for(_sample_snapshot()), refresh_interval=0, stream_logs=False)
    async with app.run_test(size=(80, 30)):
        assert app.query_one("#panels").has_class("narrow")


async def test_layout_wide_class_when_terminal_broad():
    app = DashboardApp(_provider_for(_sample_snapshot()), refresh_interval=0, stream_logs=False)
    async with app.run_test(size=(140, 40)):
        assert app.query_one("#panels").has_class("wide")


async def test_layout_forced_narrow_ignores_width():
    app = DashboardApp(
        _provider_for(_sample_snapshot()),
        refresh_interval=0,
        stream_logs=False,
        layout="narrow",
    )
    async with app.run_test(size=(200, 50)):
        assert app.query_one("#panels").has_class("narrow")


async def test_cycle_layout_key_advances_mode():
    app = DashboardApp(_provider_for(_sample_snapshot()), refresh_interval=0, stream_logs=False)
    async with app.run_test(size=(140, 40)) as pilot:
        assert app._layout_mode == "auto"
        await pilot.press("v")
        assert app._layout_mode == "wide"
        await pilot.press("v")
        assert app._layout_mode == "narrow"
        await pilot.press("v")
        assert app._layout_mode == "auto"


async def test_theme_applied():
    app = DashboardApp(
        _provider_for(_sample_snapshot()),
        refresh_interval=0,
        stream_logs=False,
        theme="nord",
    )
    async with app.run_test():
        assert app.theme == "nord"


async def test_default_theme_is_ansi_dark():
    app = DashboardApp(_provider_for(_sample_snapshot()), refresh_interval=0, stream_logs=False)
    async with app.run_test():
        assert app.theme == "ansi-dark"


async def test_log_pane_present():
    snap = _sample_snapshot()
    app = DashboardApp(_provider_for(snap), refresh_interval=0, stream_logs=False)
    async with app.run_test():
        assert app.query_one("#logtail", LogTail) is not None


async def test_provider_error_surfaced_not_crashed():
    async def _boom() -> Snapshot:
        raise ConnectionError("llama-swap down")

    app = DashboardApp(_boom, refresh_interval=0, stream_logs=False)
    async with app.run_test():
        assert "error" in app.summary_text.lower()
