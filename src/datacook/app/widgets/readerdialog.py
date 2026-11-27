"""Reader dialog: a reader op's Params form plus a preview of the first rows.

The preview runs in the app's "reader-preview" job slot (`request_evaluate` of the reader
record without parents, `head=preview_rows`), so only a head is held and a newer form value
cancels the running preview. On OK, `record()` is the reader `OpRecord` to add as a root.
"""

from typing import TYPE_CHECKING

from cutepandas.pandaswidgets import DataFrameViewer
from prettyqt import custom_widgets
from prettyqt.qt import QtWidgets

from datacook import i18n
from datacook.app import style
from datacook.app.widgets.columnchooser import form_factories
from datacook.engine import Cancelled, OpRecord
from datacook.i18n import _


if TYPE_CHECKING:
    from datacook.app.controllers import AppController
    from datacook.app.protocols import RequestLike
    from datacook.engine import Op, Params


SLOT = "reader-preview"


class ReaderDialog(QtWidgets.QDialog):
    def __init__(
        self,
        app: AppController,
        op: type[Op],
        path: str | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.app = app
        self.op = op
        self.setObjectName("reader-dialog")
        self.setWindowTitle(str(_("Open data: {title}")).format(title=op.title))
        self.resize(900, 600)
        self.form = custom_widgets.PydanticForm(
            op.Params,
            debounce_ms=app.state.settings.preview_debounce_ms,
            widget_factories=form_factories(lambda _i: [], getattr(op, "extensions", ())),
            translate=i18n.translate,
        )
        if isinstance(form_layout := self.form.layout(), QtWidgets.QFormLayout):
            form_layout.setContentsMargins(0, 4, 8, 4)
            form_layout.setVerticalSpacing(8)
            form_layout.setHorizontalSpacing(10)
            form_layout.setFieldGrowthPolicy(
                QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
            )
        if path is not None and "path" in op.Params.model_fields:
            self.form.set_raw_value({"path": path})
        form_scroll = QtWidgets.QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        form_container = QtWidgets.QWidget()
        form_box = QtWidgets.QVBoxLayout(form_container)
        form_box.setContentsMargins(0, 0, 0, 0)
        form_box.addWidget(self.form)
        form_box.addStretch(1)
        form_scroll.setWidget(form_container)
        self.viewer = DataFrameViewer(sortable=False)
        self.status = QtWidgets.QLabel()
        self.status.setObjectName("reader-status")
        self.status.setWordWrap(True)
        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(form_scroll)
        splitter.addWidget(self.viewer)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([310, 590])
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)
        self._params: Params | None = None
        self.form.value_changed.connect(self._preview)
        self.form.errors_changed.connect(self._on_errors)
        self.finished.connect(self.stop)
        if (params := self.form.get_value()) is not None:
            self._preview(params)
        else:
            self._on_errors(self.form.get_errors())

    def params(self) -> Params | None:
        return self.form.get_value()

    def record(self) -> OpRecord | None:
        params = self.params()
        return OpRecord(self.op.id, params) if params is not None else None

    # --- preview -----------------------------------------------------------------------
    def _preview(self, params: Params) -> None:
        if params == self._params:
            return
        self._params = params
        self.status.setProperty("error", False)
        style.repolish(self.status)
        self.status.setText(str(_("Reading preview…")))
        self._ok_enabled(True)
        rows = self.app.state.settings.preview_rows
        record = OpRecord(self.op.id, params)
        self.app.jobs.request_evaluate(SLOT, record, (), self._on_done, head=rows)

    def _on_done(self, req: RequestLike) -> None:
        try:
            head = req.result()
        except Cancelled:
            return
        except Exception as e:  # noqa: BLE001 - shown in the dialog
            self.viewer.holder.set_df(None)
            self.status.setProperty("error", True)
            style.repolish(self.status)
            self.status.setText(str(_("Cannot read: {error}")).format(error=e))
            return
        self.viewer.holder.set_df(head)
        self.status.setProperty("error", False)
        style.repolish(self.status)
        text = str(_("Preview: first {rows} rows, {cols} columns"))
        self.status.setText(text.format(rows=len(head), cols=len(head.columns)))

    def _on_errors(self, errors: dict[str, str]) -> None:
        self._ok_enabled(not errors)
        if errors:
            self._params = None
            self.app.jobs.cancel(SLOT)

    def _ok_enabled(self, enabled: bool) -> None:
        self.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(enabled)

    def stop(self, _result: int = 0) -> None:
        """Cancel a running preview and drop the shown head."""
        self.app.jobs.cancel(SLOT)
        self.viewer.holder.set_df(None)

    def accept(self) -> None:
        if self.params() is not None:
            super().accept()
