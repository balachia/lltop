"""Resolve a model's on-disk GGUF size from the HF cache.

This is the "nominal size / cost to load" signal: the quantized weight bytes a
model would occupy, available whether or not it's currently loaded. Resolved
from the `-hf user/repo:tag` reference in each model's llama-swap command.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_HF_RE = re.compile(r"-hf\s+(\S+)")

# Successful resolutions are memoized (GGUF sizes don't change); None is never
# cached so a later prepull/download is picked up without a restart.
_SIZE_CACHE: dict[str, int] = {}


def hf_home() -> Path:
    env = os.environ.get("HF_HOME")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "huggingface"


def parse_hf_ref(cmd: str) -> str | None:
    """Extract the `-hf user/repo:tag` reference from a llama-swap command."""
    m = _HF_RE.search(cmd)
    return m.group(1) if m else None


def resolve_gguf_size_bytes(ref: str, home: Path) -> int | None:
    """Total bytes of the GGUF file(s) for `ref` in the HF cache, or None.

    Handles sharded models (sums all matching shards). Returns None when nothing
    matching the tag is cached.
    """
    repo, _, tag = ref.partition(":")
    repo_dir = "models--" + repo.replace("/", "--")
    snapshots = home / "hub" / repo_dir / "snapshots"
    if not snapshots.is_dir():
        return None
    pattern = f"*{tag}*.gguf" if tag else "*.gguf"
    total = 0
    found = False
    for f in snapshots.glob(f"*/{pattern}"):
        if "mmproj" in f.name:
            continue
        # getsize follows symlinks (HF cache snapshots point at blobs)
        total += os.path.getsize(f)
        found = True
    return total if found else None


def gguf_size_kb(ref: str | None, home: Path | None = None) -> int | None:
    """Memoized GGUF size in KB for an `-hf` ref (None if absent/not cached)."""
    if not ref:
        return None
    if ref in _SIZE_CACHE:
        return _SIZE_CACHE[ref]
    b = resolve_gguf_size_bytes(ref, home or hf_home())
    if b is None:
        return None
    kb = b // 1024
    _SIZE_CACHE[ref] = kb
    return kb
