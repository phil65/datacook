"""Overlay: a translucent message panel with optional buttons over another widget.

Used by the data view for slot states other than "ready" ("computing…", "recomputing…",
"Not in memory — Recompute", errors). The overlay follows its parent's size.
"""

from typing import TYPE_CHECKING

from prettyqt.qt import QtCore, QtWidgets

from datacook.app import style


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class Overlay(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.setObjectName("overlay")
        self.setAutoFillBackground(False)
        self.panel = QtWidgets.QFrame(self)
        self.panel.setObjectName("overlay-panel")
        self.panel.setMinimumWidth(260)
        self.panel.setMaximumWidth(440)
        self.title = QtWidgets.QLabel(self.panel)
        self.title.setObjectName("overlay-title")
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        self.title.setWordWrap(True)
        self.title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.detail = QtWidgets.QLabel(self.panel)
        self.detail.setObjectName("overlay-detail")
        self.detail.setWordWrap(True)
        self.detail.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.detail.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self._buttons = QtWidgets.QHBoxLayout()
        self._buttons.setSpacing(8)
        self._buttons.addStretch()
        self._buttons.addStretch()
        panel_layout = QtWidgets.QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(24, 20, 24, 20)
        panel_layout.setSpacing(8)
        panel_layout.addWidget(self.title)
        panel_layout.addWidget(self.detail)
        panel_layout.addLayout(self._buttons)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addStretch()
        row = QtWidgets.QHBoxLayout()
        row.addStretch()
        row.addWidget(self.panel)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        self.buttons: list[QtWidgets.QPushButton] = []
        parent.installEventFilter(self)
        self.hide()

    def show_message(
        self,
        title: str,
        detail: str = "",
        buttons: Sequence[tuple[str, Callable[[], object]]] = (),
        *,
        kind: str = "info",
    ) -> None:
        self.panel.setProperty("kind", kind)
        style.repolish(self.panel)
        style.repolish(self.title)
        self.title.setText(title)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        for button in self.buttons:
            self._buttons.removeWidget(button)
            button.deleteLater()
        self.buttons = []
        for text, slot in buttons:
            button = QtWidgets.QPushButton(text, self.panel)
            button.clicked.connect(lambda _checked=False, fn=slot: fn())
            self._buttons.insertWidget(self._buttons.count() - 1, button)
            self.buttons.append(button)
        self._fit()
        self.show()
        self.raise_()

    def button(self, text: str) -> QtWidgets.QPushButton | None:
        return next((b for b in self.buttons if b.text() == text), None)

    def _fit(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        if watched is self.parentWidget() and event.type() == QtCore.QEvent.Type.Resize:
            self._fit()
        return False
