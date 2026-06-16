"""Compose client + ps + config into a single Snapshot for the UI."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from .aggregator import ModelStats, rollup
from .client import LlamaSwapClient, Model, RunningModel
from .hf import gguf_size_kb, parse_hf_ref
from .ps import attribute_rss_to_models, fetch_ps, parse_ps_output


@dataclass(frozen=True)
class ModelView:
    name: str
    status: str  # "loaded" | "unloaded"
    group: str | None
    rss_kb: int | None
    ttl: int | None
    stats: ModelStats | None
    pinned: bool = False
    disk_size_kb: int | None = None


@dataclass(frozen=True)
class Snapshot:
    models: list[ModelView]

    @property
    def loaded_count(self) -> int:
        return sum(1 for v in self.models if v.status == "loaded")

    @property
    def total_rss_kb(self) -> int:
        return sum(v.rss_kb or 0 for v in self.models)


def unload_eta_seconds(
    ttl: int | None,
    last_seen_iso: str | None,
    now: datetime,
    loaded_since: datetime | None = None,
) -> int | None:
    """Best-guess seconds until llama-swap auto-unloads an idle model.

    llama-swap evicts a model `ttl` seconds after its last activity. We can't see
    that internal timer, so we approximate the last-activity instant as the most
    recent of two signals:
      - the last *logged* request (metrics last_seen), and
      - when llouie first observed the model loaded (`loaded_since`).
    The latter rescues the common case where a model was warmed by a health probe
    (not logged) or the metrics ring rolled — without it the request proxy reads
    stale and the ETA looks bogusly overdue.

    Returns *signed* seconds: a negative result means even our best proxy says the
    model is overdue (so the estimate is unreliable — the caller should treat that
    as unknown rather than "0s, about to unload").
    """
    candidates: list[datetime] = []
    if last_seen_iso:
        try:
            d = datetime.fromisoformat(last_seen_iso)
        except ValueError:
            d = None
        if d is not None and d.tzinfo is not None:
            candidates.append(d)
    if loaded_since is not None:
        candidates.append(loaded_since)
    if ttl is None or not candidates:
        return None
    elapsed = (now - max(candidates)).total_seconds()
    return round(ttl - elapsed)


class LoadObserver:
    """Records when llouie first saw each model loaded, across refreshes.

    This is the floor that makes ETA estimates survive health-probe loads: even
    with no logged request, llouie knows the model has been alive at least since
    it first observed it loaded. Entries drop when a model unloads.
    """

    def __init__(self) -> None:
        self._since: dict[str, datetime] = {}

    def observe(self, loaded_models: set[str], now: datetime) -> None:
        for m in loaded_models:
            self._since.setdefault(m, now)
        for m in list(self._since):
            if m not in loaded_models:
                del self._since[m]

    @property
    def since(self) -> dict[str, datetime]:
        return dict(self._since)


def load_groups(config_path: str | Path) -> dict[str, str]:
    """Parse config.yaml → {model_name: group_name}. Ungrouped models omitted."""
    data = yaml.safe_load(Path(config_path).read_text()) or {}
    groups = data.get("groups") or {}
    out: dict[str, str] = {}
    for group_name, spec in groups.items():
        for member in (spec or {}).get("members", []):
            out[member] = group_name
    return out


def load_pinned(config_path: str | Path) -> set[str]:
    """Members of any `persistent: true` group — these never auto-unload."""
    data = yaml.safe_load(Path(config_path).read_text()) or {}
    groups = data.get("groups") or {}
    pinned: set[str] = set()
    for spec in groups.values():
        if (spec or {}).get("persistent"):
            pinned.update((spec or {}).get("members", []))
    return pinned


def load_hf_refs(config_path: str | Path) -> dict[str, str]:
    """Parse each model's command for its `-hf user/repo:tag` reference."""
    data = yaml.safe_load(Path(config_path).read_text()) or {}
    models = data.get("models") or {}
    out: dict[str, str] = {}
    for model_id, spec in models.items():
        ref = parse_hf_ref((spec or {}).get("cmd", "") or "")
        if ref:
            out[model_id] = ref
    return out


def build_snapshot(
    configured: list[Model],
    running: list[RunningModel],
    rss_by_model: dict[str, int],
    stats_by_model: dict[str, ModelStats],
    groups: dict[str, str],
    pinned: set[str] | None = None,
    disk_sizes: dict[str, int] | None = None,
) -> Snapshot:
    pinned = pinned or set()
    disk_sizes = disk_sizes or {}
    running_by_name = {r.model: r for r in running}
    views: list[ModelView] = []
    for m in configured:
        rm = running_by_name.get(m.id)
        loaded = rm is not None
        views.append(
            ModelView(
                name=m.id,
                status="loaded" if loaded else "unloaded",
                group=groups.get(m.id),
                rss_kb=rss_by_model.get(m.id) if loaded else None,
                ttl=rm.ttl if rm else None,
                stats=stats_by_model.get(m.id),
                pinned=m.id in pinned,
                disk_size_kb=disk_sizes.get(m.id),
            )
        )
    views.sort(key=lambda v: (v.status != "loaded", v.name))
    return Snapshot(models=views)


async def gather_snapshot(client: LlamaSwapClient, config_path: str | Path) -> Snapshot:
    configured, running, metrics, ps_text = await asyncio.gather(
        client.list_models(),
        client.running_models(),
        client.metrics(),
        fetch_ps(),
    )
    rss_by_model = attribute_rss_to_models(parse_ps_output(ps_text), running)
    stats_by_model = rollup(metrics)
    groups = load_groups(config_path)
    pinned = load_pinned(config_path)
    refs = load_hf_refs(config_path)
    disk_sizes = {mid: kb for mid, ref in refs.items() if (kb := gguf_size_kb(ref)) is not None}
    return build_snapshot(
        configured, running, rss_by_model, stats_by_model, groups, pinned, disk_sizes
    )
