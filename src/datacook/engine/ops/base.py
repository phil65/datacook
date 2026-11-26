"""Op base classes and op records.

An `Op` subclass is the behaviour (apply, code generation, code recognition) plus metadata;
an `OpRecord` (op id + frozen `Params` instance) is what a tree node stores and what project
files contain. Ops are stateless: all methods are classmethods taking the params.

Most ops are a single pandas call; `CallOp` derives `apply`, `to_code` and `from_call` from
one declaration (`method` / `function`, positional params), so execution and generated code
cannot drift. Ops working on selected columns derive from `ops.series.ColumnOp`.
"""

import ast
from dataclasses import dataclass
import keyword
import math
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

import pydantic

from datacook.engine import categories, frames
from datacook.i18n import LazyText


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from datacook.engine.categories import Category
    from datacook.engine.frames import Backend, Frame


class Params(pydantic.BaseModel):
    """Base for op parameters: immutable, unknown keys rejected."""

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")


class NoParams(Params):
    pass


class OpError(Exception):
    """An op failed to apply (wraps the backend's exception)."""


class Op:
    """Base class for operations. Subclasses set the metadata class variables."""

    id: ClassVar[str]
    title: ClassVar[LazyText]
    description: ClassVar[LazyText] = LazyText("")  # no msgid: not in the catalog
    category: ClassVar[Category] = categories.GENERAL
    icon: ClassVar[str] = "mdi.function"
    Params: ClassVar[type[Params]] = NoParams
    n_inputs: ClassVar[int] = 1
    """Number of parent frames: 0 = source (reader), 2 = merge, ..."""
    variadic: ClassVar[bool] = False
    """`n_inputs` or more parent frames (concat)."""
    backend: ClassVar[Backend] = "pandas"
    imports: ClassVar[tuple[str, ...]] = ("import pandas as pd",)
    """Import lines the generated code needs."""
    requires: ClassVar[tuple[str, ...]] = ()
    """Importable modules needed at runtime (optional dependencies)."""
    extra: ClassVar[str | None] = None
    """The package extra that installs `requires`."""

    # --- execution -------------------------------------------------------------------
    @classmethod
    def apply(cls, params: Any, *inputs: Frame) -> Frame:
        raise NotImplementedError

    # --- code ------------------------------------------------------------------------
    @classmethod
    def to_code(cls, params: Any, inputs: Sequence[str], output: str) -> str:
        """Python statement(s) computing `output` from the input variables."""
        raise NotImplementedError

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> Match | None:
        """Recognise one statement produced by `to_code`; `bound` = known variable names.

        Return None if the statement is not this op. Raise `ValueError` for a recognised
        statement with invalid params.
        """
        return None

    # --- helpers ---------------------------------------------------------------------
    @classmethod
    def record(cls, params: Params | None = None, /, **kwargs: Any) -> OpRecord:
        return OpRecord(cls.id, params if params is not None else cls.Params(**kwargs))

    @classmethod
    def takes(cls, n: int) -> bool:
        """Whether the op takes `n` input frames."""
        return n == cls.n_inputs or (cls.variadic and n > cls.n_inputs)

    @classmethod
    def inputs_text(cls) -> str:
        """`"2"` or `"2 or more"` (error messages)."""
        return f"{cls.n_inputs} or more" if cls.variadic else str(cls.n_inputs)

    @classmethod
    def imports_for(cls, params: Any) -> tuple[str, ...]:
        """Import lines the generated code needs for `params` (default: `cls.imports`)."""
        return cls.imports

    @classmethod
    def available(cls) -> bool:
        import importlib.util

        return all(importlib.util.find_spec(mod) is not None for mod in cls.requires)


@dataclass(frozen=True, slots=True)
class Match:
    """A recognised statement: the op's params, input variables and output variable."""

    params: Params
    inputs: tuple[str, ...]
    output: str


@dataclass(frozen=True, slots=True)
class OpRecord:
    """What a node stores: the op id plus its (immutable) params."""

    op_id: str
    params: Params

    def to_json(self) -> dict[str, Any]:
        return {"op": self.op_id, "params": self.params.model_dump(mode="json")}


# --- column references -------------------------------------------------------------------

COLUMN_WIDGETS = frozenset({"column", "columns", "column_map"})


def column_refs(params: pydantic.BaseModel) -> dict[int, list[str]]:
    """Column names the params refer to, per input index (`{0: ["a", "b"], 1: [...]}`).

    Read from the fields' UI hints (`json_schema_extra={"widget": "column" | "columns" |
    "column_map", "input": n}`), also in nested models (e.g. `Aggregation.column`).
    `column_map` refers to its keys. Order of first appearance, no duplicates.
    """
    refs: dict[int, dict[str, None]] = {}
    _collect_refs(params, 0, refs)
    return {index: list(names) for index, names in refs.items()}


def _collect_refs(model: pydantic.BaseModel, index: int, refs: dict[int, dict[str, None]]) -> None:
    for name, info in type(model).model_fields.items():
        value = getattr(model, name)
        extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
        widget = extra.get("widget")
        field_index = extra.get("input", index)
        if not isinstance(field_index, int):
            field_index = index
        if widget in COLUMN_WIDGETS:
            names = refs.setdefault(field_index, {})
            match value:
                case str():
                    names[value] = None
                case dict():
                    names.update(dict.fromkeys(str(k) for k in value))
                case list() | tuple():
                    names.update(dict.fromkeys(str(v) for v in value))
            continue
        items = value if isinstance(value, (list, tuple)) else [value]
        for item in items:
            if isinstance(item, pydantic.BaseModel):
                _collect_refs(item, field_index, refs)


def string_values(params: pydantic.BaseModel) -> set[str]:
    """Every string anywhere in the params (keys included): names a step may create."""
    found: set[str] = set()

    def visit(value: Any) -> None:
        match value:
            case str():
                found.add(value)
            case dict():
                for k, v in value.items():
                    visit(k)
                    visit(v)
            case list() | tuple():
                for v in value:
                    visit(v)

    visit(params.model_dump(mode="json"))
    return found


# --- code helpers ------------------------------------------------------------------------


def literal(value: Any) -> str:  # noqa: PLR0911
    """Python source of a literal value (str/int/float/bool/None, lists, tuples, dicts).

    Strings use double quotes where possible (ruff / black style).
    """
    match value:
        case str():
            r = repr(value)
            if r.startswith("'") and '"' not in value:
                return '"' + r[1:-1].replace("\\'", "'") + '"'
            return r
        case list():
            return "[" + ", ".join(literal(v) for v in value) + "]"
        case tuple():
            inner = ", ".join(literal(v) for v in value)
            return f"({inner},)" if len(value) == 1 else f"({inner})"
        case dict():
            return "{" + ", ".join(f"{literal(k)}: {literal(v)}" for k, v in value.items()) + "}"
        case float() if math.isnan(value) or math.isinf(value):
            return f'float("{value}")'
        case _:
            return repr(value)


LINE_LENGTH = 88


def format_call(func: str, args: Sequence[str], kwargs: Mapping[str, Any], indent: int = 0) -> str:
    """`func(a, b, key=value)`, wrapped one argument per line when longer than 88 chars."""
    parts = [*args, *(f"{k}={literal(v)}" for k, v in kwargs.items())]
    line = f"{func}({', '.join(parts)})"
    if indent + len(line) <= LINE_LENGTH or not parts:
        return line
    inner = "".join(f"    {p},\n" for p in parts)
    return f"{func}(\n{inner})"


def dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


def assignment(stmt: ast.stmt) -> tuple[str, ast.expr] | None:
    """`(target, value)` of `name = value`, else None."""
    if (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
    ):
        return stmt.targets[0].id, stmt.value
    return None


class _FloatSpecials(ast.NodeTransformer):
    def visit_Call(self, node: ast.Call) -> ast.AST:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "float"
            and len(node.args) == 1
            and not node.keywords
            and isinstance(arg := node.args[0], ast.Constant)
            and arg.value in ("nan", "inf", "-inf")
        ):
            return ast.Constant(float(str(arg.value)))
        return node


def literal_value(node: ast.expr) -> Any:
    """Evaluate a literal expression (plus `float("nan")` / `float("inf")`).

    Raises ValueError for anything else.
    """
    try:
        return ast.literal_eval(_FloatSpecials().visit(node))
    except (TypeError, SyntaxError, MemoryError, RecursionError) as e:
        raise ValueError(str(e)) from e


def strip_tail(value: ast.expr, tail: str) -> ast.expr | None:
    """`value` without the trailing code `tail` (`".reset_index()"`); None if it has none."""
    text = ast.unparse(value)
    tail = ast.unparse(ast.parse(f"x{tail}", mode="eval").body)[1:]
    if not text.endswith(tail) or len(text) == len(tail):
        return None
    try:
        return ast.parse(text[: -len(tail)], mode="eval").body
    except SyntaxError:
        return None


def call_arguments(
    params: Params,
    positional: Sequence[str] = (),
    always: Sequence[str] = (),
    skip: Sequence[str] = (),
) -> tuple[list[Any], dict[str, Any]]:
    """Call arguments of params: `positional` ones in order, the others as keywords.

    A keyword is passed when it is required, listed in `always` or differs from its
    default; `skip`: params that are not call arguments (e.g. the selected columns).
    """
    values = params.model_dump(mode="python")
    for name in skip:
        values.pop(name, None)
    args = [values.pop(name) for name in positional]
    fields = type(params).model_fields
    kwargs = {
        k: v
        for k, v in values.items()
        if k in always
        or fields[k].is_required()
        or v != fields[k].get_default(call_default_factory=True)
    }
    return args, kwargs


class CallOp(Op):
    """An op that is one pandas call.

    Either `method` (called on the first input, remaining inputs as leading positional
    arguments: `out = a.merge(b, how="left")`) or `function` (a dotted name in the generated
    code, all inputs as leading positional arguments: `out = pd.read_csv("x.csv")`).
    Params named in `positional` are passed positionally; the other params are passed as
    keywords when they differ from their default.
    """

    method: ClassVar[str | None] = None
    function: ClassVar[str | None] = None
    positional: ClassVar[tuple[str, ...]] = ()
    always: ClassVar[tuple[str, ...]] = ()
    """Params passed even when they equal their default (defaults that differ from pandas)."""
    fixed: ClassVar[Mapping[str, Any]] = MappingProxyType({})
    """Keyword arguments that are not params, always passed first (e.g. `axis="columns"`)."""
    then: ClassVar[str] = ""
    """Code appended to the call (`".reset_index()"`); `finish()` does the same in `apply`."""

    @classmethod
    def finish(cls, params: Any, result: Any) -> Any:
        """What `then` does, applied to the call's result."""
        return result

    @classmethod
    def call_args(cls, params: Params) -> tuple[list[Any], dict[str, Any]]:
        args, kwargs = call_arguments(params, cls.positional, cls.always)
        return args, {**cls.fixed, **kwargs}

    @classmethod
    def params_from_call(cls, args: list[Any], kwargs: dict[str, Any]) -> Params | None:
        """The params of a call; None if not this op."""
        if len(args) > len(cls.positional):
            msg = f"too many positional arguments for {cls.id}"
            raise ValueError(msg)
        for key, value in cls.fixed.items():
            if key not in kwargs or kwargs.pop(key) != value:
                return None
        if not set(kwargs) <= set(cls.Params.model_fields):
            return None  # e.g. `dropna(axis="columns")` is not "drop rows with missing values"
        return cls.Params(**dict(zip(cls.positional, args)), **kwargs)

    @classmethod
    def _callable(cls, inputs: Sequence[Frame]) -> Any:
        if cls.method is not None:
            return getattr(inputs[0], cls.method)
        assert cls.function is not None
        module, _sep, name = cls.function.rpartition(".")
        namespace = {"pd": "pandas"}
        import importlib

        obj: Any = importlib.import_module(namespace.get(module, module))
        return getattr(obj, name)

    @classmethod
    def apply(cls, params: Any, *inputs: Frame) -> Frame:
        args, kwargs = cls.call_args(params)
        frame_args = inputs[1:] if cls.method is not None else inputs
        result = cls.finish(params, cls._callable(inputs)(*frame_args, *args, **kwargs))
        if not frames.is_frame(result):
            msg = f"{cls.id} returned {type(result).__name__}, not a frame"
            raise OpError(msg)
        return result

    @classmethod
    def to_code(cls, params: Any, inputs: Sequence[str], output: str) -> str:
        args, kwargs = cls.call_args(params)
        if cls.method is not None:
            func = f"{inputs[0]}.{cls.method}"
            frame_args = list(inputs[1:])
        else:
            assert cls.function is not None
            func = cls.function
            frame_args = list(inputs)
        width = len(output) + 3 + len(cls.then)  # the tail goes on the last line
        call = format_call(func, [*frame_args, *map(literal, args)], kwargs, width)
        return f"{output} = {call}{cls.then}"

    @classmethod
    def literal_args(cls, call: ast.Call, skip: int = 0) -> tuple[list[Any], dict[str, Any]] | None:
        """Literal positional (after `skip`) and keyword arguments of a call, else None."""
        if any(kw.arg is None for kw in call.keywords):
            return None
        try:
            args = [literal_value(a) for a in call.args[skip:]]
            kwargs = {kw.arg: literal_value(kw.value) for kw in call.keywords if kw.arg}
        except ValueError:  # not literal: user code, kept as custom code
            return None
        return args, kwargs

    @classmethod
    def from_code(  # noqa: PLR0911
        cls, stmt: ast.stmt, bound: Mapping[str, Any]
    ) -> Match | None:
        assign = assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if cls.then:
            value = strip_tail(value, cls.then)
        if not isinstance(value, ast.Call):
            return None
        func = dotted_name(value.func)
        if func is None:
            return None
        n_frames = cls.n_inputs
        if cls.method is not None:
            base, _sep, attr = func.rpartition(".")
            if attr != cls.method or base not in bound:
                return None
            inputs = [base]
            n_frames -= 1
        elif func == cls.function:
            inputs = []
        else:
            return None
        frame_nodes = value.args[:n_frames]
        if len(frame_nodes) < n_frames or not all(
            isinstance(a, ast.Name) and a.id in bound for a in frame_nodes
        ):
            return None
        inputs += [a.id for a in frame_nodes if isinstance(a, ast.Name)]
        found = cls.literal_args(value, n_frames)
        if found is None:
            return None
        params = cls.params_from_call(*found)
        return None if params is None else Match(params, tuple(inputs), output)


def assign_target(value: ast.expr, bound: Mapping[str, Any]) -> tuple[str, ast.keyword] | None:
    """`(frame, keyword)` of `frame.assign(<one keyword>)` on a bound frame variable."""
    if not (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "assign"
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id in bound
        and not value.args
        and len(value.keywords) == 1
    ):
        return None
    return value.func.value.id, value.keywords[0]


def assign_item(kw: ast.keyword) -> tuple[str, ast.expr] | None:
    """`(name, value)` of an `assign` argument `name=value` or `**{"name": value}`."""
    if kw.arg is not None:
        return kw.arg, kw.value
    value = kw.value
    if (
        isinstance(value, ast.Dict)
        and len(value.keys) == 1
        and isinstance(key := value.keys[0], ast.Constant)
        and isinstance(key.value, str)
    ):
        return key.value, value.values[0]
    return None


def assign_kwarg(name: str, expr: str) -> str:
    """`name=expr` for `DataFrame.assign`, or `**{"name": expr}` if not a plain identifier."""
    if name.isidentifier() and not keyword.iskeyword(name) and name != "self":
        return f"{name}={expr}"
    return f"**{{{literal(name)}: {expr}}}"
