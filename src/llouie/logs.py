"""llama-swap log streaming: parse level-prefixed lines, tail a bounded buffer.

`/logs/stream` is a long-lived text/plain line stream (not SSE framing).
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from .client import USER_AGENT

_LEVEL_RE = re.compile(r"^\[(\w+)\]\s*(.*)$", re.DOTALL)

_LEVEL_COLORS = {
    "ERROR": "red",
    "WARN": "yellow",
    "WARNING": "yellow",
    "INFO": "blue",
    "DEBUG": "dim",
}


@dataclass(frozen=True)
class LogLine:
    level: str | None
    message: str
    raw: str


def parse_log_line(raw: str) -> LogLine:
    m = _LEVEL_RE.match(raw)
    if m:
        return LogLine(level=m.group(1).upper(), message=m.group(2), raw=raw)
    return LogLine(level=None, message=raw, raw=raw)


def level_color(level: str | None) -> str:
    if level is None:
        return "dim"
    return _LEVEL_COLORS.get(level.upper(), "white")


class LogBuffer:
    def __init__(self, maxlen: int = 500) -> None:
        self._lines: deque[LogLine] = deque(maxlen=maxlen)

    def append(self, raw: str) -> None:
        if not raw.strip():
            return
        self._lines.append(parse_log_line(raw))

    @property
    def lines(self) -> list[LogLine]:
        return list(self._lines)


async def stream_log_lines(
    url: str, *, timeout: float | None = None
) -> AsyncIterator[str]:
    """Yield log lines from /logs/stream as they arrive. Runs until cancelled."""
    async with httpx.AsyncClient(
        timeout=timeout, headers={"User-Agent": USER_AGENT}
    ) as client:
        async with client.stream("GET", f"{url.rstrip('/')}/logs/stream") as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                yield line
