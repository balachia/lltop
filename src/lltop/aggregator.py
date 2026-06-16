"""Aggregate the /api/metrics ring buffer into per-model rollups."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .client import ActivityLogEntry


@dataclass(frozen=True)
class ModelStats:
    model: str
    req_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_tokens: int
    avg_tokens_per_second: float
    avg_duration_ms: float
    success_rate: float
    last_seen: str


def _stats_for(model: str, entries: list[ActivityLogEntry]) -> ModelStats:
    n = len(entries)
    decode_speeds = [e.tokens_per_second for e in entries if e.output_tokens > 0]
    avg_tps = sum(decode_speeds) / len(decode_speeds) if decode_speeds else 0.0
    avg_dur = sum(e.duration_ms for e in entries) / n
    successes = sum(1 for e in entries if 200 <= e.status_code < 300)
    return ModelStats(
        model=model,
        req_count=n,
        total_input_tokens=sum(e.input_tokens for e in entries),
        total_output_tokens=sum(e.output_tokens for e in entries),
        total_cache_tokens=sum(e.cache_tokens for e in entries),
        avg_tokens_per_second=avg_tps,
        avg_duration_ms=avg_dur,
        success_rate=successes / n,
        last_seen=max(e.timestamp for e in entries),
    )


def rollup(entries: list[ActivityLogEntry]) -> dict[str, ModelStats]:
    by_model: dict[str, list[ActivityLogEntry]] = defaultdict(list)
    for e in entries:
        by_model[e.model].append(e)
    return {model: _stats_for(model, es) for model, es in by_model.items()}
