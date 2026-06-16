# llouie

A terminal dashboard + tmux statusline for monitoring a local **llama-swap** stack —
think `htop`, but for your swappable LLMs.

llama-swap ships its own web `/ui`, but it won't tell you the two things you actually
want when juggling models on one box: **how much RAM each loaded model is really using**,
and **how expensive each model is to load**. llouie surfaces both.

## What you get

- **Inventory** of every configured model — installed, loaded, or idle — at a glance.
- **RAM per loaded model.** llama-swap doesn't track its children's memory; llouie
  correlates process RSS to each model by matching the `--port` it reports in `/running`.
- **Size / cost-to-load** for *every* model (even unloaded ones), resolved from the GGUF
  files in your Hugging Face cache. Since `RAM − Size ≈ KV + buffers`, you can see what a
  load will actually cost before you pull the trigger.
- **Recent activity / request counts** from the metrics ring.
- A **one-line tmux statusline** so your loaded model + RAM is always in the corner.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- A running llama-swap instance (default `http://localhost:1135`)

## Install

```bash
uv tool install .        # installs the `llouie` command
# or run straight from a clone without installing:
uv run llouie
```

## Usage

```bash
llouie            # interactive TUI dashboard
llouie status     # one-line summary, for a tmux statusline
```

Options (both subcommands):

| Flag | Default | Meaning |
|------|---------|---------|
| `--url` | `http://localhost:1135` | llama-swap base URL |
| `--config` | `~/.config/llama-swap/config.yaml` | llama-swap config path |
| `--theme` | `ansi-dark` | Textual theme name |
| `--layout` | `auto` | `auto` \| `wide` \| `narrow` |

### TUI keys

| Key | Action |
|-----|--------|
| `r` | refresh |
| `l` | load the selected model |
| `u` | unload the selected model |
| `f` | toggle the own-requests log filter |
| `v` | cycle layout (auto / wide / narrow) |
| `q` | quit |

Inventory columns: **Model · Status · Group · Size · RAM · Unload~** (Unload~ shows the
remaining vs configured idle-TTL, `pinned`, or `?` when the idle clock is uncertain).

### tmux statusline

`llouie status` prints one of:

```
llm:idle                  # nothing loaded
llm:qw3-coder 14.2G       # a single model loaded, with its RAM
llm:3▪ 41.8G              # several loaded, with total RAM
```

It fails closed — on any error it prints `llm:-` rather than erroring out your bar. Wire
it into tmux, e.g.:

```tmux
set -g status-right '#(llouie status)'
```

## Development

```bash
uv sync                  # install deps incl. dev extras
uv run pytest            # unit + smoke tests
uv run pytest -m live    # opt-in integration tests (hit a real llama-swap on :1135)
uv run ruff check        # lint
```

Architecture is split for testability: a pure, fully unit-tested **data layer**
(`client`, `ps`, `aggregator`, `state`, `hf`, `format`, `logs`, `statusline`) and a thin,
smoke-tested **Textual shell** (`tui/`). Keep logic in the data layer.
