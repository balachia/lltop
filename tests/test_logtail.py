"""Smoke tests: LogTail widget parses + buffers streamed lines."""

from __future__ import annotations

from llouie.tui.logtail import LogTail
from textual.app import App, ComposeResult


class _Host(App):
    def __init__(self, **kwargs: object) -> None:
        super().__init__()
        self._tail_kwargs = kwargs

    def compose(self) -> ComposeResult:
        yield LogTail(id="tail", **self._tail_kwargs)


async def test_logtail_mounts():
    app = _Host()
    async with app.run_test():
        assert app.query_one("#tail", LogTail) is not None


async def test_logtail_buffers_added_lines():
    app = _Host()
    async with app.run_test():
        tail = app.query_one("#tail", LogTail)
        tail.add_raw("[INFO] hello")
        tail.add_raw("[ERROR] boom")
        assert len(tail.buffer.lines) == 2
        assert tail.buffer.lines[0].level == "INFO"
        assert tail.buffer.lines[1].level == "ERROR"


async def test_logtail_skips_blank():
    app = _Host()
    async with app.run_test():
        tail = app.query_one("#tail", LogTail)
        tail.add_raw("")
        tail.add_raw("[INFO] real")
        assert len(tail.buffer.lines) == 1


async def test_logtail_respects_maxlen():
    app = _Host(maxlen=2)
    async with app.run_test():
        tail = app.query_one("#tail", LogTail)
        for i in range(5):
            tail.add_raw(f"[INFO] line {i}")
        assert len(tail.buffer.lines) == 2
        assert tail.buffer.lines[-1].message == "line 4"


async def test_logtail_filter_hides_own_requests_but_keeps_buffer():
    app = _Host(own_marker="llouie")
    async with app.run_test():
        tail = app.query_one("#tail", LogTail)
        tail.toggle_filter()  # turn filtering on
        assert tail.filter_own is True
        tail.add_raw('[INFO] Request 127.0.0.1 "GET /running" 200 "llouie" 5us')
        tail.add_raw('[INFO] Request 10.0.0.9 "POST /v1/chat" 200 "curl/8" 5us')
        # both buffered (history preserved), but the own request isn't "visible"
        assert len(tail.buffer.lines) == 2
        visible = [ll for ll in tail.buffer.lines if tail._visible(ll.raw)]
        assert len(visible) == 1
        assert "curl" in visible[0].raw


async def test_logtail_toggle_is_retroactive():
    app = _Host(own_marker="llouie")
    async with app.run_test():
        tail = app.query_one("#tail", LogTail)
        tail.add_raw('[INFO] "GET /running" "llouie"')
        tail.add_raw('[INFO] "POST /v1/chat" "curl/8"')
        # filtering off → both visible
        assert sum(tail._visible(ll.raw) for ll in tail.buffer.lines) == 2
        tail.toggle_filter()  # on → own hidden
        assert sum(tail._visible(ll.raw) for ll in tail.buffer.lines) == 1
        tail.toggle_filter()  # off again → both back
        assert sum(tail._visible(ll.raw) for ll in tail.buffer.lines) == 2
