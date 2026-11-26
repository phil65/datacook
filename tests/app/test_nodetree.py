"""Node tree dock: structure follows the session (add / remove / rename / undo), badges."""

from typing import TYPE_CHECKING

from prettyqt.qt import QtCore
import pytest

from datacook.app.docks.nodetree import NodeStatus, NodeTreeWidget
from datacook.engine import OpError
from datacook.engine.ops import rows, sources
from tests.app.conftest import check_invariant, drain, frame


if TYPE_CHECKING:
    from datacook.app.controllers import AppController
    from datacook.app.testing import FakeSession


@pytest.fixture
def tree(qtbot, app: AppController) -> NodeTreeWidget:
    widget = NodeTreeWidget(app)
    qtbot.addWidget(widget)
    return widget


def _rows(tree: NodeTreeWidget) -> list[str]:
    model = tree.model
    return ["  " * model.depth(n) + model.label(n) for n in model.ids()]


def _tree(app: AppController) -> tuple[str, str, str]:
    """Root -> a, root -> b (a branch)."""
    root = app.commands.add_node(sources.InlineData.record(data={"a": [1, 2]}), name="data")
    a = app.commands.add_node(rows.Head.record(n=1), [root], name="a")
    b = app.commands.add_node(rows.Head.record(n=2), [root], name="b")
    drain(app)
    return root, a, b


def test_tree_reflects_add_remove_and_undo(app: AppController, tree: NodeTreeWidget) -> None:
    root, a, _b = _tree(app)
    assert _rows(tree) == ["data", "  a", "  b"]
    c = app.commands.add_node(rows.Head.record(n=1), [a], name="c")
    drain(app)
    assert _rows(tree) == ["data", "  a", "    c", "  b"]
    assert tree.model.rowCount(tree.model.index_of(a)) == 1
    tree.delete(a)
    drain(app)
    assert _rows(tree) == ["data", "  b"]
    assert tree.model.index_of(c).isValid() is False
    app.commands.undo()
    drain(app)
    # re-added subtree goes to the end of its parent's children (design §6)
    assert _rows(tree) == ["data", "  b", "  a", "    c"]
    app.commands.undo()  # the add of c
    drain(app)
    assert _rows(tree) == ["data", "  b", "  a"]
    assert tree.model.index_of(root).isValid()
    check_invariant(app)


def test_rename_and_comment_through_commands(app: AppController, tree: NodeTreeWidget) -> None:
    _root, a, _b = _tree(app)
    index = tree.model.index_of(a)
    assert tree.model.setData(index, "first", QtCore.Qt.ItemDataRole.EditRole)
    drain(app)
    assert tree.model.data(index) == "first"
    assert app.session.get(a).name == "first"
    app.commands.undo()
    drain(app)
    assert tree.model.data(tree.model.index_of(a)) == "a"
    tree.set_comment(a, "keep only one")
    drain(app)
    tooltip = tree.model.data(tree.model.index_of(a), QtCore.Qt.ItemDataRole.ToolTipRole)
    assert "keep only one" in tooltip
    # an empty or unchanged name is not a command
    depth = app.commands.undo_stack.count()
    assert not tree.model.setData(tree.model.index_of(a), "  ", QtCore.Qt.ItemDataRole.EditRole)
    assert app.commands.undo_stack.count() == depth


def test_selection_syncs_with_state(app: AppController, tree: NodeTreeWidget) -> None:
    root, a, b = _tree(app)
    tree.view.setCurrentIndex(tree.model.index_of(b))
    assert app.state.current == b
    app.state.current = a
    assert tree.model.node_id(tree.view.currentIndex()) == a
    app.state.current = None
    assert not tree.view.selectionModel().hasSelection()
    tree.branch(root)
    assert app.state.current == root
    check_invariant(app)


def test_status_badges_and_shape(
    app: AppController, fake: FakeSession, tree: NodeTreeWidget
) -> None:
    root, a, b = _tree(app)
    model = tree.model
    assert model.status(a) == NodeStatus.NOT_COMPUTED
    assert model.data(model.index_of(a, 1)) == ""
    app.state.current = a
    assert model.status(a) == NodeStatus.COMPUTING
    changed: list[str] = []
    model.dataChanged.connect(lambda tl, _br: changed.append(model.node_id(tl)))
    fake.complete(fake.pending(a)[0], frame(1))
    drain(app)
    assert model.status(a) == NodeStatus.PINNED
    assert a in changed
    assert model.data(model.index_of(a, 1)) == "1 × 1"  # noqa: RUF001
    assert model.data(model.index_of(a, 2)).endswith("B")
    fake.put(b, frame(2))
    drain(app)
    assert model.status(b) == NodeStatus.IN_MEMORY  # cached, not pinned
    app.state.current = b
    fake.fail(fake.request(root), OpError("x"))
    drain(app)
    assert model.status(root) == NodeStatus.ERROR
    tooltip = model.data(model.index_of(a), QtCore.Qt.ItemDataRole.ToolTipRole)
    assert "Upstream error" in tooltip
    assert model.data(model.index_of(root), QtCore.Qt.ItemDataRole.DecorationRole) is not None
    check_invariant(app)


def test_structure_reset_rebuilds(
    app: AppController, fake: FakeSession, tree: NodeTreeWidget
) -> None:
    _tree(app)
    for i in range(250):  # > 200 events in one drain -> structure_reset
        fake.add(sources.InlineData.record(data={"a": [i]}))
    resets: list[bool] = []
    tree.model.modelReset.connect(lambda: resets.append(True))
    drain(app)
    assert resets
    assert len(tree.model.ids()) == 253
