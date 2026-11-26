## v2.12.0 (2020-07-24)

### Feat

- also save current name when saving project
- some type columns for EstimatorsModel

### Fix

- only allow dragdrop import for datasets for now
- **BaseListMixin**: insert at correct position

### Refactor

- move more stuff to basehistoryitemtree

## v2.11.2 (2020-07-23)

### Fix

- another installer fix: disable custom statsmodels stuff

## v2.11.1 (2020-07-23)

### Refactor

- add basehistoryitemtree

### Fix

- fix tests

## v2.11.0 (2020-07-23)

### Fix

- **DataSet**: cast __getitem__ results to DataSet

### Feat

- add version CLI option
- add PureEvalIntegration to sentry addon

### Refactor

- set_context method for baseaction

## v2.10.1 (2020-07-21)

### Fix

- fix build by pinning matplotlib to v3.2.2

## v2.10.0 (2020-07-21)

### Refactor

- **Dataset**: wrap __getattr__ results to return DataSet instead of DataFrame
- rem theme support, include fixed dark theme
- improve Exception handling

### Feat

- **Sklearn**: add Pipeline estimator

### Fix

- **FilterActions**: use corresponding method classes

## v2.9.3 (2020-07-20)

### Refactor

- correct implementation for SerializeMixin.load_from_file
- supply path for tree save methods via keyword argument

### Fix

- correct from_json implementation for historymixin.from_json

## v2.9.2 (2020-07-19)

### Fix

- add missing popup info when adding estimator

## v2.9.1 (2020-07-19)

### Fix

- **HistoryMixin**: fix logging for merges without history
- **DataSet**: correct init of DataSet with data of another dataset
- **DatasetMethod**: add missing log call placeholder
- **DatasetMethod**: correctly apply to partial
- fix stringmethods.SplitMethod
- HistoryMixin.copy() shouldnt be a classmethod

## v2.9.0 (2020-07-19)

### Feat

- **Estimators**: add "Import from code" action

### Refactor

- streamline dataset / estimator: move from_script / apply_script to historymixin
- build_from_dict -> from_dict
- streamline dataset / estimator
- streamline dataset / estimator: move build_from_dict to historymixin
- streamline dataset / estimator: move as_json to historymixin
- streamline dataset / estimator
- dataset rework
- use metadata for populating HistoryTree
- use dict for metadata
- __getattribute__ --> __getattr__
- allow correct migration to newer versions
- get rid of different history classes for estimators and datasets
- add HistoryMixin

### Fix

- correct enabled state for MergeAction right_on param
- pre-configured DataItems didnt accept unknown keyword arguments
- qicons for tables
- show correct dtypes for dtypedelegate

### Perf

- use cached get_icon method from prettyqt

## v2.8.0 (2020-07-16)

### Refactor

- add and use AsType dataset method
- rework themes integration
- add and load custom font "Roboto"
- add MainApp class
- streamline estimator / dataset

### Fix

- dont use loc accessor for method calling
- wrong type for threads exception signal
- fix float64 dtype conversion
- correctly update estimator historytree

### Feat

- User setting for app style
- allow registering filetypes
- allow opening files by passing as argument

## v2.7.0 (2020-07-13)

### Refactor

- move settings to dialog
- adapt to prettyqt SelectionWidget change
- **SettingsPage**: new Settings layout
- **SettingsPage**: cleanup options initialization
- move reader validity check to FileReaderPlugin

### Fix

- **SettingsPage**: set window icons correctly

### Feat

- **FileReaders**: read first bytes from files for proper Reader selection

## v2.6.0 (2020-07-12)

### Feat

- **EstimatorsPage**: show tags
- Recipespage: allow resizing of areas by user
- add Preview Textbox to Recipes page
- enforce commit msg style

### Fix

- missing MergeActions in DatasetTree
- also reset QSettings when --reset is used.
- get rid of FullScreen flicker
- correctly load window state on startup
- Fixed an issue which led to Keyboard shortcuts not working correctly
- correct some model return values for invalid indexes
- use correct type for history.cmds in collapse_children
- dataset missing name after applying method
- baseaction: re-add callableAction
- requirements.txt to reduce vulnerabilities
- emit settings_updated signal at very end of __init__
- dont use self.widget for BaseAction
- LinRegression instead of LinModel

### Refactor

- cleanup QScintilla Plugin
- adjust to PrettyQt syntaxhighlighter changes
- SyntaxHighlighting for regex method kwargs
- **SettingsPage**: get rid of "Reload plugins" button
- always show recent lists
- ...and more reshuffling
- move more stuff out of mainwindow, allow pages to live separately
- move more stuff out of mainmenu
- only load sentry when application is packed into executable
- cleanup ThreadPool class
- more mainmenu cleanup
- move stuff out of mainwindow
- correctly shut down attached servers / processes
- AppManager.get_estimators: allow multiple types
- use yaml.full_load instead of yaml.load in pluginmanager to get rid of warning
- dont check license if app not frozen
- cleanup kwargs passing for basenesteditem / history
- some changes to sklearn-api related methods
- change way estimators get collected
