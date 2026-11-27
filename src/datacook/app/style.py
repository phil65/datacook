"""Palette-aware application styling and bundled monospace font loader.

Uses Qt `palette(...)` references throughout so the styling adapts naturally to both
light and dark system palettes without hardcoding a single theme.
"""

import pathlib
from typing import TYPE_CHECKING

from prettyqt.qt import QtGui


if TYPE_CHECKING:
    from prettyqt.qt import QtWidgets


_MONO_FAMILY: str | None = None
_FONT_LOADED = False

_FONT_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "resources" / "fonts" / ("RobotoMono-Regular.ttf")
)

STYLESHEET = """
/* --- Main window & dock chrome ---------------------------------------------------- */
QMainWindow::separator {
    width: 4px;
    height: 4px;
    background: palette(window);
}
QMainWindow::separator:hover {
    background: palette(highlight);
}

QDockWidget::title {
    text-align: left;
    padding: 5px 8px;
    background: palette(window);
    border-bottom: 1px solid palette(midlight);
    font-weight: 600;
}

/* Tabified dock tab bars */
QMainWindow > QTabBar::tab {
    padding: 5px 12px;
    margin-right: 1px;
    background: palette(window);
    border: 1px solid transparent;
    border-top: 2px solid transparent;
    color: palette(window-text);
}
QMainWindow > QTabBar::tab:selected {
    background: palette(base);
    border-color: palette(midlight);
    border-top: 2px solid palette(highlight);
    font-weight: 600;
}
QMainWindow > QTabBar::tab:hover:!selected {
    background: palette(alternate-base);
}

/* Remove double borders on top-level views directly inside docks */
QTreeView#node-tree,
QTableView#schema-table,
QTableView#category-table,
QTableView#message-list,
QListWidget#recipe-list,
QTextBrowser#recipe-details,
QPlainTextEdit#code-editor {
    border: none;
}

/* Splitters */
QSplitter::handle {
    background: palette(midlight);
}
QSplitter::handle:horizontal {
    width: 3px;
}
QSplitter::handle:vertical {
    height: 3px;
}
QSplitter::handle:hover {
    background: palette(highlight);
}

/* --- Headers & item views --------------------------------------------------------- */
QHeaderView::section {
    background: palette(window);
    color: palette(window-text);
    padding: 4px 8px;
    border: none;
    border-bottom: 1px solid palette(midlight);
    border-right: 1px solid palette(midlight);
    font-weight: 600;
}
QHeaderView::section:last {
    border-right: none;
}

QTreeView#node-tree::item {
    padding: 3px 4px;
}
QListWidget#recipe-list::item {
    padding: 5px 8px;
}

/* --- Controls --------------------------------------------------------------------- */
QPushButton {
    padding: 4px 12px;
    border: 1px solid palette(mid);
    border-radius: 4px;
    background: palette(button);
    min-height: 20px;
}
QPushButton:hover:!disabled {
    border-color: palette(highlight);
}
QPushButton:disabled {
    opacity: 0.55;
}
QPushButton[primary="true"]:enabled {
    background: palette(highlight);
    color: palette(highlighted-text);
    border-color: palette(highlight);
    font-weight: 600;
}
QPushButton[primary="true"]:hover:enabled {
    border-color: palette(text);
}

QLineEdit {
    padding: 3px 6px;
    border: 1px solid palette(mid);
    border-radius: 4px;
    background: palette(base);
    min-height: 20px;
}
QLineEdit:focus {
    border: 1px solid palette(highlight);
}
QComboBox, QSpinBox, QDoubleSpinBox {
    min-height: 22px;
}

/* --- DataView banner -------------------------------------------------------------- */
QLabel#dataview-banner {
    background: rgba(38, 139, 210, 26);
    border-bottom: 1px solid rgba(38, 139, 210, 80);
    padding: 5px 10px;
    font-weight: 600;
}

/* --- Overlay ---------------------------------------------------------------------- */
QFrame#overlay {
    background: rgba(127, 127, 127, 36);
}
QFrame#overlay-panel {
    background: palette(window);
    border: 1px solid palette(mid);
    border-radius: 8px;
}
QFrame#overlay-panel[kind="error"] {
    border: 1px solid rgba(220, 50, 47, 150);
}
QLabel#overlay-title {
    font-size: 11pt;
    font-weight: 600;
}
QFrame#overlay-panel[kind="error"] QLabel#overlay-title {
    color: #c92a2a;
}
QLabel#overlay-detail {
    color: palette(placeholder-text);
}

/* --- Params dock ------------------------------------------------------------------ */
QLabel#params-title {
    font-size: 10.5pt;
    font-weight: 600;
}
QLabel#params-description,
QLabel#params-placeholder,
QLabel#params-status,
QLabel#column-profile-hint {
    color: palette(placeholder-text);
}
QLabel#params-status[error="true"],
QLabel#reader-status[error="true"] {
    color: #c92a2a;
}
QFrame#params-divider {
    color: palette(midlight);
}

/* --- Schema dock ------------------------------------------------------------------ */
QLabel#schema-section-label {
    font-weight: 600;
    padding: 6px 6px 2px 6px;
}

/* --- Status bar & memory indicator ------------------------------------------------ */
QStatusBar {
    border-top: 1px solid palette(midlight);
    padding: 1px 4px;
}
QStatusBar::item {
    border: none;
}
QToolButton#memory-indicator {
    padding: 2px 18px 2px 8px;
    border: 1px solid transparent;
    border-radius: 4px;
}
QToolButton#memory-indicator:hover {
    background: palette(alternate-base);
    border-color: palette(midlight);
}
QToolButton#memory-indicator::menu-indicator {
    subcontrol-position: right center;
    right: 5px;
    width: 8px;
}
QToolButton#memory-indicator[overBudget="true"] {
    color: #c92a2a;
    font-weight: 600;
}

/* --- Command palette -------------------------------------------------------------- */
QWidget#op-palette {
    background: palette(window);
    border: 1px solid palette(mid);
    border-radius: 8px;
}
QWidget#op-palette QLineEdit {
    padding: 6px 10px;
    font-size: 10pt;
}
QWidget#op-palette QTableView {
    border: none;
    background: palette(base);
    border-radius: 4px;
}
"""


def mono_font(point_size: int = 10) -> QtGui.QFont:
    """Return the bundled Roboto Mono font (loaded once), falling back to system FixedFont."""
    global _FONT_LOADED, _MONO_FAMILY
    if not _FONT_LOADED:
        _FONT_LOADED = True
        if _FONT_PATH.is_file():
            font_id = QtGui.QFontDatabase.addApplicationFont(str(_FONT_PATH))
            if font_id >= 0:
                families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    _MONO_FAMILY = families[0]
    if _MONO_FAMILY:
        font = QtGui.QFont(_MONO_FAMILY, point_size)
    else:
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(point_size)
    return font


def repolish(widget: QtWidgets.QWidget) -> None:
    """Re-apply stylesheet rules after toggling a dynamic Qt property."""
    qstyle = widget.style()
    if qstyle is not None:
        qstyle.unpolish(widget)
        qstyle.polish(widget)
    widget.update()


def apply(window: QtWidgets.QWidget) -> None:
    """Install DataCook's palette-aware stylesheet on `window`."""
    window.setStyleSheet(STYLESHEET)
