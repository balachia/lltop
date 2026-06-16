"""TDD: process enumeration + RSS attribution."""

from __future__ import annotations

from llouie.client import RunningModel
from llouie.ps import (
    Proc,
    attribute_rss_to_models,
    extract_port,
    find_llama_server_procs,
    parse_ps_output,
)


# ---- parse_ps_output ------------------------------------------------------


def test_parse_ps_idle_returns_only_llama_swap(fx_ps_idle):
    procs = parse_ps_output(fx_ps_idle)
    assert len(procs) == 1
    p = procs[0]
    assert p.pid == 1767
    assert p.ppid == 1
    assert "llama-swap" in p.command
    assert p.rss_kb == 534112


def test_parse_ps_one_loaded_returns_both(fx_ps_one_loaded):
    procs = parse_ps_output(fx_ps_one_loaded)
    assert len(procs) == 2
    swap = next(p for p in procs if "llama-swap" in p.command)
    server = next(p for p in procs if "llama-server" in p.command)
    assert server.ppid == swap.pid
    assert server.rss_kb == 9834592


def test_parse_ps_handles_blank_lines():
    text = "\n  1767     1 534112 /usr/bin/llama-swap -config foo\n\n\n"
    procs = parse_ps_output(text)
    assert len(procs) == 1
    assert procs[0].command.endswith("foo")


def test_parse_ps_command_preserves_internal_spaces():
    text = "  100   1 1024 /bin/llama-server --port 5802 -c 0 --jinja"
    procs = parse_ps_output(text)
    assert procs[0].command == "/bin/llama-server --port 5802 -c 0 --jinja"


# ---- find_llama_server_procs ---------------------------------------------


def test_find_llama_server_procs_idle(fx_ps_idle):
    procs = parse_ps_output(fx_ps_idle)
    assert find_llama_server_procs(procs) == []


def test_find_llama_server_procs_one_loaded(fx_ps_one_loaded):
    procs = parse_ps_output(fx_ps_one_loaded)
    servers = find_llama_server_procs(procs)
    assert len(servers) == 1
    assert servers[0].pid == 87353


def test_find_llama_server_procs_ignores_swap():
    """Sanity check: the llama-swap parent shouldn't be mistaken for a server."""
    procs = [Proc(pid=1, ppid=0, rss_kb=100, command="/bin/llama-swap -config foo")]
    assert find_llama_server_procs(procs) == []


# ---- extract_port ---------------------------------------------------------


def test_extract_port_from_cmdline():
    cmd = "/opt/homebrew/bin/llama-server --port 5802 -c 0 -hf ... --jinja"
    assert extract_port(cmd) == 5802


def test_extract_port_returns_none_when_absent():
    assert extract_port("/usr/bin/llama-server -c 0 -hf foo") is None


def test_extract_port_handles_equals_form():
    """Some CLIs accept --port=5802."""
    assert extract_port("/bin/llama-server --port=5802 -c 0") == 5802


# ---- attribute_rss_to_models ----------------------------------------------


def test_attribute_rss_one_loaded(fx_ps_one_loaded, fx_running_one_loaded):
    procs = parse_ps_output(fx_ps_one_loaded)
    running = [RunningModel.from_json(d) for d in fx_running_one_loaded["running"]]
    rss_by_model = attribute_rss_to_models(procs, running)
    assert rss_by_model == {"gemma4-e4b": 9834592}


def test_attribute_rss_idle_returns_empty(fx_ps_idle, fx_running_idle):
    procs = parse_ps_output(fx_ps_idle)
    running = [RunningModel.from_json(d) for d in fx_running_idle["running"]]
    assert attribute_rss_to_models(procs, running) == {}


def test_attribute_rss_unmatched_port_skipped():
    """If a server process's port doesn't match any /running entry, skip it."""
    procs = [
        Proc(pid=1, ppid=0, rss_kb=100, command="/bin/llama-swap"),
        Proc(pid=2, ppid=1, rss_kb=500, command="/bin/llama-server --port 9999"),
    ]
    running: list[RunningModel] = []
    assert attribute_rss_to_models(procs, running) == {}
