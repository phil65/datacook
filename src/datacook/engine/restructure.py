"""Tree restructuring rules (Qt-free): delete a middle step and keep the steps after it.

Deleting step S with parent P re-parents S's children to P: they then consume P's output
instead of S's. That is only valid when S has exactly one input (a merge has two parents:
which one would the children get?) and S is not a source (a reader has no parent to hand
over). The column check is best effort: when P's schema is known (it was computed once),
every column a child names in its params for the input it took from S must exist in P.
Columns that steps further down need are not checked (their errors show when computed).
"""

from typing import TYPE_CHECKING, Protocol

from datacook.engine.ops.base import column_refs
from datacook.i18n import _


if TYPE_CHECKING:
    from datacook.engine.frames import FrameSummary
    from datacook.engine.node import Node
    from datacook.engine.ops import Op
    from datacook.engine.registry import Registry


class StepError(ValueError):
    """A restructuring the tree does not allow (the message says why, translated)."""


class TreeReader(Protocol):
    @property
    def registry(self) -> Registry[type[Op]]: ...

    def get(self, node_id: str) -> Node | None: ...

    def children(self, node_id: str) -> tuple[Node, ...]: ...

    def summary(self, node_id: str) -> FrameSummary | None: ...


def check_remove_step(session: TreeReader, node_id: str) -> str:
    """The parent that takes over `node_id`'s children; raises `StepError` if not allowed."""
    node = session.get(node_id)
    if node is None:
        raise KeyError(node_id)
    if not node.parents:
        msg = _(
            "The first step of a chain (a data source) cannot be deleted on its own. "
            "Delete the step with its following steps instead."
        )
        raise StepError(str(msg))
    if len(node.parents) > 1:
        msg = _(
            "A step with several inputs (e.g. a merge) cannot be deleted while keeping its "
            "following steps: they would not know which input to use."
        )
        raise StepError(str(msg))
    parent = node.parents[0]
    summary = session.summary(parent)
    if summary is not None:
        available = {c.name for c in summary.columns}
        missing: dict[str, None] = {}
        for child in session.children(node_id):
            refs = column_refs(child.record.params)
            for index, pid in enumerate(child.parents):
                if pid == node_id:
                    used = refs.get(index, ())
                    missing.update(dict.fromkeys(c for c in used if c not in available))
        if missing:
            msg = _("The following steps use columns the previous step does not have: {columns}")
            raise StepError(str(msg).format(columns=", ".join(missing)))
    return parent
