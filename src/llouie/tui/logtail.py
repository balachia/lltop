"""Log tail widget: streams /logs/stream lines into a scrollback, color-coded."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import RichLog

from ..client import USER_AGENT
from ..logs import LogBuffer, LogLine, level_color, parse_log_line


class LogTail(RichLog):
    """A RichLog that parses + color-codes llama-swap log lines.

    Keeps a parallel LogBuffer (all lines, including filtered ones) so the
    'filter own requests' toggle can retroactively show/hide llouie's own
    polling traffic without losing history.
    """

    def __init__(self, maxlen: int = 500, own_marker: str = USER_AGENT, **kwargs: object) -> None:
        super().__init__(highlight=False, markup=False, wrap=False, **kwargs)
        self.buffer = LogBuffer(maxlen=maxlen)
        self.filter_own = False
        self._own_marker = own_marker

    def _is_own(self, raw: str) -> bool:
        return self._own_marker in raw

    def _visible(self, raw: str) -> bool:
        return not (self.filter_own and self._is_own(raw))

    def _emit(self, line: LogLine) -> None:
        self.write(Text(line.message, style=level_color(line.level)))

    def add_raw(self, raw: str) -> None:
        if not raw.strip():
            return
        self.buffer.append(raw)
        if self._visible(raw):
            self._emit(parse_log_line(raw))

    def toggle_filter(self) -> bool:
        """Flip own-request filtering and rebuild the view from the buffer."""
        self.filter_own = not self.filter_own
        self.clear()
        for line in self.buffer.lines:
            if self._visible(line.raw):
                self._emit(line)
        return self.filter_own
