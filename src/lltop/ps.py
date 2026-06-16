"""Process enumeration: find llama-server children, attribute RSS to models.

macOS-first. Linux likely works (same ps flags) but untested; /proc/$pid/status
would be the canonical Linux path.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass

from .client import RunningModel


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    rss_kb: int
    command: str


def parse_ps_output(text: str) -> list[Proc]:
    procs: list[Proc] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=3)
        if len(parts) < 4:
            continue
        try:
            pid, ppid, rss = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        procs.append(Proc(pid=pid, ppid=ppid, rss_kb=rss, command=parts[3]))
    return procs


def _is_llama_server(p: Proc) -> bool:
    exe = p.command.split(maxsplit=1)[0] if p.command else ""
    return os.path.basename(exe) == "llama-server"


def find_llama_server_procs(procs: list[Proc]) -> list[Proc]:
    return [p for p in procs if _is_llama_server(p)]


_PORT_RE = re.compile(r"--port[=\s]+(\d+)")


def extract_port(cmdline: str) -> int | None:
    m = _PORT_RE.search(cmdline)
    return int(m.group(1)) if m else None


def attribute_rss_to_models(
    procs: list[Proc], running: list[RunningModel]
) -> dict[str, int]:
    """Map model_name → RSS in KB by joining ps procs against /running ports."""
    port_to_model = {r.port: r.model for r in running}
    out: dict[str, int] = {}
    for p in find_llama_server_procs(procs):
        port = extract_port(p.command)
        if port is None:
            continue
        model = port_to_model.get(port)
        if model is None:
            continue
        out[model] = p.rss_kb
    return out


async def fetch_ps() -> str:
    proc = await asyncio.create_subprocess_exec(
        "ps",
        "-ax",
        "-o",
        "pid,ppid,rss,command",
        stdout=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    return out.decode()
