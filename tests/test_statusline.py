"""TDD: one-line statusline output for tmux."""

from __future__ import annotations

from llouie.client import Model, RunningModel
from llouie.state import build_snapshot
from llouie.statusline import status_line


def _model(name: str) -> Model:
    return Model(id=name, created=0, owned_by="llama-swap")


def _running(name: str, port: int) -> RunningModel:
    return RunningModel(
        model=name, state="ready", proxy=f"http://localhost:{port}",
        ttl=600, cmd=f"/bin/llama-server --port {port}", port=port,
    )


def test_statusline_idle():
    snap = build_snapshot([_model("m1")], [], {}, {}, {})
    assert status_line(snap) == "llm:idle"


def test_statusline_one_loaded():
    snap = build_snapshot(
        [_model("m1"), _model("m2")],
        [_running("m1", 5801)],
        {"m1": 9_834_592},
        {},
        {},
    )
    assert status_line(snap) == "llm:m1 9.4G"


def test_statusline_multiple_loaded_shows_count_and_total():
    snap = build_snapshot(
        [_model("m1"), _model("m2"), _model("m3")],
        [_running("m1", 5801), _running("m2", 5802)],
        {"m1": 9_000_000, "m2": 18_000_000},
        {},
        {},
    )
    # 2 loaded → count marker + total RAM (27M KB ≈ 25.7G)
    assert status_line(snap) == "llm:2▪ 25.7G"
