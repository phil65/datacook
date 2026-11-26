"""Operations: `Op` classes, op records and the op registry (entry point group `datacook.ops`)."""

import functools
from typing import TYPE_CHECKING, Any

from datacook.engine.ops.base import CallOp, Match, NoParams, Op, OpError, OpRecord, Params
from datacook.engine.registry import OPS_GROUP, Registry


if TYPE_CHECKING:
    from collections.abc import Mapping


@functools.cache
def default_ops() -> Registry[type[Op]]:
    """The registry of all installed ops (built-ins included), loaded from entry points."""
    return Registry[type[Op]](OPS_GROUP)


def record_from_json(
    data: Mapping[str, Any], registry: Registry[type[Op]] | None = None
) -> OpRecord:
    registry = registry if registry is not None else default_ops()
    op = registry[data["op"]]
    return OpRecord(op.id, op.Params.model_validate(data.get("params", {})))


__all__ = [
    "CallOp",
    "Match",
    "NoParams",
    "Op",
    "OpError",
    "OpRecord",
    "Params",
    "default_ops",
    "record_from_json",
]
