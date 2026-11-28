r"""DataCook UI inspection and screenshot harness built on `prettyqt.debugging.UIInspector`.

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
from dataclasses import asdict
import gc
import json
import pathlib
import sys
import tempfile
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from prettyqt.debugging import CaptureInfo, LayoutWarning
    from prettyqt.qt import QtWidgets

    from datacook.app.mainwindow import MainWindow


DEFAULT_SIZE = "1400x900"
SETTLE_TIMEOUT_MS = 10_000
ALL_SCENARIOS = (
    "empty",
    "demo",
    "edit",
    "edit-filter",
    "column-map",
    "custom-code",
    "ml",
    "schema",
    "schema-numeric",
    "recipes",
    "messages",
    "sort",
    "palette",
    "reader",
)


def _apply_dark_palette(qapp: QtWidgets.QApplication) -> None:
    """Apply a standard dark Fusion palette to test dark-mode contrast."""
    from prettyqt.qt import QtGui

    qapp.setStyle("Fusion")
    pal = QtGui.QPalette()
    cr = QtGui.QPalette.ColorRole
    cg = QtGui.QPalette.ColorGroup
    pal.setColor(cr.Window, QtGui.QColor(43, 45, 48))
    pal.setColor(cr.WindowText, QtGui.QColor(225, 227, 230))
    pal.setColor(cr.Base, QtGui.QColor(30, 31, 34))
    pal.setColor(cr.AlternateBase, QtGui.QColor(38, 40, 44))
    pal.setColor(cr.ToolTipBase, QtGui.QColor(43, 45, 48))
    pal.setColor(cr.ToolTipText, QtGui.QColor(225, 227, 230))
    pal.setColor(cr.Text, QtGui.QColor(225, 227, 230))
    pal.setColor(cr.PlaceholderText, QtGui.QColor(145, 150, 160))
    pal.setColor(cr.Button, QtGui.QColor(53, 56, 61))
    pal.setColor(cr.ButtonText, QtGui.QColor(225, 227, 230))
    pal.setColor(cr.Mid, QtGui.QColor(78, 82, 90))
    pal.setColor(cr.Midlight, QtGui.QColor(60, 63, 69))
    pal.setColor(cr.Dark, QtGui.QColor(28, 30, 33))
    pal.setColor(cr.Highlight, QtGui.QColor(53, 116, 240))
    pal.setColor(cr.HighlightedText, QtGui.QColor(255, 255, 255))
    pal.setColor(cg.Disabled, cr.WindowText, QtGui.QColor(120, 125, 134))
    pal.setColor(cg.Disabled, cr.Text, QtGui.QColor(120, 125, 134))
    pal.setColor(cg.Disabled, cr.ButtonText, QtGui.QColor(120, 125, 134))
    qapp.setPalette(pal)


def _parse_size(spec: str) -> tuple[int, int]:
    w_str, sep, h_str = spec.lower().partition("x")
    if not sep:
        msg = f"invalid size {spec!r}, expected WxH (e.g. 1400x900)"
        raise argparse.ArgumentTypeError(msg)
    return int(w_str), int(h_str)


def wait_settled(
    qapp: QtWidgets.QApplication,
    window: MainWindow,
    *,
    expect_preview: bool = False,
    timeout_ms: int = SETTLE_TIMEOUT_MS,
) -> None:
    """Process Qt events until async compute/preview/view jobs finish and layouts settle."""
    from prettyqt.debugging import pump, wait_until

    from datacook.app.slots import SlotState

    app = window.app
    busy = (SlotState.LOADING, SlotState.STALE)

    def idle() -> bool:
        node_busy = app.nodes.slot.state in busy
        preview_busy = expect_preview and app.preview.slot.state in busy
        return not node_busy and not preview_busy and not app.jobs.running_ids()

    wait_until(idle, timeout_ms=timeout_ms, app=qapp)
    pump(qapp, 80)
    window.repaint()
    pump(qapp, 20)


def _build_demo_workspace(tmp_dir: pathlib.Path, rows: int = 2_000) -> pathlib.Path:
    """Write a fast demo dataset + project into `tmp_dir` and return the project path."""
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
    from prettyqt.debugging import UIInspector, capture, inspect_tree, pump, wait_until
    from prettyqt.qt import QtCore, QtWidgets

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
        inspector = UIInspector(window, out_dir=out_dir, app=qapp)
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
                if (ops := window.findChild(OpActions, "op-actions")) is not None:
                    ops.edit_current()
                _raise_dock(window, "params")
                wait_settled(qapp, window, expect_preview=True)

            elif scenario == "edit-filter":
                if (nid := _find_node(window, "Without returns")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                if (ops := window.findChild(OpActions, "op-actions")) is not None:
                    ops.edit_current()
                _raise_dock(window, "params")
                wait_settled(qapp, window, expect_preview=True)

            elif scenario == "column-map":
                if (nid := _find_node(window, "With stores")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                if (ops := window.findChild(OpActions, "op-actions")) is not None:
                    ops.start("rename_columns")
                _raise_dock(window, "params")
                wait_settled(qapp, window, expect_preview=True)

            elif scenario == "custom-code":
                if (nid := _find_node(window, "With stores")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                if (ops := window.findChild(OpActions, "op-actions")) is not None:
                    ops.start("custom_code")
                _raise_dock(window, "params")
                wait_settled(qapp, window, expect_preview=True)

            elif scenario == "ml":
                if (nid := _find_node(window, "With stores")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                if (ops := window.findChild(OpActions, "op-actions")) is not None:
                    ops.start("cluster")
                _raise_dock(window, "params")
                wait_settled(qapp, window, expect_preview=True)

            elif scenario == "schema":
                if (nid := _find_node(window, "With stores")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                _raise_dock(window, "schema")
                window.app.state.column = "category"
                wait_settled(qapp, window)

            elif scenario == "schema-numeric":
                if (nid := _find_node(window, "With stores")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                _raise_dock(window, "schema")
                window.app.state.column = "unit_price"
                wait_settled(qapp, window)

            elif scenario == "sort":
                if (nid := _find_node(window, "With stores")) is not None:
                    window.app.state.current = nid
                    wait_settled(qapp, window)
                window.app.state.sort = SortSpec("unit_price", descending=True)
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
                if (ops := window.findChild(OpActions, "op-actions")) is not None:
                    ops.show_palette()
                    pump(qapp, 60)
                    if edits := ops.palette.findChildren(QtWidgets.QLineEdit):
                        edits[0].setText(palette_query if palette_query is not None else "sort")
                pump(qapp, 80)

            elif scenario == "reader":
                op = window.app.session.registry.get("read_csv")
                dialog = ReaderDialog(window.app, op, str(demo_dir / "stores.csv"), window)
                dialog.show()
                wait_until(
                    lambda: dialog.viewer.holder.df is not None,
                    timeout_ms=SETTLE_TIMEOUT_MS,
                    app=qapp,
                )
                pump(qapp, 80)
                captures.append(
                    capture(
                        dialog,
                        out_dir / f"{scenario}_dialog.png",
                        scenario=scenario,
                        target="dialog",
                    )
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

            # Optional ad-hoc overrides
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
            if trigger_edit and (ops := window.findChild(OpActions, "op-actions")) is not None:
                ops.edit_current()
            if (
                add_op is not None
                and (ops := window.findChild(OpActions, "op-actions")) is not None
            ):
                ops.start(add_op)
            if (
                palette_query is not None
                and scenario != "palette"
                and (ops := window.findChild(OpActions, "op-actions")) is not None
            ):
                ops.show_palette()
                if edits := ops.palette.findChildren(QtWidgets.QLineEdit):
                    edits[0].setText(palette_query)
            wait_settled(qapp, window, expect_preview=trigger_edit or add_op is not None)

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

            captures.extend(inspector.capture_targets(resolved_targets, scenario=scenario))

            if dump_tree:
                lines, warnings = inspector.tree()
                print(f"\n=== Widget tree: {scenario} ({width}x{height}, lang={language}) ===")
                print("\n".join(lines))
                all_warnings.extend(warnings)
        finally:
            window.close()
            window.deleteLater()
            del inspector, window
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            pump(qapp, 30)
            gc.collect()

    return captures, all_warnings


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
        "--theme", default="light", choices=["light", "dark"], help="Palette theme."
    )
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

    if not args.gui:
        from prettyqt.debugging import ensure_offscreen

        ensure_offscreen()

    from prettyqt.qt import QtWidgets

    qapp = QtWidgets.QApplication.instance()
    if not isinstance(qapp, QtWidgets.QApplication):
        qapp = QtWidgets.QApplication(["datacook-ui-inspect"])
    qapp.setApplicationName("DataCook")
    if args.theme == "dark":
        _apply_dark_palette(qapp)

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
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(all_captures)} screenshot(s) -> {args.out}")
    if all_warnings:
        print(f"Layout warnings ({len(all_warnings)}):")
        for w in all_warnings:
            print(f"  [{w.kind}] {w.widget}: {w.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
