# AGENTS.md

## Overview

DataCook (package `datacook`, PyPI name `DataCook`) is a desktop tool for interactive data
analysis on tables. Every transformation is recorded as code in a history tree, so a session
can be replayed, branched or exported as a Python script.

**Current state: being rebuilt.** The plan (owner's OSS workspace, `DATACOOK_PLAN.md`) moves to
a Qt-free engine (tree of typed op records, code generated from them, frames materialized on
demand) with a new Qt app on top (prettyqt + cutepandas). Phase status:

| Phase | What | Status |
|---|---|---|
| 0 | Cut licensing / packaging / dead deps, move GUI + plugins to `legacy/`, rename `processanalyzer` -> `datacook`, copier-phil65 template | done |
| 1 | Downstream: generic Qt -> prettyqt, dataframe-in-Qt -> cutepandas | open |
| 2 | Engine (`datacook.engine`, Qt-free), format registry for readers / writers | done (starter op set) |
| 3 | App with all main docks (design: `DATACOOK_APP_DESIGN.md`) | done (WPs A-F, 2026-11-25); checkpoint 1 demo |
| 4 | Op catalogue port (on pandas 3) | WP4.1-4.7 done (general, missing values, text, date / time, categorical, reshape + combine, statistics); WP4.8 estimators open |
| 5-7 | Plugins, AI, docs + release | open |

`datacook [project.datacook | data file]` (GUI script, or `python -m datacook.app`) starts the
app; `tools/demo_data.py <dir>` writes sample data and a demo project. The old op catalogue
(`methods/`) and plugins are in `legacy/` (to port in phases 4 / 5).

**Feature inventory: `docs/feature-inventory.md`.** Every feature of the old app (tag
`pre-rework` = `978c73cc`, package `processanalyzer`) with its status (ported / planned /
backlog / dropped / open). **Before deleting anything from `legacy/` or porting a phase,
check and update it**: mark rows ported (with the new location), and never remove an old
feature without a row saying where it went or which owner decision dropped it. Old code
(also the GUI deleted in `aa8e9207`): `git show pre-rework:processanalyzer/<path>` (old history: private archive repo, not in this one).

## Layout

- `src/datacook/engine/` (Qt-free; `tests/test_import.py` checks that in a subprocess):
  - `ops/base.py`: `Op` (classmethods `apply(params, *frames)`, `to_code(params, inputs,
    output)`, `from_code(stmt, bound)`; metadata `id`, `title`, `description`, `category`,
    `icon`, `n_inputs` (+ `variadic`: that many or more, concat), `imports`,
    `requires`/`extra`), frozen pydantic `Params`, `OpRecord`
    (op id + params: what nodes and project files store). `CallOp` derives all three from
    one pandas call declaration (`method` or `function`, `positional`, `always`, `fixed`,
    `then` = a fixed tail like `.reset_index()` with `finish()` doing it in `apply`), so
    apply and generated code cannot drift. Per-column ops: `ops/series.py` (below).
  - `ops/{sources,columns,rows,missing,values,categorical,combine,reshape,stats,code}.py`: the built-in
    ops; `sources` are readers (`n_inputs = 0`, `extensions`, `format_id`, default
    `dtype_backend="pyarrow"`). Missing-value policy (null vs NaN): `ops/missing.py`
    docstring.
  - `ops/{strings,dates,timeseries}.py`: text, date / time and time series ops. Column-wise
    ops derive from `ops/series.py`: `ColumnOp` is the one per-column base (columns from
    `columns` or a single `column`, one `df.assign(...)` per step, results replace the
    columns or go to `<column><suffix>` if the params have `suffix`); `SeriesOp` declares
    one call like `CallOp` (`accessor` `str` / `dt` / `cat`, `method`, `function`), with
    `frame_call = True` for frame methods on the selection
    (`df.assign(**df[cols].clip(...))`, `columns=None` = `df.ffill()`). Code recognition
    via `unchain()` + `confirm()`, which regenerates the code and compares syntax trees.
  - `timecol.py`: the time column (no DatetimeIndex: time is a column named by params with
    the hint `TIME_COLUMN`, `{"widget": "column", "role": "time"}`); `time_column(session,
    node_id)` = nearest step on the path with a time param, else the first date / time
    column. The params dock pre-fills required time fields of a new step with it.
  - `registry.py`: entry-point registries; groups `datacook.ops` and `datacook.writers`
    (built-ins are registered in `pyproject.toml` the same way). `ops.default_ops()`.
  - `node.py`: immutable `Node` (id, record, parent ids, name, comment, `generation`: from a
    session-wide counter, never reused, also not for a re-added id).
  - `session.py`: `Session` = tree + `FrameCache` (`cache.py`, LRU, budget, pins, shared
    buffers counted once) + events (`events.py`) + executor. **The module docstring is the
    event/threading contract** the app builds on.
  - `restructure.py`: rules for deleting a middle step keeping its children
    (`Session.remove_step` re-parents them via `Session.reparent`, event `MOVED`).
  - `recipes.py`: recipes (op records with relative inputs, `.datacookrecipe` JSON, versioned),
    create from a path / subtree, `plan` / `apply` / `apply_many` / `import_files`, merge,
    `RecipeLibrary` (folder of recipe files). Required columns come from
    `ops.base.column_refs` (the params' column hints).
  - `codegen.py` / `parser.py`: script for a node path or the whole tree / back to steps;
    `codegen.render()` / `Session.render_code()` also return each node's line span.
  - `formats.py`: format registry (extension -> reader op / writer + Params + extra) and the
    writers (CSV, Parquet, Excel, script, project). `project.py`: JSON project files.
  - `frames.py`: the narrow interface to the dataframe library (summary, window, buffers,
    `ensure_backend`); nothing outside `ops/` and `formats.py` touches pandas directly.
- `src/datacook/app/` (Qt app; **`app/README.md` lists the API docks use**):
  `controllers/app.py` `AppController` owns session, executors, `SessionBridge`
  (`bridge.py`: engine events from any thread -> coalesced GUI-thread signals; FIFO with
  posted done callbacks), `AppState` (`state.py`: current node, column, preview, display,
  settings), `JobRunner` (`jobs.py`: one live job per slot, cancel, stale results dropped),
  `PinBook` (`pins.py`), `CommandController` (`QUndoStack`, `commands.py`), `NodeController`
  / `PreviewController` (the "current" / "preview" `ViewSlot`s, `slots.py`). Docks register
  through `uimodules.py` (`DOCKS` / `install()` in their own module, nothing shared to
  edit); `mainwindow.py` is the shell. Qt-free: `protocols`, `settings`, `pins`,
  `eventqueue`, `jobs`, `testing` (`FakeSession`). Memory invariant: views hold full frames
  only of pinned nodes (`app.held_ids() <= app.pins.pinned_ids()`). Docks in `docks/`
  (`nodetree`, `dataview`, `params`, `schema`, `code`, `messages`, `recipes`), widgets in
  `widgets/`, `actions.py` (Steps menu + command palette from the op registry), `controllers/project.py`
  (File menu, project files, reader dialog, exports, unsaved-changes prompt). The app runs on
  a plain `QApplication` (why: `application.py` docstring).
- `src/datacook/i18n.py`: `_()` returns a `LazyText` (translated when used as a string, so
  `set_language()` works after import); `N_()` marks pydantic field titles (plain strings,
  translate them in the UI with `translate()`). German catalog in `src/datacook/locales/de`
  (English = source strings); `uv run duty lang` = `tools/gettext_helpers.py scan / compile /
  stats` (GNU gettext; keywords `_` and `N_`; cutepandas labels are listed via `N_()` in
  `docks/schema.py`). `tests/test_i18n.py` fails when a msgid has no German translation.
- `src/datacook/core/application.py`: user dirs (platformdirs), resource paths.
- `src/datacook/allocator.py`: `configure()` (Arrow system pool, glibc mmap threshold 1 MiB;
  must run before pyarrow is imported: the GUI entry point `datacook.app:main` does it) and
  `release()` (pools' `release_unused` + `malloc_trim`, called by "Free memory"). Without it
  freed frames stay resident (allocator retention, not live references; numbers in the
  module docstring and the workspace plan).
- `src/datacook/constants/iconnames.py`, `resources/`: fonts, theme, sample data (no app logo / icon yet).
- `tools/bench_memory.py`: the plan's memory benchmark on the engine vs raw pandas.
- `tools/ui_inspect.py`: offscreen Qt UI screenshot and widget-tree inspection harness
  (captures full window, individual docks, named widgets or dialogs at configurable
  sizes/languages/scenarios, plus layout-clipping diagnostics).
- `legacy/`: the old GUI, plugins, app glue, old core and op catalogue (`legacy/methods/`,
  to port in phase 4). Not imported, packaged, linted, type-checked or tested. See
  `legacy/README.md`.

## Where to look

| Task | Location |
| --- | --- |
| Add an op | `src/datacook/engine/ops/` + entry point in `pyproject.toml` + a case in `tests/op_cases.py` / golden code in `tests/test_ops.py` |
| Add a reader / writer | `ops/sources.py` (reader op) / `formats.py` (writer) + entry point |
| Cache, events, threading | `src/datacook/engine/session.py`, `cache.py` |
| App state / sync, a new dock | `src/datacook/app/README.md`, `uimodules.py`, `tests/app/test_flows.py` |
| Whole-app behaviour, memory numbers | `tests/app/test_smoke.py` (smoke test; `DATACOOK_MEMORY_SCENARIO=1` for the 3M-row memory scenario) |
| Recipes, delete a middle step | `engine/recipes.py`, `engine/restructure.py`, `app/docks/recipes.py`, `tests/test_recipes.py`, `tests/app/test_recipes.py` |
| Generated code / code parser | `codegen.py`, `parser.py`, `tests/test_codegen.py` |
| Old ops / readers to port | `legacy/methods/`, `legacy/plugins/`, status in `docs/feature-inventory.md` |
| Old app code (incl. deleted GUI) | `git show pre-rework:processanalyzer/<path>` (old history: private archive repo, not in this one) |

## Commands

```bash
uv sync --all-extras          # setup (Python 3.14)
uv run pytest                 # tests
uv run ruff check . && uv run ruff format --check .
uv run ty check               # type check (warnings fail too)
uv run mknodes build          # docs (README + auto-generated pages)
uv build
uv run duty lang              # gettext: rescan, merge, compile, stats (needs GNU gettext)
uv run python tools/demo_data.py demo   # demo data + project in ./demo
uv run python tools/ui_inspect.py --scenario all --tree --out /tmp/dc-ui  # UI screenshots
ARROW_DEFAULT_MEMORY_POOL=system uv run python tools/bench_memory.py engine_keep
```

CI (`.github/workflows/build.yml`, copier-phil65 template): ruff, ruff format, ty, pytest on
3.14 (+ 3.15 allowed to fail), Linux/macOS/Windows; plus `test-free-threaded`: engine tests
and the Qt-free app core tests (`tests/test_app_core.py`) on 3.14t with `PYTHON_GIL=0` (no
Qt installed, allowed to fail). App (Qt) tests go to `tests/app/` (offscreen), which
`tests/conftest.py` skips when PySide6 is missing. Locally:
`uv venv -p 3.14t <dir>`, `uv pip install --no-deps -e .` + the engine deps (see the job).
Docs: `documentation.yml` -> GitHub Pages.

## Conventions

- copier-phil65 template (`.copier-answers.yml`); update with
  `uvx --with copier-templates-extensions copier update --trust --defaults --skip-answered`.
- Op `Params` are frozen pydantic models (`extra="forbid"`); field titles via `N_()`, UI hints
  in `json_schema_extra`: `{"widget": "file" | "code" | "column" | "columns" | "column_map"}`
  (`column` = one column name of the input, `columns` = a list of them, `column_map` = a dict
  keyed by column names; `"input": 1` = the columns come from the second input, default 0).
  Every field holding column names carries one (the app builds column choosers from it).
  Every op needs: apply == exec of its generated code, `parse(to_code) == record`, golden
  code (see `tests/test_ops.py`).
- Generated code: one block per step (`# <name or title>` + code, blank line between). The
  parser reads blocks; a block with any unknown statement becomes one `CustomCode` step.
  Each op's code is one statement (`out = <expr of the inputs>`) that no other op
  recognises: the parser tries ops in registry order and the first match wins (a `CallOp`
  with keywords its Params lack, or without its `fixed` keywords, does not match).
- No defensive copies: pandas 3 copy-on-write. Ops never mutate inputs (`CustomCode` gets a
  shallow copy). Ops that use randomness take a seed (`Sample.random_state`, default 0) so a
  recomputed node gives the same result.
- Conventional commits (commitizen hook). The version lives only in `pyproject.toml`.

## Pitfalls

- The engine must not import Qt (subprocess test). Keep pandas behind `frames.py` / ops.
- pytest runs with `-p no:logfire`: logfire's pytest plugin (docs group, via mknodes) plus
  pytest-qt's PySide6 import hook break pydantic's lazy imports at collection time.
- Entry points are read from the installed metadata: after adding an op to `pyproject.toml`
  run `uv sync` (the editable install is rebuilt) or the registry will not see it.
- `astype` with numpy dtype names (`"float32"`) leaves the pyarrow world; use
  `"float32[pyarrow]"` etc. to keep arrow memory sharing.
- Arrow memory: with the default pyarrow pool (jemalloc/mimalloc) RSS keeps freed memory;
  `ARROW_DEFAULT_MEMORY_POOL=system` for measurements.
- The GitHub default branch is still `master`; work happens on `main`.
- New UI strings: add the German translation (`uv run duty lang`, edit
  `locales/de/LC_MESSAGES/datacook.po`, compile) or `test_german_catalog_is_complete` fails.
- Tests that close a `MainWindow` with unsaved changes rely on the autouse fixture in
  `tests/app/conftest.py` (no modal Save? dialog); outside it, set
  `window.project.ask_save_changes`.
- License: MIT (`LICENSE`, `license = "MIT"` in pyproject.toml).
