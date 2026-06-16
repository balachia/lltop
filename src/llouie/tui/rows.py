"""Pure row builders: Snapshot → display tuples for the dashboard tables."""

from __future__ import annotations

from datetime import datetime, timezone

from ..format import fmt_count, fmt_rss_kb, fmt_tps, fmt_ttl
from ..state import Snapshot, unload_eta_seconds

InventoryRow = tuple[str, str, str, str, str, str]
UsageRow = tuple[str, str, str, str, str, str]


def _clock(iso_ts: str) -> str:
    try:
        return datetime.fromisoformat(iso_ts).strftime("%H:%M:%S")
    except ValueError:
        return iso_ts


def inventory_rows(
    snapshot: Snapshot,
    now: datetime | None = None,
    loading: set[str] | None = None,
    loaded_since: dict[str, datetime] | None = None,
) -> list[InventoryRow]:
    if now is None:
        now = datetime.now(timezone.utc)
    loading = loading or set()
    loaded_since = loaded_since or {}
    rows: list[InventoryRow] = []
    for v in snapshot.models:
        if v.status == "loaded":
            status = "● loaded"
            if v.pinned:
                # persistent group member — never auto-unloads, so no countdown
                unload_eta = "pinned"
            else:
                last_seen = v.stats.last_seen if v.stats else None
                eta = unload_eta_seconds(
                    v.ttl, last_seen, now, loaded_since=loaded_since.get(v.name)
                )
                # None (no signal) or <=0 (proxy says overdue but still loaded →
                # estimate is stale) both render as unknown, not a misleading "0s".
                remaining = fmt_ttl(eta) if eta is not None and eta > 0 else "?"
                # remaining/configured so the ttl window is legible at a glance
                unload_eta = f"{remaining}/{fmt_ttl(v.ttl)}"
        elif v.name in loading:
            status = "⟳ loading"
            unload_eta = "…"
        else:
            status = "idle"
            unload_eta = "-"
        rows.append(
            (
                v.name,
                status,
                v.group or "-",
                fmt_rss_kb(v.disk_size_kb),  # nominal on-disk weight size
                fmt_rss_kb(v.rss_kb),  # actual RSS when loaded
                unload_eta,
            )
        )
    return rows


def usage_rows(snapshot: Snapshot) -> list[UsageRow]:
    with_stats = [v for v in snapshot.models if v.stats is not None]
    with_stats.sort(key=lambda v: v.stats.req_count, reverse=True)
    rows: list[UsageRow] = []
    for v in with_stats:
        s = v.stats
        rows.append(
            (
                v.name,
                fmt_count(s.req_count),
                fmt_count(s.total_input_tokens),
                fmt_count(s.total_output_tokens),
                fmt_tps(s.avg_tokens_per_second),
                _clock(s.last_seen),
            )
        )
    return rows
