"""Tier 1 dashboard: model inventory + usage rollup."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Footer, Header, Static

from ..client import LlamaSwapClient
from ..format import fmt_rss_kb
from ..logs import stream_log_lines
from ..state import LoadObserver, Snapshot, gather_snapshot
from .logtail import LogTail
from .rows import inventory_rows, usage_rows

SnapshotProvider = Callable[[], Awaitable[Snapshot]]
Unloader = Callable[[str], Awaitable[None]]

DEFAULT_URL = "http://localhost:1135"
DEFAULT_CONFIG = str(Path.home() / ".config" / "llama-swap" / "config.yaml")

# Below this terminal width, stack panels vertically rather than side-by-side.
LAYOUT_BREAKPOINT = 100
LAYOUT_MODES = ("auto", "wide", "narrow")


def resolved_layout(width: int, mode: str, breakpoint: int = LAYOUT_BREAKPOINT) -> str:
    """Resolve effective layout ('wide'|'narrow') from terminal width + mode."""
    if mode in ("wide", "narrow"):
        return mode
    return "wide" if width >= breakpoint else "narrow"


def live_provider(url: str = DEFAULT_URL, config_path: str = DEFAULT_CONFIG) -> SnapshotProvider:
    async def _provide() -> Snapshot:
        async with LlamaSwapClient(url) as client:
            return await gather_snapshot(client, config_path)

    return _provide


def live_unloader(url: str = DEFAULT_URL) -> Unloader:
    async def _unload(model_id: str) -> None:
        async with LlamaSwapClient(url) as client:
            await client.unload(model_id)

    return _unload


def live_loader(url: str = DEFAULT_URL) -> Unloader:
    async def _load(model_id: str) -> None:
        async with LlamaSwapClient(url) as client:
            await client.load(model_id)

    return _load


class DashboardApp(App):
    CSS = """
    #summary { height: 1; padding: 0 1; color: $text-muted; }
    #panels { layout: grid; }
    #panels DataTable { height: 100%; width: 100%; }
    #logtail { border-top: solid $primary; }

    /* wide: inventory | usage on top row, log spanning full width below */
    #panels.wide { grid-size: 2; grid-rows: 1fr 12; }
    #panels.wide #logtail { column-span: 2; }

    /* narrow: three stacked panels */
    #panels.narrow { grid-size: 1; grid-rows: 1fr 1fr 12; }
    """
    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("l", "load", "Load selected"),
        ("u", "unload", "Unload selected"),
        ("f", "toggle_log_filter", "Filter own reqs"),
        ("v", "cycle_layout", "Layout"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        snapshot_provider: SnapshotProvider,
        refresh_interval: float = 2.0,
        url: str = DEFAULT_URL,
        stream_logs: bool = True,
        unloader: Unloader | None = None,
        loader: Unloader | None = None,
        theme: str = "ansi-dark",
        layout: str = "auto",
    ) -> None:
        super().__init__()
        self._theme_name = theme
        self._layout_mode = layout if layout in LAYOUT_MODES else "auto"
        self._provider = snapshot_provider
        self._refresh_interval = refresh_interval
        self._url = url
        self._stream_logs = stream_logs
        self._unloader = unloader
        self._loader = loader
        self._loading: set[str] = set()
        self._last_snapshot: Snapshot | None = None
        self._load_observer = LoadObserver()
        self.summary_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("loading…", id="summary")
        with Container(id="panels"):
            yield DataTable(id="inventory")
            yield DataTable(id="usage")
            yield LogTail(id="logtail")
        yield Footer()

    def _apply_layout(self) -> None:
        panels = self.query_one("#panels")
        effective = resolved_layout(self.size.width, self._layout_mode)
        panels.set_class(effective == "wide", "wide")
        panels.set_class(effective == "narrow", "narrow")

    def on_resize(self, _event: object) -> None:
        self._apply_layout()

    def action_cycle_layout(self) -> None:
        i = LAYOUT_MODES.index(self._layout_mode)
        self._layout_mode = LAYOUT_MODES[(i + 1) % len(LAYOUT_MODES)]
        self._apply_layout()
        self.notify(f"layout: {self._layout_mode}", timeout=2)

    async def on_mount(self) -> None:
        self.theme = self._theme_name
        self.title = "llouie"
        self.sub_title = self._url
        self._apply_layout()
        inv = self.query_one("#inventory", DataTable)
        inv.add_columns("Model", "Status", "Group", "Size", "RAM", "Unload~")
        inv.cursor_type = "row"
        usage = self.query_one("#usage", DataTable)
        usage.add_columns("Model", "Reqs", "In", "Out", "Speed", "Last")
        usage.cursor_type = "row"
        await self.action_refresh()
        if self._refresh_interval > 0:
            self.set_interval(self._refresh_interval, self.action_refresh)
        if self._stream_logs:
            self.run_worker(self._consume_logs(), group="logs", exclusive=True)

    async def _consume_logs(self) -> None:
        tail = self.query_one("#logtail", LogTail)
        try:
            async for line in stream_log_lines(self._url):
                tail.add_raw(line)
        except Exception as exc:  # noqa: BLE001 — stream drop is non-fatal
            tail.add_raw(f"[ERROR] log stream ended: {exc}")

    async def action_refresh(self) -> None:
        try:
            snap = await self._provider()
        except Exception as exc:  # noqa: BLE001 — surface connection errors in-UI
            self._set_summary(f"error: {exc}", error=True)
            return
        self._render(snap)

    def action_toggle_log_filter(self) -> None:
        on = self.query_one("#logtail", LogTail).toggle_filter()
        self.notify(f"own-request filter {'on' if on else 'off'}", timeout=2)

    def _selected_model(self) -> str | None:
        inv = self.query_one("#inventory", DataTable)
        if inv.row_count == 0:
            return None
        return str(inv.get_cell_at((inv.cursor_row, 0)))

    async def action_load(self) -> None:
        model = self._selected_model()
        if model is None or self._loader is None:
            return
        # Optimistically flip the row to "loading" so the status reflects the
        # pending spawn immediately, before the (slow) load worker finishes.
        self._loading.add(model)
        if self._last_snapshot is not None:
            self._render_tables(self._last_snapshot)
        self._set_summary(f"loading {model}…")
        # Cold loads can take minutes — run off the UI thread so it stays live.
        self.run_worker(self._do_load(model), group="load")

    async def _do_load(self, model: str) -> None:
        try:
            await self._loader(model)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash
            self._loading.discard(model)
            if self._last_snapshot is not None:
                self._render_tables(self._last_snapshot)
            self._set_summary(f"load failed: {exc}", error=True)
            return
        self._loading.discard(model)
        await self.action_refresh()

    async def action_unload(self) -> None:
        model = self._selected_model()
        if model is None or self._unloader is None:
            return
        try:
            await self._unloader(model)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash
            self._set_summary(f"unload failed: {exc}", error=True)
            return
        await self.action_refresh()

    def _set_summary(self, text: str, *, error: bool = False) -> None:
        self.summary_text = text
        shown = f"[red]{text}[/]" if error else text
        self.query_one("#summary", Static).update(shown)

    @staticmethod
    def _repopulate(table: DataTable, rows: list[tuple[str, ...]]) -> None:
        """Refill a row-keyed table, keeping the cursor on the same key (col 0)
        even if row order changed. Fixes the cursor jumping to top on refresh."""
        prev_key: str | None = None
        if table.row_count:
            prev_key = str(table.get_cell_at((table.cursor_row, 0)))
        table.clear()
        for row in rows:
            table.add_row(*row)
        if prev_key is not None:
            for i, row in enumerate(rows):
                if row[0] == prev_key:
                    table.move_cursor(row=i)
                    break

    def _render_tables(self, snap: Snapshot) -> None:
        self._last_snapshot = snap
        loaded = {v.name for v in snap.models if v.status == "loaded"}
        self._load_observer.observe(loaded, datetime.now(timezone.utc))
        self._repopulate(
            self.query_one("#inventory", DataTable),
            inventory_rows(
                snap, loading=self._loading, loaded_since=self._load_observer.since
            ),
        )
        self._repopulate(self.query_one("#usage", DataTable), usage_rows(snap))

    def _render(self, snap: Snapshot) -> None:
        self._render_tables(snap)
        self._set_summary(
            f"{snap.loaded_count}/{len(snap.models)} loaded · "
            f"{fmt_rss_kb(snap.total_rss_kb)} RAM"
        )
