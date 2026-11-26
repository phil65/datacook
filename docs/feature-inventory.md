# Feature inventory: old app -> rework

Every user-facing feature of the old app (package `processanalyzer`, "ProcessAnalyzer") and
where it went. The old state is tagged **`pre-rework`** (commit `978c73cc`, before phase 0);
read old code with `git show pre-rework:processanalyzer/<path>` (old history: private archive repo, not in this one). Paths in the "Old" column
are relative to `processanalyzer/` at that tag. Plan and owner decisions: `DATACOOK_PLAN.md`
in the owner's OSS workspace (§0 = binding owner decisions, §2 = engine notes, §4 = cut / keep
lists, §6 = phases and work packages, "WP4.3" etc.).

**Rule:** before deleting anything from `legacy/` or porting a phase, check this file and
update the rows you touch. Nothing leaves the app without a row saying where it went.

Status values:

- **ported**: exists in the new code (location given, checked against `main`).
- **planned**: covered by a phase / work package of the plan (phase or WP given).
- **backlog**: deferred by an owner decision (§0: "special readers, further exporters ->
  backlog"); not dropped, but no phase.
- **dropped**: removed by an owner decision (cited).
- **open**: not covered by any phase yet: **owner to decide** (`O<n>` = item in the list
  below).

## Summary (2026-11-25)

| Status | Rows |
|---|---|
| ported | 114 |
| planned | 43 |
| open | 41 |
| dropped | 10 |
| backlog | 4 (20 plugins) |
| **total** | **212** |

Counted by a row's first status; a row like "ported partly: ...; browser open (O4)" counts as
ported, its open part is in the list below. The old op catalogue (95 method classes,
`methods/`) is folded into 41 rows (§8): 30 ported (incl. custom code; WP4.1 / 4.2 / 4.3 / 4.4 / 4.5 done
2026-11-25), the rest **planned** for phase 4. "ported" includes features that now exist in a different form (noted in the row).

### Open items (owner to decide)

- **O1 Recipes.** Ported 2026-11-25 (`engine/recipes.py`, `app/docks/recipes.py`): create
  from a step path or subtree, library (rename / describe / delete / merge / import / export),
  apply to one or several steps, import recipe on many files. Still open: apply a recipe to
  every group of a group-by (with O4), create a recipe from typed code (with O3).
- **O2 Batch import.** Several files or a whole folder at once; drag & drop files from the
  OS onto the dataset list.
- **O3 Import from code.** A root step from a script that builds the table (`ds = ...`).
  `CustomCode` needs an input; `Table data` only covers typed-in tables.
- **O4 Group and resample browsers.** Group by column / category / index, or resample, opened
  a table of groups (size, start, end, duration) with: extract groups as datasets (Ctrl+E,
  Shift+E: without the key column, or as one dataset), per-group stats (describe, corr, cov),
  filter groups (by size, custom function, hide empty, extract ungrouped rows), transform,
  apply a recipe per group, resample method choice. The new app has the
  "Group and aggregate" and "Resample" ops (WP4.4), no browser.
- **O5 Editing inside the views (as recorded steps).** Edit a cell; rename a column or change
  its type inline (Columns list); drag to reorder columns / categories; context menus on the
  data view (delete rows, delete cells -> NaN, set row as header, keep rows with this value,
  show a JSON cell as a tree) and on the column list (column ops on the selection); clicking
  a column in the Columns dock scrolls the data view to it. The new docks are read-only;
  ops come from the Steps menu / palette.
- **O6 History restructuring.** Delete one middle step keeping its children: ported
  2026-11-25 ("Delete step (keep following steps)"). Still open: merge / collapse consecutive
  steps into one block.
- **O7 Several tables side by side.** "Open as tab" (Shift+Return), detachable tabs, Ctrl+W.
  §3.1 mentions comparing two nodes; no phase.
- **O8 One op on several selections.** Old actions ran on every selected dataset (e.g. rename
  / prefix with `{i}` and `{name}` templates).
- **O9 Estimator management.** Estimators page (list with own history, recent estimators),
  import an estimator from code, set params, make pipeline, online help, properties, feature
  importance. WP4.8 covers fit / transform / predict as ops only.
- **O10 Session autosave / restore.** The old app saved all datasets' histories on exit and
  listed them on the start page ("Recent datasets", "Recent estimators") for replay. New: Open
  recent (project files) and an unsaved-changes prompt only.
- **O11 Settings dialog.** Theme (a dark `darktheme.qss` is still in `resources/`, unused),
  Qt style, toolbar style, log format, "show shortcuts in context menus", "record history
  collapsed", installed plugins list, supported file types + register file associations with
  the OS. New: `AppSettings` file without UI (only language has a menu).
- **O12 Window state and chrome.** Save / restore dock layout and window geometry; fullscreen
  (F11); splash screen and start page with logo; running-jobs count in the status bar.
- **O13 CLI and logging.** `--reset`, `--use-default`, `--disable-plugins`, `--version`; log
  file in the user data dir (`logging.yaml`).
- **O14 Reader / writer option gaps.** CSV: encoding detection (chardet), delimiter and
  header sniffing, NA value; Excel: `.xls`, `.xlsb`, `.ods` (new: `.xlsx` / `.xlsm`); SQLite:
  import every table at once (new: one query); CSV export: header on/off, NA representation.
- **O15 Readers kept in §4 without a phase**: seaborn sample datasets; Arff reader (hidden in
  the scipy plugin, in no list).
- **O16 In-app help.** Old Help page (bundled docs in a web view), datetime format help table.
  The Help menu is empty; phase 7 plans user docs, not an in-app entry.
- **O17 Debug and unwired pieces (suggest: drop).** "Show YAML" of a history; Files page
  (file explorer) and project manager widgets (both already unwired at `pre-rework`).

## 1. App shell, start-up, settings

| Feature | Old | Status |
|---|---|---|
| Sidebar pages Start / Datasets / Recipes / Estimators / Help / Activity log (F1, F2, F4-F7) | `gui/mainwindow.py` | ported as one dock window `app/mainwindow.py` (pages: rows below) |
| View menu to toggle docks ("Docks" menu) | `gui/pages/datasetspage.py` | ported: View menu (`mainwindow.py`) |
| Fullscreen (F11) | `gui/mainwindow.py` | open (O12) |
| Save / restore window and dock layout | `gui/mainwindow.py` | open (O12) |
| Status bar: running jobs, busy progress bar | `gui/mainwindow.py`, `core/threads.py` | ported partly: "Computing" badges in the tree, data-view overlays (`docks/nodetree.py`, `docks/dataview.py`); job count open (O12) |
| Modal progress dialog for blocking jobs | `gui/mainwindow.py` | ported differently: async jobs (`app/jobs.py`) + overlay |
| Error message box for failed jobs | `core/threads.py` | ported: Messages dock + failure overlay with "Go to step" / "Retry" |
| Popup toasts ("Added new item") | `core/signals.py` | ported: `app.notify()` -> Messages dock |
| Splash screen, start page logo | `__main__.py`, `gui/pages/startpage.py` | open (O12) |
| Start page: recent datasets / estimators (auto-saved histories) | `gui/pages/startpage.py` | open (O10) |
| Open files given on the command line | `__main__.py` | ported: `app/application.py` `main()` / `open_paths()` |
| CLI `--reset`, `--use-default`, `--disable-plugins`, `--version` | `__main__.py` | open (O13) |
| Log file in user dir (`logging.yaml`) | `logging.yaml` | open (O13) |
| Activity log page (log view, Clear) | `gui/pages/logpage.py` | ported: Messages dock (level filter, Clear) `docks/messages.py` |
| Settings: language | `gui/pages/settingspage.py` | ported: View > Language (`application.LanguageMenu`) |
| Settings: theme, Qt style, toolbar style | `gui/pages/settingspage.py`, `mainapp.py` | open (O11) |
| Settings: log level | `gui/pages/settingspage.py` | ported: level filter in Messages dock |
| Settings: log format, show context-menu shortcuts, record history collapsed | `gui/pages/settingspage.py` | open (O11) |
| Settings: code viewer choice | `gui/pages/settingspage.py` | dropped (§0: pyqode / QScintilla replaced by the code view) |
| Settings: installed plugins list | `gui/pages/settingspage.py`, `gui/trees/pluginstree.py` | open (O11) |
| Settings: supported file types + register file associations | `gui/pages/settingspage.py` | open (O11) |
| Settings storage (dynaconf YAML) | `core/config.py`, `config_default.yaml` | ported: `app/settings.py` `AppSettings` (JSON, platformdirs) |
| Settings migration between versions | `core/config.py` | dropped (§0: rename without backwards compatibility) |
| Bundled fonts loaded at start | `mainapp.py` | open (O11; `resources/fonts` present, unused) |
| License check (key + NTP) | `core/licensemanager.py`, `gui/dialogs/licensedialog.py` | dropped (§0 licensing) |
| Sentry error reporting | `plugins/datacook_sentry_plugin` | dropped (§0 sentry) |
| PyInstaller / NSIS / Azure packaging | `main.spec`, `install.nsi`, `hooks/` (repo root) | dropped (§0 packaging) |
| i18n: gettext catalogs de + en, `_()` | `locales/`, `core/application.py` | ported: `datacook/i18n.py`, `locales/de` (English = source), runtime switch |
| Help page (bundled docs in a web view) | `gui/pages/helppage.py` | open (O16); user docs planned (7) |
| Datetime format help table (from the web) | `gui/guihelpers.py` `open_help` | open (O16) |
| Old user docs (MkDocs, mostly stubs + CLI page) | `docs/` (repo root) | planned (7) |

## 2. Datasets page: dataset list, import / export, projects

| Feature | Old | Status |
|---|---|---|
| Dataset list (Title, Rows, Features, Last operation, Index) | `models/datasetmanagermodel.py`, `gui/trees/datasettree.py` | ported: Steps tree (Step, Shape, Size, badges) `docks/nodetree.py` |
| Sort the dataset list by column, reorder by drag | `gui/trees/basehistoryitemtree.py` | open (O5, minor) |
| Add dataset > From file (format by extension) | `gui/datasetwidget.py`, `gui/guihelpers.py` | ported: File > Open data file + reader dialog with preview (`controllers/project.py`, `widgets/readerdialog.py`, `engine/formats.py`) |
| Import several files / a folder at once | `gui/trees/basehistoryitemtree.py` | open (O2) |
| Drag & drop files from the OS | `gui/trees/basehistoryitemtree.py` | open (O2) |
| Add dataset > From code | `gui/pages/datasetspage.py` | open (O3) |
| Export dataset menu (exporter plugins) | `gui/datasetwidget.py` | ported: File > Export (CSV, Parquet, Excel, Python script) |
| Load / Save project (Ctrl+L / Ctrl+S; YAML of histories, replayed) | `gui/pages/datasetspage.py` | ported: File > New / Open / Save (As) project, Open recent (JSON node records, `engine/project.py`) |
| Auto-save of all datasets on exit | `gui/pages/datasetspage.py` | open (O10) |
| Open dataset as read-only tab (Shift+Return), detachable tabs, Ctrl+W | `actions/datasetactions.py`, `gui/pages/datasetspage.py` | open (O7) |
| Rename dataset (`{i}` / `{name}` templates) | `actions/datasetactions.py` | ported: Rename step (F2); templates open (O8) |
| Apply an action to several selected datasets | `gui/baseitemview.py` | open (O8) |
| Duplicate dataset (Ctrl+D) | `actions/datasetactions.py` | ported differently: "Branch from here" (no copy) |
| Remove dataset (Del) | `actions/datasetactions.py` | ported: Delete step (Del, subtree, undoable) |
| Properties (Alt+Return): name, comment, info, history, code | `gui/dialogs/propertiesdialog.py` | ported: rename / "Comment…" in the tree, Columns dock, Code dock |
| Apply recipe to dataset | `actions/datasetactions.py` | ported: Recipes dock "Apply to current step" / "Apply to steps…" (columns checked first, one undo step; `app/docks/recipes.py`, `engine/recipes.py`) |
| Context menus grouped by category (submenus) | `gui/menus.py`, `gui/baseitemview.py` | ported: Steps menu by category + command palette (Ctrl+Shift+P) `app/actions.py` |

## 3. Datasets page: toolbar dialogs

| Feature | Old | Status |
|---|---|---|
| Calculations (column op column / number -> new column) | `gui/datasetwidget.py` | ported: "Calculate columns" (formulas, `DataFrame.eval`; `ops/columns.py`) |
| NaN handling dialog: NaN count / share per column | `gui/dialogs/nanhandlingdialog.py` | ported: Columns dock "Nulls" (`docks/schema.py`) |
| NaN dialog: fill (ffill / bfill / value), remove NaN rows (any / all) | `gui/dialogs/nanhandlingdialog.py` | ported: `engine/ops/missing.py` (fill value, fill forward / backward, drop missing) |
| NaN dialog: interpolate, extract NaN rows, replace value with NaN, batch drop | `gui/dialogs/nanhandlingdialog.py`, `actions/nanhandlingactions.py` | ported: "Interpolate missing values", "Rows with missing values", "Drop columns with missing values" (`ops/missing.py`), "Replace values" with an empty new value (`ops/values.py`); NaN vs missing policy: `ops/missing.py` docstring |
| Decision trees dialog (target, model, result) | `gui/dialogs/decisiontreedialog.py` | planned (WP4.8 part 2) |
| Clustering dialog (model, plot, adds cluster column) | `gui/dialogs/clusterdialog.py`, `gui/modelselector.py` | ported: "Cluster rows" (KMeans / DBSCAN, adds cluster column; `ops/estimators.py`, `sklearn` extra); plot planned (WP5.1) |
| Reshape > Melt | `gui/dialogs/meltdialog.py` | ported: "Unpivot (melt)" (identifier columns, columns to unpivot, names of the new columns; `ops/reshape.py`) |
| Reshape > Pivot (+ totals, live result) | `gui/dialogs/pivotdialog.py` | ported: "Pivot table" (row keys, column with the new column names, value column, function, totals + label, fill value; `ops/reshape.py`); live result = the params preview |
| Reshape > Frequency table (crosstab, normalize, totals) | `gui/dialogs/crosstabdialog.py` | ported: "Frequency table" (`pd.crosstab`, shares of the total / per row / per column, totals; `ops/reshape.py`) |
| Reshape > Transpose | `gui/datasetwidget.py` | ported: "Transpose" (new column names from a column or the row numbers, old names in a column; `ops/reshape.py`) |
| Statistical analysis menu (describe, var, cov, rank, mode, corr) | `actions/statsactions.py` | ported: Statistics category (`ops/stats.py`): "Descriptive statistics", "Variances", "Covariances", "Correlations" (Pearson / Spearman / Kendall), "Most frequent values" (mode), "Rank values" (a column op, `<column>_rank`), plus "Value counts"; results are new tables with a label column (`statistic` / `column`); the old axis option is dropped (no index: transpose first) |
| Split dataset (bool / numeric threshold, extra rows, adds split-info columns) | `gui/dialogs/splitdialog.py`, `gui/processtable.py` | planned (phase 4: pandastools `split`, §2) |
| Rolling / expanding window ops (window type, method, center) | `actions/datasetactions.py` | ported: "Rolling window" (rows or a duration on the time column, function, min. values, center), "Cumulative (expanding window)" (`ops/timeseries.py`); scipy window types (`win_type`) not ported (scipy is no dependency) |
| One-hot encode | `actions/datasetactions.py` | planned (phase 4; §2 `to_dummies`) |
| Reset index | `actions/datasetactions.py` | ported: "Reset index" (`ops/rows.py`) |
| Filter submenu: select dtypes, every n-th row, random sample, n smallest / largest | `actions/filteractions.py` | ported: "Select columns by type" (`ops/columns.py`), "Slice rows" (step), "Random sample", "Largest values" / "Smallest values" (`ops/rows.py`) |
| Merge (two datasets) | `actions/mergeactions.py` | ported: Merge op, second input chooser (`ops/combine.py`, `app/actions.py`) |
| Concat (Ctrl+M) | `actions/mergeactions.py` | ported: "Concatenate" (two or more inputs, `Op.variadic`; rows below each other or side by side, outer / inner, sort; `ops/combine.py`), the other inputs are checked in a list (`app/actions.py`); MultiIndex keys dropped (no index); Ctrl+M not mapped |
| Correlation with another dataset (corrwith) | `actions/mergeactions.py` | ported: "Correlation with another table" (`ops/stats.py`; Pearson only: pandas needs scipy for Spearman / Kendall here, no dependency; axis dropped) |
| Estimator submenu: apply transformer, train, predict | `actions/estimatoractions.py` | ported: single-step transformers, PCA, clustering and "Apply model trained on another table" (`ops/estimators.py`, `sklearn` extra) |

## 4. Datasets page: Feature list dock (columns)

| Feature | Old | Status |
|---|---|---|
| Column list: name, dtype icon, type, size; NaN tooltip | `models/featurelistmodel.py` | ported: Columns dock + column profile (`docks/schema.py`, cutepandas) |
| Click a column -> table jumps to it | `gui/pages/datasetspage.py` | open (O5) |
| Rename column inline / via context menu | `models/featurelistmodel.py`, `actions/featureactions.py` | ported as op "Rename columns" (`ops/columns.py`); inline open (O5) |
| Change dtype via dtype delegate (incl. to_datetime with format, bool mapping) | `gui/delegates/dtypedelegate.py` | ported as op "Change data type"; to_datetime (format, day first, epoch unit, UTC, invalid -> missing) as "Convert to date / time" (`ops/dates.py`); inline open (O5) |
| Reorder columns by drag | `models/featurelistmodel.py` | ported as ops: "Move columns" (to the front / end), any order via "Select columns" (`ops/columns.py`); drag open (O5) |
| Sort columns by name / type / size (reorders the frame) | `models/featurelistmodel.py` | ported partly: by name "Sort columns" (`ops/columns.py`); by type / size open (O5, column list sorting) |
| Drop index levels on the list -> reset index | `models/featurelistmodel.py` | planned (§2 key columns, phase 4) |
| Remove columns (Del) | `actions/featureactions.py` | ported: "Drop columns" |
| Merge columns (with divider) | `actions/featureactions.py` | ported: "Combine columns" (`ops/columns.py`) |
| Bin values (cut: equal width / intervals, edges) | `actions/featureactions.py` | ported: "Bin values" (`pd.cut`: a number of equal-width bins or the edges, labels, which edges are included, precision; results in `<column>_bin`; `ops/stats.py`) |
| Duplicate columns (Ctrl+D) | `actions/featureactions.py` | ported: "Duplicate columns" (`ops/columns.py`) |
| Descriptive stats of selected columns (Ctrl+S) | `actions/featureactions.py` | ported: "Descriptive statistics" with a column subset (`ops/stats.py`); Ctrl+S not mapped |
| Set as index | `actions/featureactions.py` | ported for time: "Use as time column" (`ops/timeseries.py`; sorts, time series steps default to it: `engine/timecol.py`); key columns planned (§2, phase 4) |
| Downcast (smallest dtypes) | `actions/featureactions.py` | ported: "Downcast numbers" (`pd.to_numeric(downcast=...)`, keeps arrow dtypes; `ops/columns.py`) |
| Sort by column (orientation, NA position) | `actions/featureactions.py` | ported: "Sort rows" (`ops/rows.py`) |
| Group by (Ctrl+G) -> groups browser | `actions/featureactions.py`, `gui/trees/groupedtree.py` | ported partly: "Group and aggregate" (`ops/combine.py`); browser open (O4) |
| Resample (Ctrl+R) -> resample browser | `actions/featureactions.py`, `gui/trees/resampledtree.py` | ported as ops "Resample" (aggregations per interval, optionally per group) and "Upsample" (`ops/timeseries.py`); browser open (O4) |
| Tolerance bands | `actions/featureactions.py` | ported: "Tolerance bands" (`ops/timeseries.py`) |
| Drop duplicates (subset, keep) | `actions/featureactions.py` | ported: "Drop duplicates" |
| Shift, trim (clip), replace values, difference | `actions/sliceactions.py` | ported: "Clip values", "Replace values" (`ops/values.py`); "Shift values", "Difference", "Relative change" (`ops/timeseries.py`) |
| Interpolate / fill / replace with NaN on columns | `actions/sliceactions.py` | ported: fill (value, forward / backward, mean / median / mode), interpolate (`ops/missing.py`, column subset), replace with missing ("Replace values", `ops/values.py`) |
| String ops on columns (upper, lower, slice, contains, regex extract, split) | `actions/stringactions.py` | ported (`ops/strings.py`, see §8) |
| Extract time info (date, time, year, ..., quarter, weekday) | `actions/datetimeactions.py`, `gui/dialogs/datetimeattributesdialog.py` | ported: "Extract date / time parts" (`ops/dates.py`) |
| Date to string (strftime) | `actions/datetimeactions.py` | ported: "Date / time to text" (`ops/dates.py`) |

## 5. Datasets page: Feature info (categories), Table view, Index list, History

| Feature | Old | Status |
|---|---|---|
| Categories of a categorical column | `gui/trees/categorytree.py`, `models/categorymodel.py` | ported: category table in the Columns dock |
| Rename (F2), add, remove (Del), reorder (drag / sort), ordered toggle, remove unused | `models/categorymodel.py`, `actions/categoryactions.py` | ported as ops (`ops/categorical.py`: rename, add, remove, reorder, set, as ordered / unordered, remove unused); inline editing open (O5) |
| Rename categories by function (code) | `gui/trees/categorytree.py` | ported as: "Rename categories" (old -> new mapping, `ops/categorical.py`); a function only as "Custom code" |
| Group by category -> groups browser | `gui/trees/categorytree.py` | open (O4) |
| Data table: virtual model, dtype icons, tooltips, value colouring | `gui/tablecontainer.py`, `models/pandasmodel.py`, `gui/delegates/tablecolordelegate.py` | ported: data view (`docks/dataview.py`, cutepandas `DataFrameViewer`, `settings.color_values`) |
| Index columns shown beside the data | `gui/tableindexwidget.py`, `models/pandasindexmodel.py` | planned (§2: no index, key columns) |
| Sort by header click (recorded as a sort step) | `models/pandasmodel.py` | ported: display-only sort + "Add as sort step" (header menu) |
| Edit cells (recorded as a step) | `models/pandasmodel.py` | open (O5) |
| Copy selection (Ctrl+C) | `actions/rowactions.py` | ported: cutepandas `DataFrameViewer.copy` (Ctrl+C) |
| Keep rows with this value (Ctrl+E, isin) | `actions/rowactions.py` | open (O5): the op exists ("Filter by values", `ops/rows.py`), the context menu does not |
| Delete rows (Shift+Del), delete cells (-> NaN), set row as header (Ctrl+H) | `actions/rowactions.py` | open (O5) |
| Show a JSON cell as a tree | `actions/rowactions.py` | open (O5) |
| Index list: name, type, monotonic; rename, change type, to_datetime | `gui/trees/indextree.py`, `models/indexmodel.py` | ported partly: the time column ("Use as time column", `engine/timecol.py`) and to_datetime ("Convert to date / time"); key columns planned (§2) |
| Index: reorder levels / set index by drag | `models/indexmodel.py` | planned (§2, phase 4) |
| Index: remove, reset, sort, group by, resample | `actions/indexactions.py` | planned (§2); resample ported (op "Resample", `ops/timeseries.py`); group browser open (O4) |
| Index: filter range (span slider dialog) | `actions/indexactions.py`, `gui/dialogs/filterdialog.py` | ported partly: "Slice rows" (by position, `ops/rows.py`); by index value with the key / time column (§2, WP4.4); span slider open (O5) |
| Index: split by gaps / time gaps | `actions/indexactions.py` | ported on a column: "Number segments between gaps" (`ops/timeseries.py`) |
| History dock: per-dataset op tree with rows / columns per step | `gui/trees/historytree.py`, `models/historymodel.py` | ported: Steps tree (one tree for all datasets, shape per step) |
| Show code of one step (Ctrl+Return) / code to build the dataset (Shift+Return) | `actions/historyactions.py` | ported: Code dock (current step highlighted, `docks/code.py`), Export script |
| Edit the code of a step | `actions/recipeactions.py` | planned (WP3.2 editable code pane); params: "Edit step…" (Ctrl+E) ported |
| Replay history up to here | `actions/historyactions.py` | ported: steps compute on demand, "Recompute" overlay |
| Remove one step, re-attach its children | `actions/historyactions.py`, `core/history.py` | ported: "Delete step (keep following steps)" (Shift+Del, tree context menu; `Session.remove_step` / `reparent`, rules in `engine/restructure.py`, undoable `RemoveStepCommand`); refused for sources and merges |
| Merge selected steps / collapse all | `actions/historyactions.py` | open (O6, rest) |
| Show YAML of a history | `actions/historyactions.py` | open (O17) |
| Add as recipe / collapse and add as recipe | `actions/historyactions.py` | ported differently: Steps > Recipes / tree context menu "Save steps up to here as recipe…", "Save step and following steps as recipe…" (op records, no code collapse; `app/docks/recipes.py`) |

## 6. Groups and resample browsers

| Feature | Old | Status |
|---|---|---|
| Groups table (size, start, end, duration), sortable | `gui/trees/groupedtree.py`, `models/basegroupbymodel.py`, `models/processstatsmodel.py` | open (O4) |
| Extract groups as datasets (Ctrl+E), without key (Shift+E), as one dataset | `actions/groupbyactions.py` | open (O4) |
| Per-group descriptive stats (Ctrl+S), correlations, covariances | `actions/groupbyactions.py`, `gui/trees/groupedtree.py` | open (O4) |
| Filter groups (by size, custom function), hide empty, extract ungrouped rows | `gui/trees/groupedtree.py` | open (O4) |
| Group transform (new column), apply recipe to groups | `gui/trees/groupedtree.py` | open (O4, O1) |
| Resample browser: method choice, transform, apply recipe | `gui/trees/resampledtree.py` | open (O4) |
| Signal analysis (score matrix of processes) | `actions/groupbyactions.py` | dropped (§0 processvalues) |

## 7. Recipes, estimators, files, projects pages

| Feature | Old | Status |
|---|---|---|
| Recipes page: list + code preview, saved on exit | `gui/pages/recipespage.py`, `gui/trees/recipetree.py` | ported: Recipes dock (list + description, required columns, steps), one `.datacookrecipe` file per recipe in the library folder (`<user data dir>/recipes`, `RecipeLibrary`), saved at once |
| Create custom recipe (name + code) | `gui/trees/recipetree.py` | ported partly: recipes are made from steps (name, description); from typed code open (O3) |
| Edit recipe code, remove, merge recipes (Ctrl+M) | `actions/recipeactions.py` | ported partly: rename, edit description, delete, merge (`RecipeLibrary`, Recipes dock context menu); edit steps = apply, edit, save again |
| Execute an import recipe | `actions/recipeactions.py` | ported: Recipes dock "Run" (import recipe = starts with a reader) |
| Apply an import recipe to many files | `actions/fileactions.py` | ported: "Run on files…" (one root per file, reader path swapped; `recipes.import_files`); folder / drag & drop open (O2) |
| Estimators page: list with history, add, import from code | `gui/pages/estimatorspage.py`, `gui/trees/estimatortree.py` | open (O9) |
| Add estimator dialog (browse by type, params) | `gui/dialogs/estimatorselectiondialog.py`, `gui/trees/sklearnmodelstree.py` | planned (WP4.8) |
| Estimator: set params, make pipeline, online help, properties, show code | `actions/sklearnactions.py` | open (O9) |
| Estimator: feature importance | `core/estimator.py` | open (O9) |
| Files page: file explorer, import, apply recipe, delete (unwired at `pre-rework`) | `gui/pages/fileexplorerpage.py`, `gui/trees/filetree.py` | open (O17) |
| Project manager widgets (unwired at `pre-rework`) | `gui/projectmanagercontainer.py`, `core/project.py` | open (O17) |

## 8. Op catalogue (`methods/`, 95 method classes)

Replay of every method was tested by `tests/test_shit.py`; the new engine tests
apply == generated code == parsed code per op (`tests/test_ops.py`).

| Method(s) | Old | Status |
|---|---|---|
| `QueryMethod` | `methods/pandas/datasetmethods.py` | ported: "Filter rows" (`ops/rows.py`) |
| `SortValuesMethod` | same | ported: "Sort rows" |
| `SampleMethod` | same | ported: "Random sample" (seeded) |
| `DropDuplicatesMethod` | same | ported: "Drop duplicates" |
| `DropMethod` | same | ported: "Drop columns" (`ops/columns.py`) |
| `RenameMethod` | same | ported: "Rename columns" |
| `AsTypeMethod` | same | ported: "Change data type" |
| `DropNaMethod` | same | ported: "Drop rows with missing values" (`ops/missing.py`) |
| `FillNaMethod` | same | ported: "Fill missing values" / "Fill forward" / "Fill backward" |
| `GroupByMethod` | same | ported partly: "Group and aggregate" (`ops/combine.py`) |
| `SelectDtypesMethod`, `ConvertDtypesMethod`, `AbsMethod` | same | ported: "Select columns by type", "Infer data types" (`ops/columns.py`; pandas 3 deprecated the `convert_*` flags, only the backend is a param), "Absolute values" (`ops/values.py`) |
| `AddPrefixMethod`, `AddSuffixMethod` | same | ported: "Add prefix" / "Add suffix" (`ops/columns.py`) |
| `NSmallestMethod`, `NLargestMethod` | same | ported: "Smallest values" / "Largest values" (`ops/rows.py`) |
| `ReindexMethod` | same | planned (§2: join on a key range, phase 4) |
| `ShiftMethod`, `DiffMethod` | same | ported (per column): "Shift values", "Difference", plus "Relative change" (`ops/timeseries.py`) |
| `ClipMethod`, `ReplaceMethod` | same | ported: "Clip values", "Replace values" (`ops/values.py`) |
| `IsNaMethod`, `InterpolateMethod`, `ReplaceWithNaMethod` | same | ported: "Missing value mask", "Interpolate missing values" (`ops/missing.py`), "Replace values" with an empty new value (writes `pd.NA`, keeps arrow dtypes; `ops/values.py`) |
| `ResetIndexMethod`, `RemoveIndexMethod` | same | ported: "Reset index" (`drop` = remove; `ops/rows.py`) |
| `SetIndexMethod`, `SortIndexMethod`, `ReorderLevelsMethod` | same | ported partly: a time index = "Use as time column" (`ops/timeseries.py`, `engine/timecol.py`); key columns planned (§2) |
| `AsFreqMethod`, `ResampleMethod` | same | ported: "Upsample" (method asfreq / ffill / bfill / nearest / interpolate), "Resample" (`ops/timeseries.py`; time as a column, `resample(on=...)` / `pd.Grouper(key=...)`) |
| `StackMethod`, `TransposeMethod`, `MeltMethod`, `PivotMethod`, `PivotTableMethod` | same | ported: "Transpose", "Unpivot (melt)", "Pivot table" (`ops/reshape.py`; pivot = pivot table with `first`); stack = unpivot here (no MultiIndex columns) |
| `CorrMethod`, `RankMethod`, `ModeMethod`, `DescribeMethod`, `VarMethod`, `CovMethod` | same | ported: `ops/stats.py` (see the statistics menu row) |
| Category: rename, add, remove, reorder, set ordered / unordered, remove unused (7) | `methods/pandas/categorymethods.py` | ported: `ops/categorical.py` (+ "Set categories"); legacy module deleted |
| Datetime: strftime, month name, day name (3) | `methods/pandas/datetimemethods.py` | ported: "Date / time to text", "Extract date / time parts" (parts `month_name` / `day_name`, locale) (`ops/dates.py`); new: time zones (set / convert), round, convert to date / time; legacy module deleted |
| Estimator: set params, fit, fit-transform, transform, predict, fit-predict (6) | `methods/pandas/estimatormethods.py` | ported: `FitTransform` ("Scale / transform columns"), `PCA` ("Principal components (PCA)"), `Cluster` ("Cluster rows", KMeans / DBSCAN) and `ApplyModel` ("Apply model trained on another table": fit on training table, transform / predict on target table; no model nodes) (`ops/estimators.py`, `sklearn` extra) |
| Group-by: filter, get group, transform (3) | `methods/pandas/groupbymethods.py` | planned (WP4.6) |
| Index: astype, rename, set names (3) | `methods/pandas/indexmethods.py` | planned (§2, phase 4) |
| `MergeMethod` (DataFrame.merge) | `methods/pandas/mergemethods.py` | ported: "Merge" |
| `CorrWithMethod` | same | ported: "Correlation with another table" (`ops/stats.py`); legacy module deleted |
| `MergeMethod` (pd.merge) | `methods/pandas/pandasmethods.py` | ported: "Merge" |
| `GetDummiesMethod` | same | planned (phase 4, §2 `to_dummies`) |
| `ConcatMethod`, `PivotTableMethod`, `CrossTabMethod` | same | ported: "Concatenate" (`ops/combine.py`), "Pivot table", "Frequency table" (`ops/reshape.py`) |
| `CutMethod` | same | ported: "Bin values" (`ops/stats.py`) |
| Series filter: `IsInMethod`, `IsNaMethod` | `methods/pandas/seriesmethods.py` | ported: "Filter by values" (`ops/rows.py`), "Rows with missing values" (`ops/missing.py`); legacy module deleted |
| Strings: upper, lower, capitalize, slice, contains, extract, match, replace, repeat, split (10) | `methods/pandas/stringmethods.py` | ported (`ops/strings.py`): "Change case" (upper / lower / capitalize / title / swapcase / casefold), "Slice text", "Test text" (contains / match / fullmatch / startswith / endswith -> bool column), "Filter rows by text", "Extract with regular expression", "Replace text", "Repeat text", "Split text into columns"; new: "Strip text", "Pad text", "Text length"; legacy module deleted |
| pandastools: tolerance bands | `methods/pandastools/dataframept.py` | ported: "Tolerance bands" (rolling min / max + `clip`, `ops/timeseries.py`) |
| pandastools: merge columns, duplicate features | same | ported: "Combine columns", "Duplicate columns" (`ops/columns.py`) |
| pandastools: split, uniquify columns | same | planned (phase 4, §2): split adds split-info columns for the split dialog (no op design yet); uniquify: engine column names are unique strings (readers dedupe), needed only with an import that allows duplicates |
| pandastools: index to seconds, detect gaps, detect time gaps | `methods/pandastools/indexpt.py` | ported on columns: "Seconds since start", "Number segments between gaps" (time or numeric column) (`ops/timeseries.py`); legacy module deleted |
| pandastools: float year to datetime | `methods/pandastools/seriespt.py` | ported: "Decimal year to date / time" (`ops/dates.py`); legacy module deleted |
| Arbitrary code step | (code in recipes) | ported: "Custom code" (`ops/code.py`) |


## 9. Plugins (48 at `pre-rework`; `plugins/`)

| Plugin | What | Status |
|---|---|---|
| `reader_csv` | CSV / TSV / TXT with dialog: encoding detection, delimiter / header sniffing, NA value, preview | ported: `ReadCsv` (`ops/sources.py`) + reader dialog preview; sniffing / NA open (O14) |
| `reader_excel` | `.xls`, `.xlsx`, `.xlsm`, `.xlsb`, `.ods` | ported: `ReadExcel` (`.xlsx` / `.xlsm`, `excel` extra); other formats open (O14) |
| `reader_parquet` | Parquet | ported: `ReadParquet` |
| `reader_feather` | Feather | ported: `ReadFeather` (+ Arrow IPC) |
| `reader_clipboard` | clipboard table | ported: `ReadClipboard` |
| `reader_sqlite` | every table of a DB as a dataset | ported: `ReadSqlite` (one query); all-tables import open (O14) |
| `reader_recipe` | `.recipe` files | ported differently: `.datacookrecipe` (JSON, versioned, `engine/recipes.py`) via "Import recipe file…" or the command line -> library; old code-based `.recipe` files are not read |
| `reader_seaborn` | seaborn sample datasets (table dialog) | open (O15) |
| `reader_iba_dat` | iba process-value format | backlog (§0; iba via `ibadatfile` plugin) |
| `reader_mdf`, `reader_tdms`, `reader_gdx`, `reader_stata`, `reader_r`, `reader_hdf`, `reader_pdf`, `reader_website`, `reader_madx`, `reader_xdi`, `reader_px` | further formats (11) | backlog (§0) |
| `reader_pydataset`, `reader_openml`, `reader_vega_datasets` | dataset collections (3) | backlog (§0) |
| `export_csv` | CSV (sep, decimal, index, header, NA rep) | ported: `WriteCsv` (`engine/formats.py`); header / NA rep open (O14) |
| `export_parquet` | Parquet | ported: `WriteParquet` |
| `export_recipe` | `.recipe` | ported: Recipes dock "Export…" (`.datacookrecipe`) |
| `export_hdf`, `export_html`, `export_notebook`, `export_pantab` | further exporters (4) | backlog (§0) |
| `datacook_sklearn_plugin` | KMeans, MiniBatchKMeans, spectral, agglomerative, spectral biclustering, PCA, IncrementalPCA, IsolationForest, LinearRegression, MLPClassifier, SimpleImputer, polynomial features, quantile transformer, decision tree | ported partly: scalers / transformers (StandardScaler, MinMaxScaler, RobustScaler, MaxAbsScaler, Normalizer, PowerTransformer, QuantileTransformer), PCA, KMeans / DBSCAN, plus `ApplyModel` (fit on another table and transform / predict) (`ops/estimators.py`, `sklearn` extra); supervised models planned (WP4.8 part 2) |
| `datacook_lightgbm_plugin`, `datacook_xgboost_plugin` | boosted-tree estimators | planned (phase 5, decide when porting; §4: via generic estimator op) |
| `datacook_scipy_plugin` | Levene test, Mann-Whitney U, FFT, distribution parameter fit (+ KS test) | planned (phase 5, decide when porting) |
| `datacook_scipy_plugin` | Arff file reader | open (O15) |
| `action_statsmodels` | linear regression dialog | planned (phase 5, decide when porting) |
| `datacook_qtcharts_plugin` | time-series plot (QtCharts) with series dialog | planned (phase 5, decide when porting) |
| `contextmenu_seaborn` | dist plot, heatmap | planned (WP5.1 plots) |
| `action_matplotlib` (disabled) | reg / box / swarm / resid plots, radviz | planned (WP5.1 plots) |
| `action_scattermatrix` (disabled) | scatter matrix | planned (WP5.1 plots) |
| `dock_ipython` | IPython console dock, push dataset to console, console variable -> dataset | planned (WP5.1) |
| `dock_ipython_mp` | multiprocessing console variant | planned (phase 5, decide when porting; §4 lists it as cut) |
| `action_openinexcel` | open dataset in Excel (Windows) | planned (phase 5, decide when porting; §4 lists it as cut) |
| `dtw_dtaidistance`, `dtw_fastdtw` | DTW comparers (used only by `processvalues`) | dropped (§0 processvalues; §4 cut list) |
| `codeviewer_pyqode`, `codeviewer_qscintilla` | code viewers | dropped (§0) |
| `datacook_sentry_plugin` | error reporting | dropped (§0) |
| Plugin system: `manifest.yaml` folders, plugin manager, plugin types (reader, exporter, dock, sidebar, context menu, DTW) | `core/pluginmanager.py`, `core/appmanager.py`, `plugintypes/` | ported partly: entry-point registry for ops and writers (`engine/registry.py`); UI plugins planned (WP5.1) |

## 10. Other

| Feature | Old | Status |
|---|---|---|
| `processvalues` (process value analysis), signal types dialog | `processvalues/`, `gui/dialogs/signaltypesdialog.py` | dropped (§0) |
| Background worker pool | `core/threads.py` | ported: `app/jobs.py` `JobRunner` + engine executor |
| Global signal bus | `core/signals.py` | ported: `SessionBridge` + `AppState` (`app/bridge.py`, `app/state.py`) |
| Parameter dialogs generated from method signatures | `gui/paramstogui.py`, prettyqt `custom_widgets.dataset` | ported: prettyqt `PydanticForm` in the Parameters dock with live preview (`docks/params.py`) |
| Old table viewers | `gui/viewer.py`, `gui/viewer2.py` | ported: cutepandas `DataFrameViewer` (§5 "delete") |
| Dtype icons, colour generator | `util/icons.py`, `util/colorgenerator.py` | ported: cutepandas (`utils/icons.py`, `delegates/valuecolordelegate.py`) |
