"""Column-wise ops: one expression per column, generated as a single `assign()` call.

`ColumnOp` computes one new series per selected column and writes it back under the same
name (replacing the column) or under `<column><suffix>`:

    df = df.assign(name=df["name"].str.upper(), city=df["city"].str.upper())

`SeriesOp` derives everything from a declaration of one series call (accessor, method or
function, positional params), like `CallOp` for frame methods, so execution and generated
code cannot drift. Code recognition uses `unchain()` (a method chain as a list of links)
and confirms every match by regenerating the code (`confirm()`).
"""

import ast
from dataclasses import dataclass, field
import importlib
import keyword
import typing
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import Field

from datacook.engine.ops import base
from datacook.i18n import N_


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import pandas as pd

    from datacook.engine.frames import Frame


# --- code helpers ------------------------------------------------------------------------


def column_code(var: str, column: str) -> str:
    return f"{var}[{base.literal(column)}]"


def assign_code(var: str, output: str, values: Mapping[str, str]) -> str:
    """`out = var.assign(a=..., b=...)`; `**{"a b": ...}` if a name is no identifier."""
    if all(name.isidentifier() and not keyword.iskeyword(name) for name in values):
        parts = [f"{name}={code}" for name, code in values.items()]
    else:
        inner = ", ".join(f"{base.literal(name)}: {code}" for name, code in values.items())
        parts = [f"**{{{inner}}}"]
    line = f"{output} = {var}.assign({', '.join(parts)})"
    if len(line) <= base.LINE_LENGTH:
        return line
    if parts[0].startswith("**"):
        inner = "".join(f"        {base.literal(n)}: {_indent(c, 8)},\n" for n, c in values.items())
        return f"{output} = {var}.assign(\n    **{{\n{inner}    }}\n)"
    inner = "".join(f"    {_indent(p, 4)},\n" for p in parts)
    return f"{output} = {var}.assign(\n{inner})"


def _indent(code: str, width: int) -> str:
    """Indent the continuation lines of a (wrapped) expression."""
    return code.replace("\n", "\n" + " " * width)


def assigned(
    stmt: ast.stmt, bound: Mapping[str, Any]
) -> tuple[str, str, list[tuple[str, ast.expr]]] | None:
    """`(output, input, [(name, value expr), ...])` of an `assign_code()` statement."""
    assign = base.assignment(stmt)
    if assign is None:
        return None
    output, value = assign
    if not (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "assign"
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id in bound
        and not value.args
        and value.keywords
    ):
        return None
    kwargs = _keywords(value.keywords)
    if kwargs is None:
        return None
    return output, value.func.value.id, list(kwargs.items())


def same_code(stmt: ast.stmt, code: str) -> bool:
    """Whether `code` (one statement) has the same syntax tree as `stmt`."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    return len(tree.body) == 1 and ast.dump(tree.body[0]) == ast.dump(stmt)


def confirm(
    op: type[base.Op], params: base.Params, inputs: Sequence[str], output: str, stmt: ast.stmt
) -> base.Match | None:
    """A match if the op regenerates exactly `stmt` from the recognised params."""
    if not same_code(stmt, op.to_code(params, inputs, output)):
        return None
    return base.Match(params, tuple(inputs), output)


@dataclass(frozen=True, slots=True)
class Link:
    """One link of a method chain: `.name`, `.name(args)` or `[key]`."""

    kind: Literal["attr", "call", "item"]
    name: str = ""
    args: tuple[ast.expr, ...] = ()
    kwargs: dict[str, ast.expr] = field(default_factory=dict)
    key: ast.expr | None = None

    def literal_args(self) -> tuple[list[Any], dict[str, Any]]:
        """Literal values of the call's arguments (ValueError if not literal)."""
        return [base.literal_value(a) for a in self.args], {
            k: base.literal_value(v) for k, v in self.kwargs.items()
        }


def unchain(expr: ast.expr) -> tuple[ast.expr, list[Link]] | None:
    """`df["a"].str.upper()` -> (Name df, [item "a", attr str, call upper]).

    None if a call has `*args` / `**kwargs`.
    """
    links: list[Link] = []
    node = expr
    while True:
        match node:
            case ast.Call(func=ast.Attribute(value=inner, attr=name), args=args, keywords=kws):
                if any(isinstance(a, ast.Starred) for a in args):
                    return None
                kwargs = _keywords(kws)
                if kwargs is None:
                    return None
                links.append(Link("call", name, tuple(args), kwargs))
                node = inner
            case ast.Attribute(value=inner, attr=name):
                links.append(Link("attr", name))
                node = inner
            case ast.Subscript(value=inner, slice=key):
                links.append(Link("item", key=key))
                node = inner
            case _:
                links.reverse()
                return node, links


def _keywords(keywords: Sequence[ast.keyword]) -> dict[str, ast.expr] | None:
    """Keyword arguments, `**{"a b": ...}` with literal string keys included."""
    kwargs: dict[str, ast.expr] = {}
    for kw in keywords:
        if kw.arg is not None:
            kwargs[kw.arg] = kw.value
        elif isinstance(kw.value, ast.Dict):
            for key, value in zip(kw.value.keys, kw.value.values):
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    return None
                kwargs[key.value] = value
        else:
            return None
    return kwargs


def column_of(node: ast.AST | None, var: str) -> str | None:
    """`"a"` for `var["a"]`."""
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == var
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    ):
        return node.slice.value
    return None


def chain_column(root: ast.expr, links: Sequence[Link], var: str) -> str | None:
    """`"a"` if a chain from `unchain()` starts with `var["a"]`."""
    if not (isinstance(root, ast.Name) and root.id == var and links and links[0].kind == "item"):
        return None
    key = links[0].key
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value
    return None


def item_key(link: Link) -> Any:
    """Literal key of an `item` link (ValueError if not literal)."""
    if link.kind != "item" or link.key is None:
        raise ValueError("not a subscript")
    return base.literal_value(link.key)


def frame_call(  # noqa: PLR0911
    stmt: ast.stmt, bound: Mapping[str, Any]
) -> tuple[str, str, list[str] | None, Link] | None:
    """`(output, var, columns, call)` of a frame call (`SeriesOp.frame_call`).

    `out = var.f(...)` (columns None) or `out = var.assign(**var[[...]].f(...))`.
    """
    assign = base.assignment(stmt)
    if assign is None:
        return None
    output, value = assign
    target = base.assign_target(value, bound)
    if target is not None:
        if target[1].arg is not None:
            return None
        value = target[1].value
    chain = unchain(value)
    if chain is None:
        return None
    root, links = chain
    if not (isinstance(root, ast.Name) and root.id in bound and links):
        return None
    if target is not None and root.id != target[0]:
        return None
    columns = None
    if target is not None and len(links) == 2:  # noqa: PLR2004
        try:
            columns = item_key(links[0])
        except ValueError:
            return None
    if len(links) != (1 if columns is None else 2) or links[-1].kind != "call":
        return None
    if target is not None and not isinstance(columns, list):
        return None
    return output, root.id, columns, links[-1]


# --- column ops --------------------------------------------------------------------------


class ColumnParams(base.Params):
    """Params of a `ColumnOp`: the columns to transform and where results go."""

    columns: list[str] = Field(
        title=N_("Columns"), min_length=1, json_schema_extra={"widget": "columns"}
    )
    suffix: str = Field(
        "",
        title=N_("Suffix for new columns"),
        description=N_("Empty: replace the columns. Otherwise the results are new columns."),
    )


SELECTION = ("columns", "column", "suffix")
"""Params of a `ColumnOp` that select the columns and name the results."""


class ColumnOp(base.Op):
    """The base of all per-column ops: one series per selected column, put back by `assign()`.

    The params select the columns with either `columns` (a list) or `column` (one name).
    Results replace the columns, or go to `<column><suffix>` if the params have a `suffix`
    field (`ColumnParams` has both). Subclasses implement `series()` (execution), `expr()`
    (its code) and `match_expr()` (recognise one expression: the column and the other params
    as a dict); `SeriesOp` derives all three from the declaration of one call.
    """

    Params: ClassVar[type[base.Params]] = ColumnParams

    @classmethod
    def series(cls, params: Any, frame: Frame, column: str) -> pd.Series:
        raise NotImplementedError

    @classmethod
    def expr(cls, params: Any, var: str, column: str) -> str:
        raise NotImplementedError

    @classmethod
    def match_expr(cls, node: ast.expr, var: str) -> tuple[str, dict[str, Any]] | None:
        raise NotImplementedError

    # --- column selection --------------------------------------------------------------
    @classmethod
    def selected(cls, params: Any) -> list[str] | None:
        """The selected columns; None = all (only `SeriesOp` with `frame_call`)."""
        if "column" in type(params).model_fields:
            return [params.column]
        return params.columns

    @classmethod
    def selection(cls, columns: list[str] | None, suffix: str = "") -> dict[str, Any] | None:
        """Params selecting `columns` with `suffix`; None if the params cannot express it."""
        fields = cls.Params.model_fields
        if suffix and "suffix" not in fields:
            return None
        if "column" in fields:
            return {"column": columns[0]} if columns is not None and len(columns) == 1 else None
        if columns is None and fields["columns"].is_required():
            return None
        values: dict[str, Any] = {"columns": columns}
        if "suffix" in fields:
            values["suffix"] = suffix
        return values

    @classmethod
    def results(cls, params: Any, columns: Sequence[str]) -> dict[str, str]:
        """Result column per selected column."""
        suffix = getattr(params, "suffix", "")
        return {c: f"{c}{suffix}" for c in columns}

    # --- op interface ------------------------------------------------------------------
    @classmethod
    def apply(cls, params: Any, *inputs: Frame) -> Frame:
        frame = inputs[0]
        columns = cls.selected(params)
        assert columns is not None
        missing = [c for c in columns if c not in frame.columns]
        if missing:
            raise base.OpError(f"unknown columns: {missing}")
        values = {}
        for column, name in cls.results(params, columns).items():
            try:
                values[name] = cls.series(params, frame, column)
            except AttributeError as e:  # e.g. `.cat` on a column that is not categorical
                raise base.OpError(f"{column}: {e}") from e
        return frame.assign(**values)

    @classmethod
    def to_code(cls, params: Any, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        columns = cls.selected(params)
        assert columns is not None
        values = {
            name: cls.expr(params, var, column)
            for column, name in cls.results(params, columns).items()
        }
        return assign_code(var, output, values)

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        found = assigned(stmt, bound)
        if found is None:
            return None
        output, var, pairs = found
        columns: list[str] = []
        suffixes: set[str] = set()
        options: list[dict[str, Any]] = []
        for name, node in pairs:
            try:
                matched = cls.match_expr(node, var)
            except ValueError:  # not literal: user code
                return None
            if matched is None or not name.startswith(matched[0]):
                return None
            columns.append(matched[0])
            suffixes.add(name[len(matched[0]) :])
            options.append(matched[1])
        if len(suffixes) != 1 or any(o != options[0] for o in options):
            return None
        selection = cls.selection(columns, suffixes.pop())
        if selection is None:
            return None
        params = cls.Params(**selection, **options[0])
        return confirm(cls, params, [var], output, stmt)


class SeriesOp(ColumnOp):
    """A `ColumnOp` that is one call per column, declared like `CallOp`.

    - `accessor` (`"str"`, `"dt"`, `"cat"` or None) + `method`: `df["a"].str.upper()`;
    - or `function` (dotted name; `pd` = pandas): `pd.to_datetime(df["a"], ...)`;
    - `method_param`: a param whose value picks the method (`methods` maps values to
      method names, default: the value itself); it is not passed to the call.

    Params in `positional` are passed positionally, the others as keywords when they differ
    from their default (or are listed in `always`). The selection params (`columns`,
    `column`, `suffix`) are never passed.

    `frame_call = True`: the method works on a frame column by column (`abs`, `clip`,
    `ffill`), so the code calls it once on the selected columns and puts the result back,
    `out = a.assign(**a[["x", "y"]].clip(lower=0))`, or on the whole frame when the
    `columns` field allows None (`out = a.ffill()`). No accessor, function or suffix then.
    """

    accessor: ClassVar[str | None] = None
    method: ClassVar[str | None] = None
    method_param: ClassVar[str | None] = None
    methods: ClassVar[Mapping[str, str]] = {}
    function: ClassVar[str | None] = None
    positional: ClassVar[tuple[str, ...]] = ()
    always: ClassVar[tuple[str, ...]] = ()
    frame_call: ClassVar[bool] = False

    @classmethod
    def method_name(cls, params: Any) -> str:
        if cls.method_param is not None:
            value = getattr(params, cls.method_param)
            return cls.methods.get(value, value)
        assert cls.method is not None
        return cls.method

    @classmethod
    def call_args(cls, params: Any) -> tuple[list[Any], dict[str, Any]]:
        skip = (*SELECTION, cls.method_param) if cls.method_param else SELECTION
        return base.call_arguments(params, cls.positional, cls.always, skip)

    @classmethod
    def call(cls, params: Any, obj: Any) -> Any:
        """The declared call on a series (or, with `frame_call`, a frame)."""
        args, kwargs = cls.call_args(params)
        if cls.function is not None:
            module, _sep, name = cls.function.rpartition(".")
            func = getattr(importlib.import_module({"pd": "pandas"}.get(module, module)), name)
            return func(obj, *args, **kwargs)
        if cls.accessor is not None:
            obj = getattr(obj, cls.accessor)
        return getattr(obj, cls.method_name(params))(*args, **kwargs)

    @classmethod
    def call_code(cls, params: Any, source: str, indent: int = 0) -> str:
        """Code of `call()` on the expression `source`."""
        args, kwargs = cls.call_args(params)
        if cls.function is not None:
            return base.format_call(
                cls.function, [source, *map(base.literal, args)], kwargs, indent
            )
        prefix = f"{source}.{cls.accessor}" if cls.accessor is not None else source
        func = f"{prefix}.{cls.method_name(params)}"
        return base.format_call(func, list(map(base.literal, args)), kwargs, indent)

    @classmethod
    def series(cls, params: Any, frame: Frame, column: str) -> pd.Series:
        return cls.call(params, frame[column])

    @classmethod
    def expr(cls, params: Any, var: str, column: str) -> str:
        return cls.call_code(params, column_code(var, column))

    @classmethod
    def apply(cls, params: Any, *inputs: Frame) -> Frame:
        if not cls.frame_call:
            return super().apply(params, *inputs)
        frame = inputs[0]
        columns = cls.selected(params)
        if columns is None:
            return cls.call(params, frame)
        missing = [c for c in columns if c not in frame.columns]
        if missing:
            raise base.OpError(f"unknown columns: {missing}")
        return frame.assign(**cls.call(params, frame[columns]))

    @classmethod
    def to_code(cls, params: Any, inputs: Sequence[str], output: str) -> str:
        if not cls.frame_call:
            return super().to_code(params, inputs, output)
        var = inputs[0]
        columns = cls.selected(params)
        if columns is None:
            return f"{output} = {cls.call_code(params, var, len(output) + 3)}"
        prefix = f"{output} = {var}.assign(**"
        call = cls.call_code(params, f"{var}[{base.literal(columns)}]", len(prefix))
        return f"{prefix}{call})"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        if not cls.frame_call:
            return super().from_code(stmt, bound)
        found = frame_call(stmt, bound)
        if found is None:
            return None
        output, var, columns, call = found
        options = cls._call_options(call)
        selection = cls.selection(columns)
        if options is None or selection is None:
            return None
        params = cls.Params(**selection, **options)
        return base.Match(params, (var,), output)  # like `CallOp`: `clip(upper=2)` is fine

    @classmethod
    def _call_options(cls, call: Link) -> dict[str, Any] | None:
        """The params (besides the selection) of a recognised call link; None if not this op."""
        options = cls._method_options(call.name)
        if options is None:
            return None
        try:
            args, kwargs = call.literal_args()
        except ValueError:  # not literal: user code
            return None
        if len(args) > len(cls.positional):
            return None
        if not set(kwargs) <= set(cls.Params.model_fields):
            return None  # like `CallOp`: `df.ffill(axis=1)` is user code
        options.update(zip(cls.positional, args))
        options.update(kwargs)
        return options

    @classmethod
    def _method_options(cls, name: str) -> dict[str, Any] | None:
        if cls.method_param is None:
            return {} if name == cls.method else None
        reverse = {v: k for k, v in cls.methods.items()}
        value = reverse.get(name, name)
        annotation = cls.Params.model_fields[cls.method_param].annotation
        annotation = getattr(annotation, "__value__", annotation)  # `type X = Literal[...]`
        if value not in typing.get_args(annotation):
            return None
        return {cls.method_param: value}

    @classmethod
    def match_expr(cls, node: ast.expr, var: str) -> tuple[str, dict[str, Any]] | None:  # noqa: PLR0911
        if cls.function is not None:
            if not (
                isinstance(node, ast.Call)
                and base.dotted_name(node.func) == cls.function
                and node.args
                and all(kw.arg is not None for kw in node.keywords)
            ):
                return None
            column = column_of(node.args[0], var)
            kwargs = {k.arg: k.value for k in node.keywords if k.arg}
            call = Link("call", "", tuple(node.args[1:]), kwargs)
            options: dict[str, Any] | None = {}
        else:
            chain = unchain(node)
            if chain is None:
                return None
            root, links = chain
            n = 3 if cls.accessor is not None else 2
            if len(links) != n or links[-1].kind != "call":
                return None
            column = chain_column(root, links, var)
            if cls.accessor is not None and links[1] != Link("attr", cls.accessor):
                return None
            call = links[-1]
            options = cls._method_options(call.name)
        if column is None or options is None:
            return None
        args, kwargs = call.literal_args()
        if len(args) > len(cls.positional):
            return None
        options.update(zip(cls.positional, args))
        options.update(kwargs)
        return column, options
