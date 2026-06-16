"""TDD: log line parsing + bounded tail buffer."""

from __future__ import annotations

from pathlib import Path

from llouie.logs import LogBuffer, LogLine, level_color, parse_log_line

FIXTURES = Path(__file__).parent / "fixtures"


# ---- parse_log_line -------------------------------------------------------


def test_parse_info_line():
    ll = parse_log_line('[INFO] Request 127.0.0.1 "GET /v1/models" 200')
    assert isinstance(ll, LogLine)
    assert ll.level == "INFO"
    assert ll.message.startswith("Request")


def test_parse_error_line():
    ll = parse_log_line("[ERROR] upstream returned 500 for gemma4-31b")
    assert ll.level == "ERROR"
    assert ll.message == "upstream returned 500 for gemma4-31b"


def test_parse_unbracketed_upstream_line():
    """Raw llama-server output has no [LEVEL] prefix."""
    ll = parse_log_line("llama_model_loader: loaded meta data with 30 kv pairs")
    assert ll.level is None
    assert ll.message == "llama_model_loader: loaded meta data with 30 kv pairs"


def test_parse_preserves_raw():
    raw = "[WARN]   spaced  message"
    ll = parse_log_line(raw)
    assert ll.raw == raw


def test_parse_all_fixture_lines():
    lines = [
        parse_log_line(line)
        for line in (FIXTURES / "logs_sample.txt").read_text().splitlines()
    ]
    levels = [ll.level for ll in lines]
    assert "INFO" in levels
    assert "WARN" in levels
    assert "ERROR" in levels
    assert "DEBUG" in levels
    assert None in levels  # the unbracketed upstream line


# ---- level_color ----------------------------------------------------------


def test_level_color_mapping():
    assert level_color("ERROR") == "red"
    assert level_color("WARN") == "yellow"
    assert level_color(None) == "dim"


# ---- LogBuffer ------------------------------------------------------------


def test_logbuffer_appends_and_parses():
    buf = LogBuffer(maxlen=10)
    buf.append("[INFO] hello")
    assert len(buf.lines) == 1
    assert buf.lines[0].level == "INFO"


def test_logbuffer_respects_maxlen():
    buf = LogBuffer(maxlen=3)
    for i in range(5):
        buf.append(f"[INFO] line {i}")
    assert len(buf.lines) == 3
    # oldest dropped; newest retained
    assert buf.lines[-1].message == "line 4"
    assert buf.lines[0].message == "line 2"


def test_logbuffer_skips_blank_lines():
    buf = LogBuffer(maxlen=10)
    buf.append("")
    buf.append("   ")
    buf.append("[INFO] real")
    assert len(buf.lines) == 1
