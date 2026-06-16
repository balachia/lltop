"""End-to-end smoke tests against a real llama-swap on :1135.

Opt-in: `uv run pytest -m live`. Skipped in the default run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from llouie.client import LlamaSwapClient
from llouie.state import gather_snapshot
from llouie.statusline import status_line

pytestmark = pytest.mark.live

URL = "http://localhost:1135"
CONFIG = str(Path.home() / ".config" / "llama-swap" / "config.yaml")


async def test_live_list_models_nonempty():
    async with LlamaSwapClient(URL) as client:
        models = await client.list_models()
    assert len(models) > 0


async def test_live_gather_snapshot():
    async with LlamaSwapClient(URL) as client:
        snap = await gather_snapshot(client, CONFIG)
    # every configured model should appear exactly once
    names = [v.name for v in snap.models]
    assert len(names) == len(set(names))
    assert len(names) > 0
    # statusline must produce a non-empty string without raising
    line = status_line(snap)
    assert line.startswith("llm:")


async def test_live_running_and_rss_consistent():
    """Any model reported loaded should have non-None RSS attributed."""
    async with LlamaSwapClient(URL) as client:
        snap = await gather_snapshot(client, CONFIG)
    for v in snap.models:
        if v.status == "loaded":
            assert v.rss_kb is not None and v.rss_kb > 0
