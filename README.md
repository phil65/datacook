# DataCook

DataCook is a desktop tool for exploring and transforming tables. Every operation you apply is
recorded as a step in a tree, so an analysis can be branched, replayed, saved as a project or
exported as a Python script (and the script can be edited and read back).

> **Status: being rebuilt** (phase 3 of the plan done: the new app). The new Qt app runs on
> a Qt-free engine (`datacook.engine`): a tree of typed operation records, frames computed
> on demand under a memory budget (pandas 3 with pyarrow dtypes), code generated from the
> records and parsed back. The op catalogue is a starter set (24 ops, basic readers and
> writers); porting the rest of the old catalogue in [`legacy/`](legacy/README.md) is next.

## Installation

### Option 1: Standalone executable (no Python required)

Download the binary for your platform from the
[latest GitHub Release](https://github.com/phil65/datacook/releases/latest):

| Platform | File |
|---|---|
| Windows (x86_64) | `datacook-windows-x86_64.exe` |
| macOS (Apple Silicon) | `datacook-macos-arm64` |
| Linux (x86_64) | `datacook-linux-x86_64` |

On first launch, the executable automatically sets up an isolated Python 3.14 environment
with all dependencies (including Excel support) using `uv`. Built-in management commands:

```bash
datacook self update   # update to the latest PyPI release
datacook self remove   # remove the managed runtime environment
```

*(macOS / Linux: make the downloaded file executable with `chmod +x datacook-*`. Because
binaries are not yet code-signed, Windows SmartScreen or macOS Gatekeeper may ask for
confirmation on first run.)*

### Option 2: With `uv` or `pip` (Python ≥ 3.14)

```bash
# Install as an isolated desktop tool (recommended)
uv tool install "datacook-app[excel]"
datacook

# Or run directly without installing
uvx --from "datacook-app[excel]" datacook

# Or with pip
pip install "datacook-app[excel]"
datacook
```

## The app

```bash
datacook                              # start with an empty project
datacook project.datacook             # open a project
datacook data.csv                     # open a data file (reader dialog)
uv run python tools/demo_data.py demo # sample data + a demo project in ./demo
```

**Concept.** A project is a tree of *steps*. A root step reads a file; every other step is one
operation (filter, rename, group, merge, ...) applied to its parent(s). Adding a step to a step
that already has children creates a *branch*; a merge takes a second table as its other input.
The steps are stored as typed records (operation + parameters), not as data: tables are
computed when you look at them and kept in a cache under a memory budget, so a long tree of a
large table does not cost a copy per step. The **code** of every step is generated from its
record; the whole tree (or the path to one step) exports as a plain pandas script.

**Docks** (all follow the selected step; View menu to show / hide them):

| Dock | What |
|---|---|
| Steps (left) | the tree: name, shape, size; badges for in memory / in use / computing / error. Right-click: rename, comment, branch, delete |
| Data (center) | the table of the selected step, or the preview of the step being edited. Header click = display-only sort (a row order, no copy); "Add as sort step" turns it into a real step |
| Parameters (right) | form of the step being added or edited, with a **live preview** of the first rows; Apply commits, Cancel / Esc discards |
| Columns (right, tab) | columns of the shown table (type, missing values, size) and statistics of the selected column |
| Code (bottom) | the generated script; the selected step's lines are highlighted |
| Messages (bottom, tab) | errors of failing steps (click: go to the step), loads, exports, log |
| Status bar | memory: frame cache / budget and process RSS; click for the cached steps and "Free memory" |

**Memory model.** Only the selected step and its inputs are *pinned* (kept in memory while
shown); every other computed table stays in the LRU cache until the budget (25 % of RAM by
default) needs the room or you free it. Views never copy a table: the data view reads windows
of the cached frame, previews hold only their first rows, the column statistics are computed
on a worker. Undo / redo recompute what they need.

**Keyboard shortcuts.**

| Keys | Action |
|---|---|
| Ctrl+Shift+P | command palette: every operation by name |
| Ctrl+E | edit the selected step (parameters + preview) |
| Esc | cancel the preview |
| F2 / Del (in the tree) | rename / delete the selected step (with its subtree) |
| Ctrl+Z / Ctrl+Shift+Z | undo / redo |
| Ctrl+N / Ctrl+O / Ctrl+S / Ctrl+Shift+S | new / open / save / save as project |
| Ctrl+Shift+O | open a data file |

The UI is available in English and German (View > Language, switches at runtime).

## Engine example

```python
from datacook.engine import Session
from datacook.engine.ops import missing, rows, sources

with Session() as session:
    data = {"a": [3, None, 1], "b": [4, 5, 6]}
    src = session.add(sources.InlineData.record(data=data), name="raw")
    filled = session.add(missing.FillForward.record(), [src])
    branch = session.add(rows.SortRows.record(by=["a"]), [filled])
    other = session.add(rows.Head.record(n=2), [filled])  # a second branch

    print(session.materialize(branch.id))  # computed on demand, cached
    print(session.code())  # the script for the whole tree
    session.update(filled.id, params=missing.FillForward.Params(limit=1))
    # -> `filled`, `branch` and `other` are invalidated and recomputed on request
```

`session.import_script(text)` parses a script back into nodes (statements it does not
recognise become "custom code" steps); `datacook.engine.project` saves and loads the tree as
JSON, and `datacook.engine.formats.FormatRegistry` maps file extensions to readers and
writers.

## Development

```bash
git clone https://github.com/phil65/datacook
cd datacook
uv sync --all-extras    # Python 3.14
uv run pytest
uv run ruff check . && uv run ty check
```

`uv run pytest` runs the app tests offscreen (`QT_QPA_PLATFORM=offscreen`), including a smoke
test of the whole window (`tests/app/test_smoke.py`). See [AGENTS.md](AGENTS.md) for the
layout and the rebuild status, [`src/datacook/app/README.md`](src/datacook/app/README.md) for
the app's internals. [`docs/feature-inventory.md`](docs/feature-inventory.md) lists every
feature of the old app (git tag `pre-rework`) and where it went in the rework.
