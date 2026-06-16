# CLAUDE.md

Guidance for Claude Code working in this repo.

## What this is

`lltop` — a TUI dashboard + statusline for monitoring the local **llama-swap** stack
(the `monst3r` llama-swap host, default `http://localhost:1135`). Python 3.12, managed
with `uv`. The built-in llama-swap `/ui` is "good not great"; lltop exists for
at-a-glance: installed models, what's loaded, RAM per model, request counts, plus a
one-line tmux statusline.

## Commands

```bash
uv run lltop                 # TUI dashboard (default subcommand)
uv run lltop status          # one-line tmux summary; never errors the bar
uv run pytest                 # unit + smoke tests (live tests excluded by default)
uv run pytest -m live         # opt-in: hits a real llama-swap on :1135
uv run ruff check             # lint (line-length 100, py312 target)
```

Global flags: `--url` (default `http://localhost:1135`), `--config`
(default `~/.config/llama-swap/config.yaml`), `--theme` (default `ansi-dark`),
`--layout {auto,wide,narrow}`.

TUI keys: `r` refresh · `l`/`u` load/unload selected · `f` toggle own-request log
filter · `v` cycle layout · `q` quit.

`lltop status` output: `llm:idle` / `llm:<model> <ram>` (one loaded) /
`llm:N▪ <total_ram>` (several loaded).

## Architecture

Two layers, deliberately split for testability:

- **Pure data layer** (fully unit-tested): `client` (llama-swap HTTP) · `ps`
  (process RSS) · `aggregator` · `state` (snapshot assembly) · `hf` (GGUF/HF-cache
  resolver) · `format` · `logs` · `statusline`.
- **Thin Textual shell** (smoke-tested via `run_test`): `tui/app` · `tui/rows` ·
  `tui/logtail`. Keep logic out of here — push it down into the data layer.

Entry point: `lltop = lltop.cli:main` (subparser → `tui` default / `status`).

## Non-obvious design rationale (don't re-derive this)

The genuine value over llama-swap's built-in UI lives in two correlations the server
doesn't expose:

- **RAM-per-model.** llama-swap does not track child RSS. lltop maps `ps` RSS →
  model by matching the `--port` reported in `/running`. This is the core trick —
  preserve it if you refactor `ps`/`aggregator`.
- **Size / cost-to-load column.** GGUF bytes resolved from the HF cache (`hf.py`),
  shown even for *unloaded* models, so `RAM − Size ≈ KV + buffers in RAM`.
- **Statusline fails closed.** `lltop status` catches everything and prints `llm:-`
  on any error — it must never error out a tmux bar. Keep that contract.
- **Kitty-protocol opt-out under tmux.** `__init__.py` sets
  `TEXTUAL_DISABLE_KITTY_KEY=1` when `$TMUX` is set, *before* Textual imports.
  Textual otherwise requests the kitty keyboard protocol, which re-encodes keys and
  steals tmux's prefix (you can't split panes). lltop only binds plain keys, so it
  loses nothing. Don't remove this — and it must stay in `__init__` to beat the import.

## Testing

- TDD-built. Data layer is fully unit-tested; TUI is smoke-tested.
- `live` marker = integration tests that hit a real llama-swap on `:1135`. Excluded by
  default (`addopts = -m 'not live'`); run with `uv run pytest -m live`.
- Use `respx` for HTTP mocking in client tests.

## Task tracking (chainlink)

- Tracker location: project-local `.chainlink/` in this repo (data-only — no Claude
  Code hooks wired, nothing gates tool calls).
- Run all chainlink commands from this repo root.
- Backlog: `chainlink issue ready` / `chainlink issue next`. See the `use-chainlink`
  skill for syntax.

## Related

Depends on verified llama-swap API behavior; the homelab record for the llama-swap host
is the `llama-swap-monst3r` memory.
