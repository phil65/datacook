# legacy/

Old DataCook code (package `processanalyzer`, app "ProcessAnalyzer") that still has to be
ported in the rework (plan: `DATACOOK_PLAN.md` in the owner's OSS workspace, sections 4-6).
It was moved here with `git mv` in phase 0, so `git log --follow legacy/<path>` shows its
history.

The complete old app, including the GUI deleted in phase 3, is tagged **`pre-rework`**
(`978c73cc`): `git show pre-rework:processanalyzer/<path>` (old history: private archive repo, not in this one). Where each old feature went (or
why not) is tracked in [`docs/feature-inventory.md`](../docs/feature-inventory.md): **check and
update it before deleting anything here.**

**Reference material only.** Nothing here is imported, packaged, linted (`ruff`), type-checked
(`ty`) or collected by pytest. The code does not run: the GUI targets an old prettyqt API, and
imports still say `processanalyzer.*` or the old `datacook.core` / `datacook.methods`. Don't fix it;
port what is needed into the new structure and delete the ported parts.

**Deleted** once the rework has replaced it. Done at the end of phase 3 (2026-11-25, the new
app in `src/datacook/app/`): the old GUI (`gui/`, `models/`, `actions/`, `codeviewer/`,
`mainapp.py`, `__main__.py`), its tests (`tests/test_models.py`, `tests/test_windows.py`),
`core/threads.py` and `logging.yaml`; see the `pre-rework` tag or git history
(`git log --diff-filter=D -- legacy/`) to look at them. Still to go: the op catalogue after phase 4, plugins and plugin types after
phase 5 (plugins and extras), the old docs after phase 7.

## Layout

Paths are relative to the old package root (`processanalyzer/`):

| Path | What | Replaced by (phase) |
|---|---|---|
| `core/appmanager.py`, `core/pluginmanager.py`, `plugintypes/` | `manifest.yaml` plugin discovery, plugin base classes | entry-point registry for data plugins and UI plugins (2, 5) |
| `core/baseaction.py`, `core/signals.py` | action base class, global Qt signal bus (kept: the plugins below use them) | app layer (3, done) |
| `core/estimator.py`, `methods/pandas/estimatormethods.py` | scikit-learn estimator items and their Qt dialogs | generic estimator op (5) |
| `core/project.py` | project (tree of datasets) | engine `Session` / project files (2, done) |
| `core/dataset.py`, `history.py`, `historyitemmixin.py`, `codeblock.py`, `itemclasses.py`, `nesteditem.py`, `serializemixin.py`, `categories.py` | old core (moved in phase 2): `DataSet` proxy, string-template code history | `datacook.engine` (`Node`, `Session`, `codegen`, `parser`) (2, done) |
| `core/config.py`, `config_default.yaml`, `util/helpers.py` | dynaconf settings, helpers of the old core | `datacook.app.settings.AppSettings` (3, done) |
| `methods/` (`methods.py`, `base.py`, `pandas/`, `pandastools/`), `tests/test_shit.py`, `tests/test_helpers.py`, `tests/conftest_core.py` | the old op catalogue (95 methods) and its replay tests | engine ops (4); starter set ported in phase 2 |
| `util/icons.py`, `util/colorgenerator.py`, `util/debug.py` | dtype icons, colour generator, debug decorators | cutepandas / delete (1) |
| `plugins/` | 45 plugins (readers, exporters, docks, actions, estimators) | format registry + entry-point plugins (2, 5) |
| `docs/` | old MkDocs user docs with screenshots | new user docs (7) |

## Readers and exporters

Phase 2 starts with the basic formats as a **format registry** (extension -> function + Params
model + optional extra): read CSV, Parquet, Excel, JSON, Feather/Arrow, clipboard, SQLite;
write CSV, Parquet, Excel. Matching plugins here: `reader_csv`, `reader_parquet`,
`reader_excel`, `reader_feather`, `reader_clipboard`, `reader_sqlite`, `export_csv`,
`export_parquet`. Also to port: `reader_recipe` / `export_recipe` (project / op list),
`reader_seaborn` (sample datasets).

**Backlog** (owner decision, not before the basic set works):

- `reader_iba_dat` (as a plugin via the owner's `ibadatfile`)
- `reader_mdf`, `reader_tdms`, `reader_gdx`, `reader_stata`, `reader_r`, `reader_hdf`,
  `reader_pdf` (tabula), `reader_website`, `reader_madx`, `reader_xdi`, `reader_px`
- dataset collections: `reader_pydataset`, `reader_openml`, `reader_vega_datasets`
- further exporters: `export_hdf`, `export_html`, `export_notebook`, `export_pantab`

Other plugins (decide when porting, phase 5): `datacook_sklearn_plugin`, `datacook_scipy_plugin`,
`datacook_lightgbm_plugin`, `datacook_xgboost_plugin`, `dtw_dtaidistance`, `dtw_fastdtw`,
`datacook_qtcharts_plugin`, `action_matplotlib`, `action_scattermatrix`, `action_statsmodels`,
`contextmenu_seaborn`, `dock_ipython`, `dock_ipython_mp`, `action_openinexcel` (Windows only).

Optional dependencies these plugins used (the old `extras` extra): chardet, dtaidistance,
fastdtw, fastparquet, gdxpds/gdxcc, beautifulsoup4, html5lib, ipykernel/qtconsole/jupyter-client,
lightgbm, xgboost, mdfreader, nbconvert/nbformat, npTDMS, openml, pandas_datareader, pyaxis,
pydataset, pyreadr, pyreadstat, sqlalchemy, statsmodels, vega-datasets, xdi_pandas, xlrd,
pantab, pyxlsb, odfpy, pywin32, ibadatfile, openpyxl, tabula-py, simplification, tables,
scikit-learn, scipy, matplotlib, seaborn, bidict, decli.
