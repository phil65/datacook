"""Params dock: forms for every op, live preview, commit / edit (undoable), column editors."""

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from datacook.app.docks.params import ParamsPanel
from datacook.app.slots import SlotState
from datacook.app.widgets.columnchooser import ColumnChooser, ColumnMapEditor, ColumnsChooser
from datacook.engine.ops import rows, sources, timeseries
from tests.app.conftest import check_invariant, drain


if TYPE_CHECKING:
    from datacook.app.controllers import AppController
    from datacook.app.testing import FakeSession


LEFT = pd.DataFrame({"k": [1, 2], "x": [0.5, 1.5], "s": ["a", "b"]})
RIGHT = pd.DataFrame({"key": [1, 2], "y": [10, 20]})


@pytest.fixture
def panel(app: AppController, qtbot) -> ParamsPanel:
    app.state.update_settings(preview_debounce_ms=0)
    widget = ParamsPanel(app)
    qtbot.addWidget(widget)
    return widget


def _roots(app: AppController, fake: FakeSession) -> tuple[str, str]:
    left = app.commands.add_node(sources.InlineData.record(data={"k": [1]}))
    right = app.commands.add_node(sources.InlineData.record(data={"key": [1]}))
    fake.put(left, LEFT)
    fake.put(right, RIGHT)
    drain(app)
    return left, right


def test_form_for_every_op(app: AppController, fake: FakeSession, panel: ParamsPanel) -> None:
    left, right = _roots(app, fake)
    for op in app.session.registry:
        inputs = (left, right)[: op.n_inputs]
        app.preview.start_add(op.id, inputs)
        drain(app)
        assert panel.form is not None, op.id
        assert panel.form.get_model() is op.Params
        assert panel.op is op
        assert panel.title_label.text().endswith(str(op.title))
        app.preview.cancel()
        assert panel.form is None
    check_invariant(app)


def test_preview_follows_params_then_commit_is_undoable(
    app: AppController, fake: FakeSession, panel: ParamsPanel
) -> None:
    left, _ = _roots(app, fake)
    app.state.current = left
    drain(app)
    app.preview.start_add(rows.Head.id, [left])
    # defaults are valid: the preview starts at once
    (first,) = fake.pending_previews()
    assert first.record is not None
    assert first.record.params == rows.Head.Params()
    fake.complete(first, LEFT.head(5))
    drain(app)
    assert app.preview.slot.state == SlotState.READY
    assert app.state.display == "preview"
    assert "first 2 rows" in panel.status_label.text()
    assert panel.form is not None
    panel.form.get_editor("n").setValue(1)
    (second,) = fake.pending_previews()
    assert second.record is not None
    assert second.record.params == rows.Head.Params(n=1)
    fake.complete(second, LEFT.head(1))
    drain(app)
    assert len(app.preview.slot.frame) == 1
    assert panel.apply_button.isEnabled()
    node_id = panel.apply()
    assert node_id is not None
    node = app.session.get(node_id)
    assert node is not None
    assert node.record == rows.Head.record(n=1)
    assert node.parents == (left,)
    app.commands.undo()
    drain(app)
    assert node_id not in app.session
    check_invariant(app)


def test_invalid_input_disables_apply(
    app: AppController, fake: FakeSession, panel: ParamsPanel
) -> None:
    left, _ = _roots(app, fake)
    app.preview.start_add("select_columns", [left])
    assert panel.form is not None
    # columns: min_length=1 -> invalid until a column is checked
    assert not panel.apply_button.isEnabled()
    assert fake.pending_previews() == []
    assert panel.apply() is None
    editor = panel.form.get_editor("columns")
    assert isinstance(editor, ColumnsChooser)
    editor.set_value(["s"])
    assert panel.apply_button.isEnabled()
    (req,) = fake.pending_previews()
    assert req.record is not None
    assert req.record.params.columns == ["s"]  # ty: ignore[unresolved-attribute]


def test_edit_mode_loads_step_and_follows_undo(
    app: AppController, fake: FakeSession, panel: ParamsPanel
) -> None:
    left, _ = _roots(app, fake)
    step = app.commands.add_node(rows.Head.record(n=2), [left])
    drain(app)
    app.preview.start_edit(step)
    assert panel.form is not None
    assert panel.form.get_editor("n").value() == 2  # ty: ignore[unresolved-attribute]
    assert panel.apply_button.text() == "Apply"
    panel.form.get_editor("n").setValue(3)  # ty: ignore[unresolved-attribute]
    assert panel.apply() == step
    drain(app)
    node = app.session.get(step)
    assert node is not None
    assert node.record == rows.Head.record(n=3)
    # undo while the step is being edited: the form reloads the step's params
    app.preview.start_edit(step)
    app.commands.undo()
    drain(app)
    assert panel.form.get_editor("n").value() == 2  # ty: ignore[unresolved-attribute]
    app.preview.cancel()
    check_invariant(app)


def test_column_editors_offer_input_columns(
    app: AppController, fake: FakeSession, panel: ParamsPanel
) -> None:
    left, right = _roots(app, fake)
    app.preview.start_add("merge", [left, right])
    assert panel.form is not None
    on = panel.form.get_editor("on").editor  # ty: ignore[unresolved-attribute]
    right_on = panel.form.get_editor("right_on").editor  # ty: ignore[unresolved-attribute]
    assert isinstance(on, ColumnsChooser)
    assert on.columns() == ["k", "x", "s"]
    assert right_on.columns() == ["key", "y"]
    app.preview.cancel()
    app.preview.start_add("rename_columns", [left])
    editor = panel.form.get_editor("columns")
    assert isinstance(editor, ColumnMapEditor)
    assert editor.columns() == ["k", "x", "s"]
    editor.item(1, 1).setText("x_new")  # ty: ignore[possibly-missing-attribute]
    assert editor.get_value() == {"x": "x_new"}
    (req,) = fake.pending_previews()
    assert req.record is not None
    assert req.record.params.columns == {"x": "x_new"}  # ty: ignore[unresolved-attribute]


def test_column_editor_refreshes_when_input_is_computed(
    app: AppController, fake: FakeSession, panel: ParamsPanel
) -> None:
    root = app.commands.add_node(sources.InlineData.record(data={"k": [1]}))
    drain(app)
    app.preview.start_add("groupby_aggregate", [root])
    assert panel.form is not None
    by = panel.form.get_editor("by")
    assert isinstance(by, ColumnsChooser)
    by.set_value(["k"])
    assert by.columns() == []  # input not computed yet: free names only
    fake.put(root, LEFT)
    drain(app)
    assert by.columns() == ["k", "x", "s"]
    assert by.get_value() == ["k"]  # value kept


def test_column_chooser_keeps_value(qapp) -> None:
    chooser = ColumnChooser(["a", "b"])
    chooser.set_value("b")
    chooser.set_columns(["b", "c"])
    assert chooser.get_value() == "b"
    assert chooser.columns() == ["b", "c"]
    chooser.set_value("zzz")  # not a column (yet): kept as typed
    assert chooser.get_value() == "zzz"


def test_new_time_series_step_starts_with_the_time_column(
    app: AppController, fake: FakeSession, panel: ParamsPanel
) -> None:
    root = app.commands.add_node(sources.InlineData.record(data={"k": [1]}))
    frame = pd.DataFrame({"k": [1, 2], "when": pd.to_datetime(["2024-01-01", "2024-01-02"])})
    fake.put(root, frame)
    drain(app)
    app.preview.start_add(timeseries.SecondsSinceStart.id, [root])
    assert panel.form is not None
    assert panel.form.get_editor("time_column").get_value() == "when"  # ty: ignore[unresolved-attribute]
    app.preview.cancel()
    # optional time columns (rolling: rows by default) stay off
    app.preview.start_add(timeseries.Rolling.id, [root])
    assert panel.form is not None
    value = panel.form.get_value()
    assert value is None or value.time_column is None  # ty: ignore[unresolved-attribute]
