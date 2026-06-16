"""Human-readable formatting helpers."""

from __future__ import annotations

_KB = 1024
_MB = 1024 * 1024


def fmt_rss_kb(kb: int | None) -> str:
    if not kb:
        return "-"
    if kb >= _MB:
        return f"{kb / _MB:.1f}G"
    return f"{round(kb / _KB)}M"


def fmt_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_tps(tps: float) -> str:
    if tps <= 0:
        return "-"
    return f"{round(tps)} t/s"


def fmt_ttl(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m{seconds % 60}s"
