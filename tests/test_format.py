"""TDD: human-readable formatting helpers (shared by TUI + statusline)."""

from __future__ import annotations

from lltop.format import fmt_count, fmt_rss_kb, fmt_tps, fmt_ttl


def test_fmt_rss_kb_gigabytes():
    assert fmt_rss_kb(9_834_592) == "9.4G"


def test_fmt_rss_kb_megabytes():
    assert fmt_rss_kb(534_112) == "522M"


def test_fmt_rss_kb_none():
    assert fmt_rss_kb(None) == "-"


def test_fmt_rss_kb_zero():
    assert fmt_rss_kb(0) == "-"


def test_fmt_count_small():
    assert fmt_count(523) == "523"


def test_fmt_count_thousands():
    assert fmt_count(1234) == "1.2k"


def test_fmt_count_millions():
    assert fmt_count(2_500_000) == "2.5M"


def test_fmt_count_zero():
    assert fmt_count(0) == "0"


def test_fmt_tps():
    assert fmt_tps(91.305) == "91 t/s"


def test_fmt_tps_zero_is_dash():
    assert fmt_tps(0.0) == "-"


def test_fmt_ttl_minutes_seconds():
    assert fmt_ttl(600) == "10m0s"


def test_fmt_ttl_under_minute():
    assert fmt_ttl(45) == "45s"


def test_fmt_ttl_none():
    assert fmt_ttl(None) == "-"
