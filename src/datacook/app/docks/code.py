"""Code pane (bottom): the generated script of the whole tree, read-only (editable in 3.2).

`CodeController` owns the text and the node line spans (`session.render_code()`): it
re-renders on structure / params / name changes (coalesced to one render per event-loop
turn) and on a language switch (step comments use op titles), highlights the current
node's span (`AppState.current`) without re-rendering, and marks the first line of every
failing step's span (error markers with the message as tooltip).
"""

from typing import TYPE_CHECKING

from prettyqt import custom_widgets
from prettyqt.qt import QtCore, QtGui, QtWidgets

from datacook.app.uimodules import DockSpec
from datacook.i18n import _


if TYPE_CHECKING:
    from datacook.app.controllers import AppController
    from datacook.app.mainwindow import MainWindow


SPAN_COLOR = QtGui.QColor(38, 139, 210, 45)


class CodeController(QtCore.QObject):
    """Keeps a `CodeEditor` in sync with the session (GUI thread)."""

    def __init__(
        self,
        app: AppController,
        editor: custom_widgets.CodeEditor,
        parent: QtCore.QObject | None = None,
    ):
        super().__init__(parent)
        self.app = app
        self.editor = editor
        self.text = ""
        self.spans: dict[str, tuple[int, int]] = {}
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.render)
        bridge = app.bridge
        for signal in (
            bridge.nodes_added,
            bridge.nodes_removed,
            bridge.nodes_changed,
            bridge.nodes_moved,
        ):
            signal.connect(self.schedule)
        bridge.structure_reset.connect(self.schedule)
        bridge.node_error.connect(self._on_error)
        # a new generation (or a successful recompute) may clear an error
        bridge.nodes_invalidated.connect(self._on_results)
        bridge.nodes_materialized.connect(self._on_results)
        app.state.current_changed.connect(self._on_current_changed)
        app.state.language_changed.connect(self.schedule)
        self.render()

    # --- rendering ---------------------------------------------------------------------
    def schedule(self, *_args: object) -> None:
        """Re-render once the current batch of events is handled."""
        self._timer.start()

    def render(self) -> None:
        self._timer.stop()
        script = self.app.session.render_code()
        self.text = script.text if self.app.session.nodes() else ""
        self.spans = dict(script.spans)
        self.editor.set_text(self.text)
        self.update_markers()

    def current_span(self) -> tuple[int, int] | None:
        current = self.app.state.current
        return None if current is None else self.spans.get(current)

    def error_lines(self) -> dict[int, str]:
        """{first line of a failing step's span: message}."""
        lines: dict[int, str] = {}
        for nid, (first, _last) in self.spans.items():
            if (error := self.app.session.error(nid)) is not None:
                lines[first] = f"{type(error).__name__}: {error}"
        return lines

    def update_markers(self) -> None:
        """Error markers plus the current node's span (both are extra selections)."""
        self.editor.set_line_markers(self.error_lines(), kind="error")
        self._highlight_span()

    def _highlight_span(self) -> None:
        selections = [s for s in self.editor.extraSelections() if not _is_span(s)]
        if (span := self.current_span()) is not None:
            doc = self.editor.document()
            first, last = span
            start = doc.findBlockByNumber(first - 1)
            end = doc.findBlockByNumber(last - 1)
            if start.isValid() and end.isValid():
                for number in range(first - 1, last):
                    block = doc.findBlockByNumber(number)
                    selection = QtWidgets.QTextEdit.ExtraSelection()
                    selection.format.setBackground(SPAN_COLOR)
                    selection.format.setProperty(
                        QtGui.QTextFormat.Property.FullWidthSelection, True
                    )
                    selection.format.setProperty(_SPAN_PROPERTY, True)
                    selection.cursor = QtGui.QTextCursor(block)
                    selections.append(selection)
                cursor = QtGui.QTextCursor(end)
                self.editor.setTextCursor(cursor)
                self.editor.ensureCursorVisible()
                self.editor.setTextCursor(QtGui.QTextCursor(start))
                self.editor.ensureCursorVisible()
        self.editor.setExtraSelections(selections)

    # --- signals -----------------------------------------------------------------------
    def _on_current_changed(self, _old: object, _new: object) -> None:
        if self._timer.isActive():
            return  # the pending render highlights the new span
        self._highlight_span()

    def _on_error(self, _nid: str, _exc: object) -> None:
        if not self._timer.isActive():
            self.update_markers()

    def _on_results(self, ids: tuple[str, ...]) -> None:
        if not self._timer.isActive() and any(i in self.spans for i in ids):
            self.update_markers()


_SPAN_PROPERTY = QtGui.QTextFormat.Property.UserProperty + 1


def _is_span(selection: QtWidgets.QTextEdit.ExtraSelection) -> bool:
    return bool(selection.format.property(_SPAN_PROPERTY))


class CodePane(QtWidgets.QWidget):
    def __init__(self, app: AppController, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.editor = custom_widgets.CodeEditor(parent=self)
        self.editor.setObjectName("code-editor")
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.editor)
        self.controller = CodeController(app, self.editor, self)


def create(app: AppController, _window: MainWindow) -> QtWidgets.QWidget:
    return CodePane(app)


DOCKS = (DockSpec("code", _("Code"), "bottom", create),)
