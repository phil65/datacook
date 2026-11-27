r"""Playwright-style Qt UI inspection and screenshot harness for DataCook.

Captures deterministic screenshots of the full app, individual docks, named widgets or
dialogs at arbitrary window sizes, languages and UI states, and optionally dumps a widget
geometry / layout-diagnostic tree.

Examples:
    # Run the full curated visual suite (writes PNGs + manifest.json)
    uv run python tools/ui_inspect.py --scenario all --out /tmp/dc-ui

    # Capture a single state at a compact size and inspect specific docks
    uv run python tools/ui_inspect.py --scenario demo --size 1280x800 \
        --target window,nodetree,dataview,code --out /tmp/dc-ui

    # Check German layout and dump widget tree + diagnostics
    uv run python tools/ui_inspect.py --scenario edit --lang de --tree --out /tmp/dc-ui
"""

import argparse
from dataclasses import asdict, dataclass
import json
import os
import pathlib
import sys
import tempfile
import time
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from prettyqt.qt import QtWidgets

    from datacook.app.mainwindow import MainWindow


DEFAULT_SIZE = "1400x900"
SETTLE_TIMEOUT_MS = 10_000


@dataclass(frozen=True, slots=True)
class CaptureInfo:
    scenario: str
    target: str
    path: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class LayoutWarning:
    widget: str
    kind: str
    detail: str


def _parse_size(spec: str) -> tuple[int, int]:
    w_str, sep, h_str = spec.lower().partition("x")
    if not sep:
        msg = f"invalid size {spec!r}, expected WxH (e.g. 1400x900)"
        raise argparse.ArgumentTypeError(msg)
    return int(w_str), int(h_str)


def _ensure_offscreen(*, gui: bool) -> None:
    if not gui and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"


def _pump(qapp: QtWidgets.QApplication, ms: int = 40) -> None:
    from prettyqt.qt import QtCore

    deadline = time.monotonic() + ms / 1000.0
    while time.monotonic() < deadline:
        qapp.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 10)
        time.sleep(0.005)
    qapp.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents)


def wait_settled(
    qapp: QtWidgets.QApplication,
    window: MainWindow,
    *,
    expect_preview: bool = False,
    timeout_ms: int = SETTLE_TIMEOUT_MS,
) -> None:
    """Process Qt events until async compute/preview/view jobs finish and layouts settle."""
    from prettyqt.qt import QtCore

    from datacook.app.slots import SlotState

    app = window.app
    deadline = time.monotonic() + timeout_ms / 1000.0
    busy = (SlotState.LOADING, SlotState.STALE)
    while time.monotonic() < deadline:
        qapp.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 20)
        node_busy = app.nodes.slot.state in busy
        preview_busy = expect_preview and app.preview.slot.state in busy
        jobs_busy = bool(app.jobs.running_ids())
        if not node_busy and not preview_busy and not jobs_busy:
            break
        time.sleep(0.01)
    # Give pending zero-ms timers (code render, prefetch, resize polish) a turn to run.
    _pump(qapp, 80)
    window.repaint()
    qapp.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents)


def _build_demo_workspace(tmp_dir: pathlib.Path, rows: int = 2_000) -> pathlib.Path:
    """Write a fast demo dataset + project into `tmp_dir` and return the project path."""
    # Reuse tools/demo_data.py directly so screenshots match the real demo project.
    tools_dir = str(pathlib.Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import demo_data  # ty: ignore[unresolved-import]

    from datacook.engine import project

    demo_data.stores().to_csv(tmp_dir / "stores.csv", index=False)
    demo_data.sales(rows).to_parquet(tmp_dir / "sales.parquet", index=False)
    project_path = tmp_dir / "demo.datacook"
    with demo_data.demo_project(tmp_dir) as session:
        project.save(session, project_path)
    return project_path


def _find_node(window: MainWindow, selector: str) -> str | None:
    nodes = window.app.session.nodes()
    if selector.isdigit():
        idx = int(selector)
        return nodes[idx].id if 0 <= idx < len(nodes) else None
    needle = selector.lower()
    for node in nodes:
        if node.id == selector or (node.name and node.name.lower() == needle):
            return node.id
    for node in nodes:
        if node.name and needle in node.name.lower():
            return node.id
    return None


def _raise_dock(window: MainWindow, dock_id: str) -> None:
    dock = window.docks.get(dock_id)
    if dock is not None:
        dock.show()
        dock.raise_()


def _resolve_target(window: MainWindow, target: str) -> QtWidgets.QWidget | None:
    from prettyqt.qt import QtWidgets

    if target == "window":
        return window
    if target in window.docks:
        return window.docks[target]
    if target in window.widgets:
        return window.widgets[target]
    return window.findChild(QtWidgets.QWidget, target)


def _capture_widget(
    widget: QtWidgets.QWidget,
    out_path: pathlib.Path,
    scenario: str,
    target: str,
) -> CaptureInfo:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    pixmap.save(str(out_path))
    return CaptureInfo(
        scenario=scenario,
        target=target,
        path=str(out_path),
        width=pixmap.width(),
        height=pixmap.height(),
    )


def inspect_tree(
    root: QtWidgets.QWidget,
    *,
    max_depth: int = 8,
) -> tuple[list[str], list[LayoutWarning]]:
    """Return an indented widget tree and basic layout diagnostics (clipping, tiny widgets)."""
    from prettyqt.qt import QtWidgets

    lines: list[str] = []
    warnings: list[LayoutWarning] = []

    def label_for(w: QtWidgets.QWidget) -> str:
        name = w.objectName()
        cls = type(w).__name__
        return f"{cls}#{name}" if name else cls

    def visit(widget: QtWidgets.QWidget, depth: int) -> None:
        if depth > max_depth or not widget.isVisible():
            return
        geo = widget.geometry()
        extra = ""
        if isinstance(widget, QtWidgets.QLabel):
            text = widget.text().replace("\n", " ")[:48]
            if text:
                extra = f' text="{text}"'
            if (
                text
                and not widget.wordWrap()
                and widget.width() > 0
                and widget.fontMetrics().horizontalAdvance(widget.text()) > widget.width() + 4
            ):
                warnings.append(
                    LayoutWarning(
                        label_for(widget),
                        "clipped-label",
                        f'"{text}" needs {widget.fontMetrics().horizontalAdvance(widget.text())}px,'
                        f" has {widget.width()}px",
                    )
                )
        elif isinstance(widget, QtWidgets.QAbstractButton):
            text = widget.text().replace("&", "")[:40]
            if text:
                extra = f' text="{text}"'
                needed = widget.sizeHint().width()
                if 0 < widget.width() < needed - 4:
                    warnings.append(
                        LayoutWarning(
                            label_for(widget),
                            "cramped-button",
                            f'"{text}" sizeHint={needed}px, width={widget.width()}px',
                        )
                    )
        elif isinstance(widget, QtWidgets.QDockWidget):
            extra = f' title="{widget.windowTitle()}"'

        if (
            (widget.width() == 0 or widget.height() == 0)
            and type(widget).__name__ not in ("TrackingSpacer", "HeaderView")
            and widget.objectName() != "qt_scrollarea_viewport"
        ):
            warnings.append(
                LayoutWarning(
                    label_for(widget),
                    "zero-size",
                    f"visible widget has geometry {geo.width()}x{geo.height()}",
                )
            )

        indent = "  " * depth
        lines.append(
            f"{indent}{label_for(widget)} [{geo.x()},{geo.y()} {geo.width()}x{geo.height()}]{extra}"
        )
        for child in widget.children():
            if isinstance(child, QtWidgets.QWidget):
                visit(child, depth + 1)

    visit(root, 0)
    return lines, warnings


def _make_window(
    *,
    width: int,
    height: int,
    language: str,
    recipe_dir: pathlib.Path,
) -> MainWindow:
    from datacook.app.application import set_language
    from datacook.app.controllers import AppController
    from datacook.app.mainwindow import MainWindow
    from datacook.app.settings import AppSettings

    settings = AppSettings(
        selection_debounce_ms=0,
        preview_debounce_ms=0,
        preview_rows=80,
        language=language,
        recipe_folder=str(recipe_dir),
    )
    app = AppController(settings=settings)
    set_language(app, language)
    window = MainWindow(app)
    if window.project is not None:
        window.project.ask_save_changes = lambda: "discard"  # ty: ignore[unresolved-attribute]
    window.resize(width, height)
    window.show()
    return window


def _run_scenario(
    qapp: QtWidgets.QApplication,
    scenario: str,
    *,
    width: int,
    height: int,
    language: str,
    out_dir: pathlib.Path,
    targets: list[str],
    demo_dir: pathlib.Path,
    project_path: pathlib.Path,
    dock_to_raise: str | None = None,
    select_step: str | None = None,
    select_column: str | None = None,
    sort_spec: str | None = None,
    trigger_edit: bool = False,
    add_op: str | None = None,
    palette_query: str | None = None,
    dump_tree: bool = False,
) -> tuple[list[CaptureInfo], list[LayoutWarning]]:
    from prettyqt.qt import QtCore

    from datacook.app.actions import OpActions
    from datacook.app.controllers.project import ProjectController
    from datacook.app.docks.recipes import RecipeController
    from datacook.app.state import SortSpec
    from datacook.app.widgets.readerdialog import ReaderDialog
    from datacook.engine.ops import rows as row_ops

    captures: list[CaptureInfo] = []
    all_warnings: list[LayoutWarning] = []

    with tempfile.TemporaryDirectory(prefix="dc-recipes-") as recipe_tmp:
        window = _make_window(
            width=width,
            height=height,
            language=language,
            recipe_dir=pathlib.Path(recipe_tmp),
        )
        try:
            wait_settled(qapp, window)

            if scenario != "empty":
                assert isinstance(window.project, ProjectController)
                window.project.open(project_path)
                wait_settled(qapp, window)

            if scenario == "demo":
                if (nid := _find_node(window, "With stores")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                # Also materialize a couple nodes so the tree shows varied status dots.
                for name in ("Best first", "First 1000"):
                    if (nid := _find_node(window, name)) is not None:
                        window.app.session.materialize(nid)
                if (nid := _find_node(window, "With stores")) is not None:
                    window.app.state.current = nid
                wait_settled(qapp, window)

            elif scenario == "edit":
                if (nid := _find_node(window, "Units per region")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                ops = window.findChild(OpActions, "op-actions")
                if ops is not None:
                    ops.edit_current()
                _raise_dock(window, "params")
                wait_settled(qapp, window, expect_preview=True)

            elif scenario == "edit-filter":
                if (nid := _find_node(window, "Without returns")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                ops = window.findChild(OpActions, "op-actions")
                if ops is not None:
                    ops.edit_current()
                _raise_dock(window, "params")
                wait_settled(qapp, window, expect_preview=True)

            elif scenario == "schema":
                if (nid := _find_node(window, "With stores")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                _raise_dock(window, "schema")
                window.app.state.column = "category"
                wait_settled(qapp, window)

            elif scenario == "recipes":
                assert isinstance(window.recipes, RecipeController)
                if (nid := _find_node(window, "Without returns")) is not None:
                    window.recipes.create(
                        nid,
                        subtree=False,
                        name="Import clean orders",
                        description="Loads sales parquet, fills missing discounts, drops returns.",
                    )
                if (nid := _find_node(window, "Top discounts")) is not None:
                    window.recipes.create(
                        nid,
                        subtree=True,
                        name="Top 1000 discounts",
                        description="Sorts by discount & price and keeps top 1,000 rows.",
                    )
                _raise_dock(window, "recipes")
                wait_settled(qapp, window)

            elif scenario == "messages":
                if (nid := _find_node(window, "Without returns")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                    bad = window.app.commands.add_node(
                        row_ops.FilterRows.record(expr="missing_column > 0"),
                        [nid],
                        name="Broken filter",
                    )
                    window.app.notify("Loaded demo project successfully", "info", nid)
                    window.app.notify("Column 'discount' had 8% missing values", "warning", nid)
                    window.app.state.current = bad
                _raise_dock(window, "messages")
                wait_settled(qapp, window)

            elif scenario == "palette":
                if (nid := _find_node(window, "With stores")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                ops = window.findChild(OpActions, "op-actions")
                if ops is not None:
                    ops.show_palette()
                    _pump(qapp, 60)
                    line_edit = ops.palette.findChild(
                        type(window.findChild(object)),
                    )
                    del line_edit
                    from prettyqt.qt import QtWidgets

                    edits = ops.palette.findChildren(QtWidgets.QLineEdit)
                    if edits:
                        edits[0].setText(palette_query if palette_query is not None else "sort")
                _pump(qapp, 80)

            elif scenario == "reader":
                op = window.app.session.registry.get("read_csv")
                dialog = ReaderDialog(window.app, op, str(demo_dir / "stores.csv"), window)
                dialog.show()
                deadline = time.monotonic() + SETTLE_TIMEOUT_MS / 1000.0
                while time.monotonic() < deadline:
                    qapp.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 20)
                    if dialog.viewer.holder.df is not None:
                        break
                    time.sleep(0.01)
                _pump(qapp, 80)
                captures.append(
                    _capture_widget(dialog, out_dir / f"{scenario}_dialog.png", scenario, "dialog")
                )
                if dump_tree:
                    lines, warnings = inspect_tree(dialog)
                    print(f"\n=== Widget tree: {scenario} (ReaderDialog) ===")
                    print("\n".join(lines))
                    all_warnings.extend(warnings)
                dialog.stop()
                dialog.close()
                dialog.deleteLater()
                return captures, all_warnings

            # Optional ad-hoc overrides (Playwright-style driving flags)
            if select_step is not None and (nid := _find_node(window, select_step)) is not None:
                window.app.state.current = nid
                wait_settled(qapp, window)
            if dock_to_raise is not None:
                _raise_dock(window, dock_to_raise)
            if select_column is not None:
                window.app.state.column = select_column
            if sort_spec is not None:
                col, sep, order = sort_spec.partition(":")
                window.app.state.sort = SortSpec(col, sep != "" and order.lower().startswith("d"))
            if trigger_edit:
                ops = window.findChild(OpActions, "op-actions")
                if ops is not None:
                    ops.edit_current()
            if add_op is not None:
                ops = window.findChild(OpActions, "op-actions")
                if ops is not None:
                    ops.start(add_op)
            if palette_query is not None and scenario != "palette":
                ops = window.findChild(OpActions, "op-actions")
                if ops is not None:
                    ops.show_palette()
                    from prettyqt.qt import QtWidgets

                    edits = ops.palette.findChildren(QtWidgets.QLineEdit)
                    if edits:
                        edits[0].setText(palette_query)
            wait_settled(qapp, window, expect_preview=trigger_edit or add_op is not None)

            # Resolve capture targets
            resolved_targets: list[str] = []
            for t in targets:
                if t == "all-docks":
                    resolved_targets.append("window")
                    resolved_targets.extend(
                        dock_id for dock_id, dock in window.docks.items() if dock.isVisible()
                    )
                    resolved_targets.append("dataview")
                else:
                    resolved_targets.append(t)

            for target in dict.fromkeys(resolved_targets):
                widget = _resolve_target(window, target)
                if widget is None:
                    print(f"warning: target {target!r} not found", file=sys.stderr)
                    continue
                fname = (
                    f"{scenario}_{target}.png" if len(resolved_targets) > 1 else f"{scenario}.png"
                )
                captures.append(_capture_widget(widget, out_dir / fname, scenario, target))

            if dump_tree:
                lines, warnings = inspect_tree(window)
                print(f"\n=== Widget tree: {scenario} ({width}x{height}, lang={language}) ===")
                print("\n".join(lines))
                all_warnings.extend(warnings)
        finally:
            window.close()
            _pump(qapp, 30)

    return captures, all_warnings


ALL_SCENARIOS = (
    "empty",
    "demo",
    "edit",
    "edit-filter",
    "schema",
    "recipes",
    "messages",
    "palette",
    "reader",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        default="demo",
        choices=[*ALL_SCENARIOS, "all"],
        help="Built-in UI state to capture (default: demo; 'all' runs the full suite).",
    )
    parser.add_argument("--project", type=pathlib.Path, help="Optional .datacook project to open.")
    parser.add_argument("--size", type=_parse_size, default=_parse_size(DEFAULT_SIZE), help="WxH")
    parser.add_argument("--lang", default="en", choices=["en", "de"], help="UI language.")
    parser.add_argument(
        "--target",
        default="window",
        help="Comma-separated targets: window, all-docks, dock id, or widget objectName.",
    )
    parser.add_argument("--dock", help="Show and raise a dock tab before capturing.")
    parser.add_argument("--select", help="Select a step by name or 0-based index.")
    parser.add_argument("--column", help="Select a column in AppState.")
    parser.add_argument("--sort", help="Apply display sort: <column> or <column>:desc.")
    parser.add_argument("--edit", action="store_true", help="Open Edit Step on current node.")
    parser.add_argument("--add-op", help="Start adding an op by id (opens params preview).")
    parser.add_argument("--palette", nargs="?", const="", help="Open command palette with query.")
    parser.add_argument("--tree", action="store_true", help="Print widget tree and warnings.")
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path(".ui_inspect"))
    parser.add_argument("--gui", action="store_true", help="Use native display (not offscreen).")
    args = parser.parse_args(argv)

    _ensure_offscreen(gui=args.gui)

    from prettyqt.qt import QtWidgets

    qapp = QtWidgets.QApplication.instance()
    if not isinstance(qapp, QtWidgets.QApplication):
        qapp = QtWidgets.QApplication(["datacook-ui-inspect"])
    qapp.setApplicationName("DataCook")

    targets = [t.strip() for t in args.target.split(",") if t.strip()]
    scenarios = list(ALL_SCENARIOS) if args.scenario == "all" else [args.scenario]
    args.out.mkdir(parents=True, exist_ok=True)

    all_captures: list[CaptureInfo] = []
    all_warnings: list[LayoutWarning] = []

    with tempfile.TemporaryDirectory(prefix="dc-demo-") as demo_tmp:
        demo_dir = pathlib.Path(demo_tmp)
        project_path = args.project or _build_demo_workspace(demo_dir)
        width, height = args.size
        for scenario in scenarios:
            caps, warns = _run_scenario(
                qapp,
                scenario,
                width=width,
                height=height,
                language=args.lang,
                out_dir=args.out,
                targets=targets,
                demo_dir=demo_dir,
                project_path=project_path,
                dock_to_raise=args.dock,
                select_step=args.select,
                select_column=args.column,
                sort_spec=args.sort,
                trigger_edit=args.edit,
                add_op=args.add_op,
                palette_query=args.palette,
                dump_tree=args.tree,
            )
            all_captures.extend(caps)
            all_warnings.extend(warns)

    manifest = {
        "size": f"{args.size[0]}x{args.size[1]}",
        "language": args.lang,
        "captures": [asdict(c) for c in all_captures],
        "warnings": [asdict(w) for w in all_warnings],
    }
    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(all_captures)} screenshot(s) -> {args.out}")
    if all_warnings:
        print(f"Layout warnings ({len(all_warnings)}):")
        for w in all_warnings:
            print(f"  [{w.kind}] {w.widget}: {w.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
