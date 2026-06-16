"""One-line status output for tmux statuslines."""

from __future__ import annotations

from .format import fmt_rss_kb
from .state import Snapshot


def status_line(snapshot: Snapshot) -> str:
    loaded = [v for v in snapshot.models if v.status == "loaded"]
    if not loaded:
        return "llm:idle"
    if len(loaded) == 1:
        return f"llm:{loaded[0].name} {fmt_rss_kb(loaded[0].rss_kb)}"
    return f"llm:{len(loaded)}▪ {fmt_rss_kb(snapshot.total_rss_kb)}"
