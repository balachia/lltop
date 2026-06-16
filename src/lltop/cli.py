"""lltop entry point: TUI dashboard + statusline output."""

from __future__ import annotations

import argparse
import asyncio
import sys

from .client import LlamaSwapClient
from .state import gather_snapshot
from .statusline import status_line
from .tui.app import (
    DEFAULT_CONFIG,
    DEFAULT_URL,
    DashboardApp,
    live_loader,
    live_provider,
    live_unloader,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lltop", description="llama-swap TUI + status")
    p.add_argument("--url", default=DEFAULT_URL, help="llama-swap base URL")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="llama-swap config.yaml path")
    p.add_argument("--theme", default="ansi-dark", help="Textual theme name")
    p.add_argument(
        "--layout",
        default="auto",
        choices=["auto", "wide", "narrow"],
        help="panel layout (auto picks by terminal width)",
    )
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("tui", help="interactive dashboard (default)")
    sub.add_parser("status", help="one-line summary for tmux")
    return p


async def _run_status(url: str, config: str) -> int:
    try:
        async with LlamaSwapClient(url) as client:
            snap = await gather_snapshot(client, config)
    except Exception:  # noqa: BLE001 — statusline must never error the bar
        print("llm:-")
        return 0
    print(status_line(snap))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "status":
        return asyncio.run(_run_status(args.url, args.config))
    # default: TUI
    app = DashboardApp(
        live_provider(args.url, args.config),
        url=args.url,
        unloader=live_unloader(args.url),
        loader=live_loader(args.url),
        theme=args.theme,
        layout=args.layout,
    )
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
