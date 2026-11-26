"""CommandController: every Session mutation, undoable (GUI thread only)."""

import contextlib
from typing import TYPE_CHECKING

from prettyqt import gui
from prettyqt.qt import QtCore

from datacook.app import commands


if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    from datacook.app.protocols import SessionLike
    from datacook.engine import OpRecord


class CommandController(QtCore.QObject):
    """Owns the undo stack. Docks never call `Session.add/update/remove` directly.

    Undo / redo actions for menus: `undo_stack.createUndoAction(parent)` /
    `createRedoAction(parent)`. The clean state of the stack is the "saved" state.
    """

    def __init__(self, session: SessionLike, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self.session = session
        self.undo_stack = gui.UndoStack(self)

    def push(self, command: commands.SessionCommand) -> commands.SessionCommand:
        """Run `command` and put it on the stack; re-raises if its first redo failed."""
        self.undo_stack.push(command)
        if command.error is not None:
            raise command.error
        return command

    # --- operations --------------------------------------------------------------------
    def add_node(
        self,
        record: OpRecord,
        parents: Sequence[str] = (),
        *,
        name: str | None = None,
        comment: str | None = None,
        node_id: str | None = None,
    ) -> str:
        """Add a step (a new root if `parents` is empty, a branch if the parent has children)."""
        cmd = commands.AddNodeCommand(
            self.session, record, parents, name=name, comment=comment, node_id=node_id
        )
        self.push(cmd)
        return cmd.node_id

    def remove_subtree(self, node_id: str) -> None:
        self.push(commands.RemoveSubtreeCommand(self.session, node_id))

    def remove_step(self, node_id: str) -> None:
        """Delete one middle step, keep its children (they move to its parent).

        Raises `engine.restructure.StepError` (translated reason) for sources, merges and
        children that use columns the parent does not have.
        """
        self.push(commands.RemoveStepCommand(self.session, node_id))

    def edit_params(self, node_id: str, record: OpRecord) -> None:
        node = self.session.get(node_id)
        if node is not None and node.record == record:
            return
        self.push(commands.EditParamsCommand(self.session, node_id, record))

    def rename(self, node_id: str, name: str) -> None:
        self.push(commands.RenameCommand(self.session, node_id, name))

    def set_comment(self, node_id: str, comment: str) -> None:
        self.push(commands.CommentCommand(self.session, node_id, comment))

    @contextlib.contextmanager
    def macro(self, text: object) -> Generator[None]:
        """Group the commands pushed inside into one undo step."""
        self.undo_stack.beginMacro(str(text))
        try:
            yield
        finally:
            self.undo_stack.endMacro()

    # --- stack -------------------------------------------------------------------------
    def undo(self) -> None:
        self.undo_stack.undo()

    def redo(self) -> None:
        self.undo_stack.redo()

    def can_undo(self) -> bool:
        return self.undo_stack.canUndo()

    def can_redo(self) -> bool:
        return self.undo_stack.canRedo()

    def clear(self) -> None:
        """New / open project: forget the history."""
        self.undo_stack.clear()

    def is_clean(self) -> bool:
        return self.undo_stack.isClean()

    def set_clean(self) -> None:
        self.undo_stack.setClean()
