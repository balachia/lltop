"""TDD: HF-cache GGUF size resolution."""

from __future__ import annotations

from pathlib import Path

from llouie.hf import parse_hf_ref, resolve_gguf_size_bytes

REF = "unsloth/gemma-4-26B-A4B-it-GGUF:UD-Q5_K_XL"
REPO_DIR = "models--unsloth--gemma-4-26B-A4B-it-GGUF"


def _cache_with(tmp_path: Path, *files: tuple[str, int]) -> Path:
    snap = tmp_path / "hub" / REPO_DIR / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    for name, size in files:
        (snap / name).write_bytes(b"x" * size)
    return tmp_path


# ---- parse_hf_ref ---------------------------------------------------------


def test_parse_hf_ref_from_cmd():
    cmd = "/opt/homebrew/bin/llama-server --port ${PORT} -c 0\n-hf unsloth/foo-GGUF:Q5\n--jinja"
    assert parse_hf_ref(cmd) == "unsloth/foo-GGUF:Q5"


def test_parse_hf_ref_absent():
    assert parse_hf_ref("llama-server --port 5801 -m /local/model.gguf") is None


# ---- resolve_gguf_size_bytes ----------------------------------------------


def test_resolve_size_single_file(tmp_path):
    home = _cache_with(tmp_path, ("gemma-4-26B-A4B-it-UD-Q5_K_XL.gguf", 5000))
    assert resolve_gguf_size_bytes(REF, home) == 5000


def test_resolve_size_sums_shards(tmp_path):
    home = _cache_with(
        tmp_path,
        ("gemma-UD-Q5_K_XL-00001-of-00002.gguf", 4000),
        ("gemma-UD-Q5_K_XL-00002-of-00002.gguf", 3000),
    )
    assert resolve_gguf_size_bytes(REF, home) == 7000


def test_resolve_size_excludes_mmproj(tmp_path):
    home = _cache_with(
        tmp_path,
        ("gemma-UD-Q5_K_XL.gguf", 5000),
        ("mmproj-UD-Q5_K_XL.gguf", 999),  # vision projector, not weights
    )
    assert resolve_gguf_size_bytes(REF, home) == 5000


def test_resolve_size_none_when_not_cached(tmp_path):
    (tmp_path / "hub").mkdir()  # cache exists but repo absent
    assert resolve_gguf_size_bytes(REF, tmp_path) is None


def test_resolve_size_ignores_other_tags(tmp_path):
    home = _cache_with(tmp_path, ("gemma-4-26B-A4B-it-Q8_0.gguf", 9000))  # wrong tag
    assert resolve_gguf_size_bytes(REF, home) is None
