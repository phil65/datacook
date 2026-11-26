"""Params dock: a `PydanticForm` for the op of the open preview, live preview, Apply / Cancel.

Follows `AppState.preview` (design §3 "Edit params with live preview, then commit"):

- a new `PreviewSpec` (other op, mode, target or inputs) rebuilds the form from the op's
  `Params` (edit mode: loaded with the step's params; add mode: defaults, and if they are
  valid the preview starts at once);
- the form's debounced `value_changed` goes to `app.preview.set_params()`, invalid input
  (`errors_changed`) to `set_params(None)`;
- params changed from outside (undo of the edited step, code edits) are loaded into the form;
- column fields (`"widget": "column" | "columns" | "column_map"`, `"input": n`) offer the
  columns of input `n` from `session.summary()` and refresh when that input is computed;
- required time-column fields (`"role": "time"`) of a new step start with the input's time
  column (`engine.timecol.time_column()`).

Apply (edit) / Add = `app.preview.commit()`, Cancel = `app.preview.cancel()`.
"""

from typing import TYPE_CHECKING

from prettyqt import custom_widgets
from prettyqt.qt import QtCore, QtWidgets

from datacook import i18n
from datacook.app.uimodules import DockSpec
from datacook.app.widgets.columnchooser import form_factories
from datacook.engine import timecol
from datacook.i18n import _


if TYPE_CHECKING:
    from datacook.app.controllers import AppController
    from datacook.app.mainwindow import MainWindow
    from datacook.app.state import PreviewSpec
    from datacook.engine import Op, Params


def _spec_key(spec: PreviewSpec) -> tuple[object, ...]:
    return (spec.mode, spec.op_id, spec.target, spec.inputs)


class ParamsPanel(QtWidgets.QWidget):
    """The params dock widget (one form at a time; rebuilt per preview)."""

    def __init__(self, app: AppController, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self.form: custom_widgets.PydanticForm | None = None
        self.op: type[Op] | None = None
        self._key: tuple[object, ...] | None = None
        self._column_editors: list[QtWidgets.QWidget] = []
        self._emitted: Params | None = None
        """The params last sent to the preview controller (or loaded from it)."""

        layout = QtWidgets.QVBoxLayout(self)
        self.title_label = QtWidgets.QLabel()
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        self.description_label = QtWidgets.QLabel()
        self.description_label.setWordWrap(True)
        self.placeholder = QtWidgets.QLabel()
        self.placeholder.setWordWrap(True)
        self.placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        self.apply_button = QtWidgets.QPushButton()
        self.apply_button.setObjectName("params-apply")
        self.apply_button.setDefault(True)
        self.cancel_button = QtWidgets.QPushButton()
        self.cancel_button.setObjectName("params-cancel")
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.apply_button)
        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)
        layout.addWidget(self.placeholder, 1)
        layout.addWidget(self.scroll_area, 1)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)

        self.apply_button.clicked.connect(self.apply)
        self.cancel_button.clicked.connect(self.cancel)
        app.state.preview_changed.connect(self._on_preview_changed)
        app.state.language_changed.connect(self.retranslate)
        app.preview.slot.state_changed.connect(self._update_status)
        app.bridge.nodes_materialized.connect(self._on_materialized)
        app.bridge.structure_reset.connect(self._refresh_columns)
        self.retranslate()
        self._on_preview_changed(app.state.preview)

    # --- public ------------------------------------------------------------------------
    def apply(self) -> str | None:
        """Commit the preview (Add / Apply); the form's current input counts."""
        if self.form is None or self.app.preview.spec is None:
            return None
        params = self.form.get_value()
        if params is None:
            return None
        self._send(params)
        return self.app.preview.commit()

    def cancel(self) -> None:
        self.app.preview.cancel()

    def columns(self, index: int) -> list[str]:
        """Column names of input `index` of the open preview (empty if not computed)."""
        spec = self.app.state.preview
        if spec is None or index >= len(spec.inputs):
            return []
        summary = self.app.session.summary(spec.inputs[index])
        return [c.name for c in summary.columns] if summary is not None else []

    def retranslate(self, _language: object = None) -> None:
        self.apply_button.setText(str(_("Apply")))
        self.cancel_button.setText(str(_("Cancel")))
        self.placeholder.setText(
            str(_("Choose an operation from the Steps menu or the palette (Ctrl+Shift+P)."))
        )
        if self.form is not None:
            self.form.retranslate()
        self._update_header()
        self._update_status()

    # --- preview spec ------------------------------------------------------------------
    def _on_preview_changed(self, spec: PreviewSpec | None) -> None:
        if spec is None:
            self._clear()
            return
        if _spec_key(spec) != self._key:
            self._build(spec)
            return
        if spec.params is not None and spec.params != self._emitted and self.form is not None:
            # changed from outside (undo, code): load into the form without re-emitting
            self._emitted = spec.params
            self.form.set_raw_value(spec.params)
            self.form.get_value()  # refresh error labels
        self._update_buttons()

    def _clear(self) -> None:
        self._key = None
        self.op = None
        self._emitted = None
        self._column_editors = []
        if self.form is not None:
            self.form.deleteLater()
            self.form = None
        self.scroll_area.takeWidget()
        self.scroll_area.hide()
        self.placeholder.show()
        self._update_header()
        self._update_status()
        self._update_buttons()

    def _build(self, spec: PreviewSpec) -> None:
        self._clear()
        self._key = _spec_key(spec)
        op = self.app.session.registry.get(spec.op_id)
        self.op = op
        params = spec.params
        if params is None and spec.mode == "edit" and spec.target is not None:
            node = self.app.session.get(spec.target)
            params = node.record.params if node is not None else None
        editors: list[QtWidgets.QWidget] = []
        factories = form_factories(self.columns, getattr(op, "extensions", ()), editors)
        form = custom_widgets.PydanticForm(
            op.Params,
            debounce_ms=self.app.state.settings.preview_debounce_ms,
            widget_factories=factories,
            translate=i18n.translate,
        )
        form.setObjectName("params-form")
        self._column_editors = editors
        if params is not None:
            form.set_raw_value(params)
        elif spec.mode == "add" and spec.inputs:
            self._prefill_time_column(form, op, spec.inputs[0])
        self.form = form
        self.scroll_area.setWidget(form)
        self.placeholder.hide()
        self.scroll_area.show()
        form.value_changed.connect(self._send)
        form.errors_changed.connect(self._on_errors)
        self._update_header()
        self._update_status()
        if params is not None:
            self._emitted = params
            form.get_value()
        elif spec.mode == "add":
            # defaults: preview at once if they are valid
            value = form.get_value()
            if value is not None:
                self._send(value)
        self._update_buttons()

    def _prefill_time_column(
        self, form: custom_widgets.PydanticForm, op: type[Op], input_id: str
    ) -> None:
        """Required time-role fields of a new step start with the input's time column."""
        required = op.Params.model_fields
        fields = [f for f in timecol.time_fields(op.Params) if required[f].is_required()]
        if fields and (column := timecol.time_column(self.app.session, input_id)) is not None:
            form.set_raw_value(dict.fromkeys(fields, column))

    # --- form -> controller -------------------------------------------------------------
    def _send(self, params: Params | None) -> None:
        """To the controller (it skips params it already previews)."""
        self._emitted = params
        self.app.preview.set_params(params)
        self._update_buttons()

    def _on_errors(self, errors: dict[str, str]) -> None:
        if errors:
            self._send(None)
        self._update_buttons()

    # --- columns -----------------------------------------------------------------------
    def _on_materialized(self, ids: tuple[str, ...]) -> None:
        spec = self.app.state.preview
        if spec is not None and set(spec.inputs) & set(ids):
            self._refresh_columns()

    def _refresh_columns(self) -> None:
        for editor in self._column_editors:
            index = editor.property("column_input") or 0
            editor.set_columns(self.columns(int(index)))  # ty: ignore[missing-attribute]

    # --- texts / state -----------------------------------------------------------------
    def _update_header(self) -> None:
        spec = self.app.state.preview
        op = self.op
        if spec is None or op is None:
            self.title_label.setText(str(_("No operation")))
            self.description_label.clear()
            return
        if spec.mode == "edit":
            text = str(_("Edit step: {title}")).format(title=op.title)
        else:
            text = str(_("New step: {title}")).format(title=op.title)
        self.title_label.setText(text)
        self.description_label.setText(str(op.description))
        self.apply_button.setText(str(_("Apply") if spec.mode == "edit" else _("Add")))

    def _update_buttons(self) -> None:
        spec = self.app.state.preview
        valid = self.form is not None and not self.form.get_errors()
        self.apply_button.setEnabled(spec is not None and valid)
        self.cancel_button.setEnabled(spec is not None)

    def _update_status(self, _state: object = None) -> None:
        slot = self.app.preview.slot
        if self.app.state.preview is None:
            self.status_label.clear()
        elif slot.error is not None:
            self.status_label.setText(str(_("Preview failed: {error}")).format(error=slot.error))
        elif slot.message:
            self.status_label.setText(slot.message)
        elif (head := slot.frame) is not None:
            text = str(_("Preview: first {rows} rows, {cols} columns"))
            self.status_label.setText(text.format(rows=len(head), cols=len(head.columns)))
        else:
            self.status_label.clear()


def create(app: AppController, window: MainWindow) -> QtWidgets.QWidget:
    return ParamsPanel(app, window)


DOCKS = (DockSpec("params", _("Parameters"), "right", create),)
