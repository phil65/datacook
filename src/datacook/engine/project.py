"""Project files: the node tree as JSON (op records incl. reader specs, versioned).

```json
{"format": "datacook-project", "version": 1,
 "nodes": [{"id": "...", "op": "read_csv", "params": {...}, "parents": [],
            "name": null, "comment": null}, ...]}
```
Loading creates nodes only; nothing is computed or executed until a frame is requested.
"""

import json
import pathlib
from typing import TYPE_CHECKING, Any

from datacook.engine.ops import record_from_json


if TYPE_CHECKING:
    from datacook.engine.session import Session

FORMAT = "datacook-project"
VERSION = 1


class ProjectError(ValueError):
    pass


def to_dict(session: Session) -> dict[str, Any]:
    nodes = [
        {
            "id": node.id,
            **node.record.to_json(),
            "parents": list(node.parents),
            "name": node.name,
            "comment": node.comment,
        }
        for node in session.nodes()
    ]
    return {"format": FORMAT, "version": VERSION, "nodes": nodes}


def from_dict(session: Session, data: dict[str, Any]) -> None:
    if data.get("format") != FORMAT:
        raise ProjectError("not a DataCook project")
    version = data.get("version")
    if not isinstance(version, int) or version > VERSION:
        msg = f"unsupported project version {version!r} (supported: <= {VERSION})"
        raise ProjectError(msg)
    for entry in data["nodes"]:
        try:
            record = record_from_json(entry, session.registry)
        except (KeyError, ValueError) as e:
            msg = f"node {entry.get('id')!r}: {e}"
            raise ProjectError(msg) from e
        session.add(
            record,
            entry.get("parents", []),
            name=entry.get("name"),
            comment=entry.get("comment"),
            node_id=entry["id"],
        )


def dumps(session: Session) -> str:
    return json.dumps(to_dict(session), indent=2, ensure_ascii=False)


def save(session: Session, path: str | pathlib.Path) -> None:
    pathlib.Path(path).write_text(dumps(session) + "\n", encoding="utf-8")


def load(session: Session, path: str | pathlib.Path) -> None:
    """Add the project's nodes to `session` (usually an empty one)."""
    from_dict(session, json.loads(pathlib.Path(path).read_text(encoding="utf-8")))
