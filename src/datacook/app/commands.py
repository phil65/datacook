"""Undoable commands over `Session` mutations (GUI thread; push via `CommandController`).

Commands store node ids and op records only, never frames: undo recomputes on demand.
A command whose first `redo` fails is marked obsolete (Qt then drops it from the stack) and
keeps the exception in `error`; `CommandController.push` re-raises it.
"""

from typing import TYPE_CHECKING

from prettyqt.qt import QtGui

from datacook.engine.node import new_id
from datacook.i18n import _


if TYPE_CHECKING:
    from collections.abc import Sequence

    from datacook.app.protocols import SessionLike
    from datacook.engine import Node, OpRecord


class SessionCommand(QtGui.QUndoCommand):
    """Base: `_redo` / `_undo` do the work; `affected()` names the touched nodes."""

    def __init__(self, session: SessionLike, text: object) -> None:
        super().__init__(str(text))
        self.session = session
        self.error: Exception | None = None
        self._done_once = False

    def redo(self) -> None:
        if self._done_once:
            self._redo()
            return
        try:
            self._redo()
        except Exception as e:  # noqa: BLE001 - re-raised by CommandController.push
            self.error = e
            self.setObsolete(True)
        self._done_once = True

    def undo(self) -> None:
        self._undo()

    def _redo(self) -> None:
        raise NotImplementedError

    def _undo(self) -> None:
        raise NotImplementedError

    def affected(self) -> tuple[str, ...]:
        return ()


class AddNodeCommand(SessionCommand):
    def __init__(
        self,
        session: SessionLike,
        record: OpRecord,
        parents: Sequence[str] = (),
        *,
        name: str | None = None,
        comment: str | None = None,
        node_id: str | None = None,
    ) -> None:
        super().__init__(session, _("Add step"))
        self.record = record
        self.parents = tuple(parents)
        self.name = name
        self.comment = comment
        self.node_id = node_id or new_id()

    def _redo(self) -> None:
        self.session.add(
            self.record, self.parents, name=self.name, comment=self.comment, node_id=self.node_id
        )

    def _undo(self) -> None:
        self.session.remove(self.node_id)

    def affected(self) -> tuple[str, ...]:
        return (self.node_id,)


class RemoveSubtreeCommand(SessionCommand):
    """Remove a node and its descendants; undo re-adds them with the same ids.

    Known limit: re-added nodes go to the end of their parents' children.
    """

    def __init__(self, session: SessionLike, node_id: str) -> None:
        super().__init__(session, _("Delete step"))
        self.node_id = node_id
        self.snapshot: tuple[Node, ...] = ()

    def _redo(self) -> None:
        ids = {self.node_id, *self.session.descendants(self.node_id)}
        # insertion order = parents before children (also for multi-input nodes)
        self.snapshot = tuple(n for n in self.session.nodes() if n.id in ids)
        self.session.remove(self.node_id)

    def _undo(self) -> None:
        for node in self.snapshot:
            self.session.add(
                node.record, node.parents, name=node.name, comment=node.comment, node_id=node.id
            )

    def affected(self) -> tuple[str, ...]:
        return tuple(n.id for n in self.snapshot) or (self.node_id,)


class RemoveStepCommand(SessionCommand):
    """Delete one middle step; its children move to its parent (`Session.remove_step`).

    Undo re-adds the step with the same id and gives the children their old parents back.
    """

    def __init__(self, session: SessionLike, node_id: str) -> None:
        super().__init__(session, _("Delete step (keep following steps)"))
        self.node_id = node_id
        self.node: Node | None = None
        self.children: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def _redo(self) -> None:
        children = tuple((c.id, c.parents) for c in self.session.children(self.node_id))
        self.node = self.session.remove_step(self.node_id)
        self.children = children

    def _undo(self) -> None:
        node = self.node
        if node is None:
            return
        self.session.add(
            node.record, node.parents, name=node.name, comment=node.comment, node_id=node.id
        )
        for child, parents in self.children:
            self.session.reparent(child, parents)

    def affected(self) -> tuple[str, ...]:
        return (self.node_id, *(c for c, _p in self.children))


class EditParamsCommand(SessionCommand):
    def __init__(self, session: SessionLike, node_id: str, record: OpRecord) -> None:
        super().__init__(session, _("Edit step"))
        self.node_id = node_id
        node = session.get(node_id)
        if node is None:
            raise KeyError(node_id)
        self.old = node.record
        self.new = record

    def _redo(self) -> None:
        self.session.update(self.node_id, self.new)

    def _undo(self) -> None:
        self.session.update(self.node_id, self.old)

    def affected(self) -> tuple[str, ...]:
        return (self.node_id, *self.session.descendants(self.node_id))


class _TextCommand(SessionCommand):
    """Rename / comment; consecutive edits of the same node merge into one undo step."""

    field: str = ""
    command_id: int = -1

    def __init__(self, session: SessionLike, node_id: str, text: str, title: object) -> None:
        super().__init__(session, title)
        self.node_id = node_id
        node = session.get(node_id)
        if node is None:
            raise KeyError(node_id)
        self.old = getattr(node, self.field) or ""
        self.new = text

    def _redo(self) -> None:
        self._apply(self.new)

    def _undo(self) -> None:
        self._apply(self.old)

    def _apply(self, text: str) -> None:
        raise NotImplementedError

    def id(self) -> int:
        return self.command_id

    def mergeWith(self, other: QtGui.QUndoCommand) -> bool:  # noqa: N802
        if not isinstance(other, type(self)) or other.node_id != self.node_id:
            return False
        self.new = other.new
        return True

    def affected(self) -> tuple[str, ...]:
        return (self.node_id,)


class RenameCommand(_TextCommand):
    field = "name"
    command_id = 1001

    def __init__(self, session: SessionLike, node_id: str, name: str) -> None:
        super().__init__(session, node_id, name, _("Rename step"))

    def _apply(self, text: str) -> None:
        self.session.update(self.node_id, name=text)


class CommentCommand(_TextCommand):
    field = "comment"
    command_id = 1002

    def __init__(self, session: SessionLike, node_id: str, comment: str) -> None:
        super().__init__(session, node_id, comment, _("Edit comment"))

    def _apply(self, text: str) -> None:
        self.session.update(self.node_id, comment=text)
