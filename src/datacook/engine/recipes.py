"""Recipes: reusable step sequences (Qt-free, backend-agnostic: op records only).

A `Recipe` is an ordered list of op records whose inputs are *relative*: an earlier step of
the recipe (its index) or `INPUT`, the node the recipe is applied to. Steps may branch and
join again (a merge of two recipe branches); every step that is not a source has its
inputs inside the recipe or on `INPUT`. A recipe without `INPUT` starts with a reader: an
**import recipe**, applied to files (the reader's path is swapped per file).

Created from a node path (`from_path`) or a subtree (`from_subtree`); applied with
`apply` / `apply_many` / `import_files` (or `plan` + your own `add`, e.g. undoable commands
in the app). Applying adds normal nodes, so the generated code is just normal steps.

File format (`.datacookrecipe`, JSON, versioned):

```json
{"format": "datacook-recipe", "version": 1, "name": "Clean", "description": "",
 "created": "2026-11-25T10:00:00+00:00", "datacook": "0.1.0",
 "required_columns": ["a"],
 "steps": [{"op": "dropna", "params": {...}, "inputs": ["input"], "name": null,
            "comment": null},
           {"op": "head", "params": {"n": 5}, "inputs": [0]}]}
```

`required_columns`: columns the input must have, derived from the steps' column params
(`ops.base.column_refs`): with the input's schema known at creation, every referenced
column the input has; otherwise the columns the steps reading the input directly name.
"""

from dataclasses import dataclass, field, replace
import datetime as dt
import json
import pathlib
import re
from typing import TYPE_CHECKING, Any, Protocol

from datacook.engine import node as node_mod
from datacook.engine.ops import record_from_json
from datacook.engine.ops.base import column_refs, string_values
from datacook.i18n import _


if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from datacook.engine.frames import FrameSummary
    from datacook.engine.node import Node
    from datacook.engine.ops import Op, OpRecord
    from datacook.engine.registry import Registry
    from datacook.engine.session import Session


FORMAT = "datacook-recipe"
VERSION = 1
SUFFIX = ".datacookrecipe"
INPUT = "input"
"""Step input meaning "the node the recipe is applied to"."""

type StepInput = int | str


class RecipeError(ValueError):
    """Invalid recipe, file or application (the message says why, translated)."""


@dataclass(frozen=True, slots=True)
class RecipeStep:
    record: OpRecord
    inputs: tuple[StepInput, ...] = (INPUT,)
    """Index of an earlier step, or `INPUT`."""
    name: str | None = None
    comment: str | None = None


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _version() -> str:
    import datacook

    return str(getattr(datacook, "__version__", ""))


@dataclass(frozen=True, slots=True)
class Recipe:
    name: str
    steps: tuple[RecipeStep, ...]
    description: str = ""
    required_columns: tuple[str, ...] = ()
    created: str = field(default_factory=_now)
    datacook: str = field(default_factory=_version)
    """DataCook version that wrote the recipe."""

    @property
    def is_import(self) -> bool:
        """No step reads the input: the recipe starts with a reader (apply it to files)."""
        return not any(INPUT in s.inputs for s in self.steps)

    def leaves(self) -> list[int]:
        """Indexes of the steps no other step consumes."""
        used = {i for s in self.steps for i in s.inputs if isinstance(i, int)}
        return [i for i in range(len(self.steps)) if i not in used]

    def sources(self) -> list[int]:
        """Indexes of the steps without inputs (readers)."""
        return [i for i, s in enumerate(self.steps) if not s.inputs]

    def missing_columns(self, columns: Iterable[str]) -> list[str]:
        available = set(columns)
        return [c for c in self.required_columns if c not in available]

    def validate(self, registry: Registry[type[Op]]) -> None:
        """Structure check (input indexes, input counts); raises `RecipeError`."""
        if not self.steps:
            raise RecipeError(str(_("A recipe needs at least one step.")))
        for i, step in enumerate(self.steps):
            try:
                op = registry[step.record.op_id]
            except KeyError as e:
                msg = _("Step {index}: unknown operation {op!r}")
                raise RecipeError(str(msg).format(index=i + 1, op=step.record.op_id)) from e
            if not op.takes(len(step.inputs)):
                msg = _("Step {index}: {op} takes {n} input(s)")
                raise RecipeError(str(msg).format(index=i + 1, op=op.id, n=op.inputs_text()))
            for ref in step.inputs:
                if ref != INPUT and not (isinstance(ref, int) and 0 <= ref < i):
                    msg = _("Step {index}: invalid input {ref!r}")
                    raise RecipeError(str(msg).format(index=i + 1, ref=ref))

    # --- serialisation -----------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "version": VERSION,
            "name": self.name,
            "description": self.description,
            "created": self.created,
            "datacook": self.datacook,
            "required_columns": list(self.required_columns),
            "steps": [
                {
                    **s.record.to_json(),
                    "inputs": list(s.inputs),
                    "name": s.name,
                    "comment": s.comment,
                }
                for s in self.steps
            ],
        }

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def save(self, path: str | pathlib.Path) -> None:
        pathlib.Path(path).write_text(self.dumps() + "\n", encoding="utf-8")


def from_dict(data: Any, registry: Registry[type[Op]] | None = None) -> Recipe:
    from datacook.engine.ops import default_ops

    registry = registry if registry is not None else default_ops()
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise RecipeError(str(_("Not a DataCook recipe")))
    version = data.get("version")
    if not isinstance(version, int) or version > VERSION:
        msg = _("Unsupported recipe version {version!r} (supported: up to {supported})")
        raise RecipeError(str(msg).format(version=version, supported=VERSION))
    steps = []
    for i, entry in enumerate(data.get("steps", [])):
        try:
            record = record_from_json(entry, registry)
        except (KeyError, ValueError) as e:
            msg = _("Step {index}: {error}")
            raise RecipeError(str(msg).format(index=i + 1, error=e)) from e
        steps.append(
            RecipeStep(
                record,
                tuple(entry.get("inputs", [INPUT])),
                name=entry.get("name"),
                comment=entry.get("comment"),
            )
        )
    recipe = Recipe(
        name=str(data.get("name") or ""),
        steps=tuple(steps),
        description=str(data.get("description") or ""),
        required_columns=tuple(data.get("required_columns", ())),
        created=str(data.get("created") or ""),
        datacook=str(data.get("datacook") or ""),
    )
    recipe.validate(registry)
    return recipe


def loads(text: str, registry: Registry[type[Op]] | None = None) -> Recipe:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        msg = _("Not a DataCook recipe: {error}")
        raise RecipeError(str(msg).format(error=e)) from e
    return from_dict(data, registry)


def load(path: str | pathlib.Path, registry: Registry[type[Op]] | None = None) -> Recipe:
    return loads(pathlib.Path(path).read_text(encoding="utf-8"), registry)


# --- creating ------------------------------------------------------------------------------


class TreeReader(Protocol):
    """What creating a recipe reads (`Session`, the app's `SessionLike`)."""

    @property
    def registry(self) -> Registry[type[Op]]: ...

    def get(self, node_id: str) -> Node | None: ...

    def nodes(self) -> tuple[Node, ...]: ...

    def ancestors(self, node_id: str) -> tuple[Node, ...]: ...

    def descendants(self, node_id: str) -> tuple[str, ...]: ...

    def summary(self, node_id: str) -> FrameSummary | None: ...


def from_nodes(
    session: TreeReader,
    node_ids: Iterable[str],
    *,
    name: str,
    description: str = "",
    input_columns: Iterable[str] | None = None,
) -> Recipe:
    """A recipe of the given nodes (in tree order).

    At most one node outside them may feed them (it becomes `INPUT`); without one, the nodes
    must start with a reader (import recipe).

    `input_columns`: the schema of that outside node, if known (else read from its summary).
    """
    wanted = set(node_ids)
    nodes = [n for n in session.nodes() if n.id in wanted]
    if not nodes:
        raise RecipeError(str(_("No steps selected for the recipe.")))
    index = {n.id: i for i, n in enumerate(nodes)}
    external = list(dict.fromkeys(p for n in nodes for p in n.parents if p not in index))
    if len(external) > 1:
        msg = _(
            "The steps use {n} steps outside the selection as input; a recipe can have only "
            "one input."
        )
        raise RecipeError(str(msg).format(n=len(external)))
    steps = tuple(
        RecipeStep(
            n.record,
            tuple(index.get(p, INPUT) for p in n.parents),
            name=n.name,
            comment=n.comment,
        )
        for n in nodes
    )
    if input_columns is None and external:
        summary = session.summary(external[0])
        if summary is not None:
            input_columns = [c.name for c in summary.columns]
    recipe = Recipe(
        name=name,
        steps=steps,
        description=description,
        required_columns=_required(steps, input_columns) if external else (),
    )
    recipe.validate(session.registry)
    return recipe


def _required(steps: Sequence[RecipeStep], input_columns: Iterable[str] | None) -> tuple[str, ...]:
    found: dict[str, None] = {}
    if input_columns is not None:
        available = set(input_columns)
        for step in steps:
            for names in column_refs(step.record.params).values():
                found.update(dict.fromkeys(c for c in names if c in available))
        return tuple(found)
    for step in steps:
        refs = column_refs(step.record.params)
        for i, ref in enumerate(step.inputs):
            if ref == INPUT:
                found.update(dict.fromkeys(refs.get(i, ())))
    return tuple(found)


def from_path(
    session: TreeReader,
    node_id: str,
    *,
    start: str | None = None,
    name: str,
    description: str = "",
) -> Recipe:
    """The steps leading to `node_id`: after `start` (its input), or all (import recipe)."""
    ids = [n.id for n in session.ancestors(node_id)]
    if start is not None:
        before = {n.id for n in session.ancestors(start)}
        if start not in ids:
            raise RecipeError(str(_("The start step is not on the path to the step.")))
        ids = [i for i in ids if i not in before]
    return from_nodes(session, ids, name=name, description=description)


def from_subtree(session: TreeReader, node_id: str, *, name: str, description: str = "") -> Recipe:
    """`node_id` and every step after it; the recipe's input is `node_id`'s parent."""
    ids = [node_id, *session.descendants(node_id)]
    return from_nodes(session, ids, name=name, description=description)


# --- combining -----------------------------------------------------------------------------


def merge(first: Recipe, second: Recipe, *, name: str | None = None) -> Recipe:
    """`second` applied to the result of `first` (one recipe)."""
    leaves = first.leaves()
    if len(leaves) != 1:
        raise RecipeError(str(_("The first recipe must end in a single step to merge.")))
    if second.is_import:
        raise RecipeError(str(_("An import recipe can only be the first one of a merge.")))
    offset = len(first.steps)
    steps = [
        replace(s, inputs=tuple(i + offset if isinstance(i, int) else leaves[0] for i in s.inputs))
        for s in second.steps
    ]
    mentioned = set().union(*(string_values(s.record.params) for s in first.steps))
    required = list(first.required_columns)
    if first.is_import:
        required = []
    else:
        required += [c for c in second.required_columns if c not in mentioned]
    return Recipe(
        name=name or f"{first.name} + {second.name}",
        steps=(*first.steps, *steps),
        description="\n".join(d for d in (first.description, second.description) if d),
        required_columns=tuple(dict.fromkeys(required)),
    )


# --- applying ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlannedNode:
    """A node to add (ids are fresh); `parents` are existing or earlier planned ids."""

    node_id: str
    record: OpRecord
    parents: tuple[str, ...]
    name: str | None = None
    comment: str | None = None


def plan(
    recipe: Recipe,
    target: str | None = None,
    *,
    path: str | pathlib.Path | None = None,
    registry: Registry[type[Op]] | None = None,
) -> list[PlannedNode]:
    """The nodes applying `recipe` adds: on `target`, or (import recipe) reading `path`.

    With `path`, the recipe's reader reads that file instead (another reader if the file
    type differs; its options are then the defaults) and is named after the file.
    """
    if recipe.is_import:
        if target is not None:
            msg = _("{name!r} is an import recipe (it starts with a reader): apply it to files.")
            raise RecipeError(str(msg).format(name=recipe.name))
    elif target is None:
        msg = _("{name!r} needs a step to apply it to.")
        raise RecipeError(str(msg).format(name=recipe.name))
    steps = list(recipe.steps)
    if path is not None:
        steps = _with_path(recipe, steps, pathlib.Path(path), registry)
    ids = [node_mod.new_id() for _step in steps]
    out = []
    for i, step in enumerate(steps):
        parents = tuple(ids[ref] if isinstance(ref, int) else str(target) for ref in step.inputs)
        out.append(PlannedNode(ids[i], step.record, parents, name=step.name, comment=step.comment))
    return out


def _with_path(
    recipe: Recipe,
    steps: list[RecipeStep],
    path: pathlib.Path,
    registry: Registry[type[Op]] | None,
) -> list[RecipeStep]:
    from datacook.engine.formats import FormatRegistry
    from datacook.engine.ops import OpRecord, default_ops

    sources = recipe.sources()
    if not recipe.is_import or len(sources) != 1:
        msg = _("Only an import recipe with one reader can be applied to files.")
        raise RecipeError(str(msg))
    index = sources[0]
    step = steps[index]
    if "path" not in type(step.record.params).model_fields:
        raise RecipeError(str(_("The recipe's first step does not read a file.")))
    registry = registry if registry is not None else default_ops()
    try:
        reader = FormatRegistry(registry).reader_for(path)
    except KeyError as e:
        msg = _("No reader for {suffix} files")
        raise RecipeError(str(msg).format(suffix=path.suffix or path.name)) from e
    if reader.id == step.record.op_id:
        params = step.record.params.model_copy(update={"path": str(path)})
        record = OpRecord(reader.id, reader.Params.model_validate(params.model_dump()))
    else:
        record = reader.record(path=str(path))
    steps[index] = replace(step, record=record, name=path.name)
    return steps


def input_columns(session: Session, node_id: str) -> list[str]:
    """Column names of a node (from its summary, else computed now)."""
    summary = session.summary(node_id)
    if summary is None:
        session.materialize(node_id)
        summary = session.summary(node_id)
    if summary is None:  # pragma: no cover - materialize stores a summary
        return []
    return [c.name for c in summary.columns]


def check_target(recipe: Recipe, columns: Iterable[str], target_label: str = "") -> None:
    """Raise `RecipeError` if the target lacks a required column."""
    missing = recipe.missing_columns(columns)
    if missing:
        msg = _("Recipe {name!r} needs columns that {target} does not have: {columns}")
        target = target_label or str(_("the step"))
        raise RecipeError(
            str(msg).format(name=recipe.name, target=target, columns=", ".join(missing))
        )


def _add(session: Session, planned: Sequence[PlannedNode]) -> list[Node]:
    added: list[Node] = []
    try:
        for p in planned:
            node = session.add(
                p.record, p.parents, name=p.name, comment=p.comment, node_id=p.node_id
            )
            added.append(node)
    except Exception:
        for node in reversed(added):
            if node.id in session:
                session.remove(node.id)
        raise
    return added


def apply(
    session: Session, recipe: Recipe, target: str | None = None, *, check: bool = True
) -> list[Node]:
    """Add the recipe's steps on `target` (a new branch); checks required columns first."""
    if check and target is not None and recipe.required_columns:
        check_target(recipe, input_columns(session, target), target)
    return _add(session, plan(recipe, target, registry=session.registry))


def apply_many(
    session: Session, recipe: Recipe, targets: Sequence[str], *, check: bool = True
) -> list[list[Node]]:
    """`apply` to every target; all targets are checked before anything is added."""
    if check and recipe.required_columns:
        for target in targets:
            check_target(recipe, input_columns(session, target), target)
    return [apply(session, recipe, target, check=False) for target in targets]


def import_files(
    session: Session, recipe: Recipe, paths: Sequence[str | pathlib.Path]
) -> list[list[Node]]:
    """An import recipe once per file (a new root each); all plans are made first."""
    plans = [plan(recipe, path=p, registry=session.registry) for p in paths]
    return [_add(session, planned) for planned in plans]


# --- library -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LibraryEntry:
    path: pathlib.Path
    recipe: Recipe | None
    error: str | None = None

    @property
    def name(self) -> str:
        return self.recipe.name if self.recipe is not None else self.path.stem


def _slug(name: str) -> str:
    slug = re.sub(r"[^\w\- ]+", "", name).strip().replace(" ", "_")
    return slug[:80] or "recipe"


class RecipeLibrary:
    """A folder of `.datacookrecipe` files (the app uses `<user data dir>/recipes`)."""

    def __init__(self, folder: str | pathlib.Path, registry: Registry[type[Op]] | None = None):
        self.folder = pathlib.Path(folder)
        self.registry = registry

    def entries(self) -> list[LibraryEntry]:
        """Every recipe file, sorted by name; unreadable files carry `error`."""
        if not self.folder.is_dir():
            return []
        out = []
        for path in sorted(self.folder.glob(f"*{SUFFIX}")):
            try:
                out.append(LibraryEntry(path, load(path, self.registry)))
            except (RecipeError, OSError, UnicodeDecodeError) as e:
                out.append(LibraryEntry(path, None, str(e)))
        return sorted(out, key=lambda e: e.name.casefold())

    def _free_path(self, name: str, keep: pathlib.Path | None = None) -> pathlib.Path:
        base = _slug(name)
        path = self.folder / f"{base}{SUFFIX}"
        n = 2
        while path.exists() and path != keep:
            path = self.folder / f"{base}-{n}{SUFFIX}"
            n += 1
        return path

    def save(self, recipe: Recipe) -> pathlib.Path:
        """Store a new recipe (a free file name from its name)."""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self._free_path(recipe.name)
        recipe.save(path)
        return path

    def update(
        self,
        path: str | pathlib.Path,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> pathlib.Path:
        """Rename / re-describe a recipe; the file follows the name. Returns the new path."""
        path = pathlib.Path(path)
        recipe = load(path, self.registry)
        changes: dict[str, Any] = {}
        if name is not None:
            if not name.strip():
                raise RecipeError(str(_("A recipe needs a name.")))
            changes["name"] = name.strip()
        if description is not None:
            changes["description"] = description
        recipe = replace(recipe, **changes)
        new_path = self._free_path(recipe.name, keep=path) if name is not None else path
        recipe.save(new_path)
        if new_path != path:
            path.unlink()
        return new_path

    def delete(self, path: str | pathlib.Path) -> None:
        pathlib.Path(path).unlink(missing_ok=True)

    def merge(
        self, paths: Sequence[str | pathlib.Path], *, name: str | None = None
    ) -> pathlib.Path:
        """A new recipe: the given recipes one after the other (originals are kept)."""
        if len(paths) < 2:  # noqa: PLR2004
            raise RecipeError(str(_("Select at least two recipes to merge.")))
        recipes = [load(p, self.registry) for p in paths]
        result = recipes[0]
        for other in recipes[1:]:
            result = merge(result, other)
        if name:
            result = replace(result, name=name)
        return self.save(replace(result, created=_now()))

    def import_file(self, path: str | pathlib.Path) -> pathlib.Path:
        """Copy a recipe file into the library (validated first)."""
        return self.save(load(path, self.registry))
