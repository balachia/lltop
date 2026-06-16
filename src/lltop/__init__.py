import os

# Textual asks the terminal for the kitty keyboard protocol, which re-encodes
# keystrokes and breaks tmux's prefix detection (Ctrl-a/Ctrl-b stop working, so
# you can't split panes etc.). lltop only binds plain keys, so under tmux we opt
# out. Must run before textual is imported, hence here in the package __init__.
# setdefault leaves an explicit user override (TEXTUAL_DISABLE_KITTY_KEY) intact.
if os.environ.get("TMUX"):
    os.environ.setdefault("TEXTUAL_DISABLE_KITTY_KEY", "1")

__version__ = "0.0.1"
