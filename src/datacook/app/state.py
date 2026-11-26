"""AppState: what the user is looking at (GUI thread only).

The `Session` is the truth for data; `AppState` is the truth for the view: the current node,
the selected column, an open params preview, what the data view shows, the display sort and
the settings. Docks write it (`state.current = id`) and react to its signals; the
controllers do the rest (pins, requests, preview jobs). Setters emit only on a real change.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from prettyqt.qt import QtCore

from datacook.app.settings import AppSettings


if TYPE_CHECKING:
    from datacook.engine import Params


type Display = Literal["node", "preview"]


@dataclass(frozen=True, slots=True)
class PreviewSpec:
    """An open params form with live preview.

    `mode="add"`: a new step of `op_id` on `inputs` (normally `(target,)`); `mode="edit"`:
    new params for the existing node `target` (inputs = its parents). `params=None` until
    the form has valid values.
    """

    mode: Literal["add", "edit"]
    op_id: str
    target: str | None
    inputs: tuple[str, ...]
    params: Params | None = None


@dataclass(frozen=True, slots=True)
class SortSpec:
    """Display-only sort of the data view (design §12.1): not part of the tree or script."""

    column: str
    descending: bool = False


class AppState(QtCore.QObject):
    current_changed = QtCore.Signal(object, object)
    """(old, new) node id or None."""
    column_changed = QtCore.Signal(object)
    preview_changed = QtCore.Signal(object)
    """PreviewSpec or None."""
    display_changed = QtCore.Signal(str)
    sort_changed = QtCore.Signal(object)
    """SortSpec or None."""
    settings_changed = QtCore.Signal(object)
    """(AppSettings) the new settings."""
    language_changed = QtCore.Signal(object)
    """Language code or None; docks `retranslate()` on it."""

    def __init__(self, settings: AppSettings | None = None, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._current: str | None = None
        self._column: str | None = None
        self._preview: PreviewSpec | None = None
        self._display: Display = "node"
        self._sort: SortSpec | None = None
        self._settings = settings or AppSettings()
        self._language: str | None = self._settings.language

    @property
    def current(self) -> str | None:
        return self._current

    @current.setter
    def current(self, node_id: str | None) -> None:
        if node_id == self._current:
            return
        old, self._current = self._current, node_id
        self.sort = None  # display sort belongs to the shown frame
        self.current_changed.emit(old, node_id)

    @property
    def column(self) -> str | None:
        return self._column

    @column.setter
    def column(self, column: str | None) -> None:
        if column != self._column:
            self._column = column
            self.column_changed.emit(column)

    @property
    def preview(self) -> PreviewSpec | None:
        return self._preview

    @preview.setter
    def preview(self, spec: PreviewSpec | None) -> None:
        if spec != self._preview:
            self._preview = spec
            self.preview_changed.emit(spec)

    @property
    def display(self) -> Display:
        return self._display

    @display.setter
    def display(self, display: Display) -> None:
        if display != self._display:
            self._display = display
            self.display_changed.emit(display)

    @property
    def sort(self) -> SortSpec | None:
        return self._sort

    @sort.setter
    def sort(self, spec: SortSpec | None) -> None:
        if spec != self._sort:
            self._sort = spec
            self.sort_changed.emit(spec)

    @property
    def settings(self) -> AppSettings:
        return self._settings

    @settings.setter
    def settings(self, settings: AppSettings) -> None:
        if settings != self._settings:
            self._settings = settings
            self.settings_changed.emit(settings)

    def update_settings(self, **changes: object) -> AppSettings:
        """Replace some settings (validated); emits `settings_changed`."""
        new = AppSettings.model_validate({**self._settings.model_dump(), **changes})
        self.settings = new
        return new

    @property
    def language(self) -> str | None:
        return self._language

    @language.setter
    def language(self, language: str | None) -> None:
        if language != self._language:
            self._language = language
            self.language_changed.emit(language)
