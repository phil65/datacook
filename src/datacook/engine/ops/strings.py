"""Text ops (`.str` methods).

Case, strip, replace, slice, pad, length, repeat, test, filter rows, extract, split.
Joining columns as text is "Combine columns" (`ops/columns.py`).
"""

import ast
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import Field, model_validator

from datacook.engine import categories
from datacook.engine.ops import base, series
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import pandas as pd

    from datacook.engine.frames import Frame


class TextOp(series.SeriesOp):
    category = categories.TEXT
    accessor = "str"


class ChangeCase(TextOp):
    id = "str_case"
    title = _("Change case")
    description = _("Upper case, lower case, capitalize, title case, ... of text columns.")
    icon = "mdi.format-letter-case"
    method_param = "case"

    class Params(series.ColumnParams):
        case: Literal["upper", "lower", "capitalize", "title", "swapcase", "casefold"] = Field(
            "upper", title=N_("Case")
        )


class Strip(TextOp):
    id = "str_strip"
    title = _("Strip text")
    description = _("Remove whitespace (or the given characters) at the start and end of text.")
    icon = "mdi.format-align-justify"
    method_param = "side"
    methods = {"both": "strip", "left": "lstrip", "right": "rstrip"}  # noqa: RUF012

    class Params(series.ColumnParams):
        side: Literal["both", "left", "right"] = Field("both", title=N_("Side"))
        to_strip: str | None = Field(
            None,
            title=N_("Characters"),
            description=N_("Characters to remove (any order). Empty: whitespace."),
        )


class Replace(TextOp):
    id = "str_replace"
    title = _("Replace text")
    description = _("Replace a text or a regular expression in text columns.")
    icon = "mdi.find-replace"
    method = "replace"
    positional = ("pat", "repl")

    class Params(series.ColumnParams):
        pat: str = Field(title=N_("Search for"), min_length=1)
        repl: str = Field("", title=N_("Replace with"))
        regex: bool = Field(
            False,
            title=N_("Regular expression"),
            description=N_("Groups can be used in the replacement as \\1, \\2, ..."),
        )
        case: bool | None = Field(None, title=N_("Case sensitive"))
        n: int = Field(-1, title=N_("Replacements per cell"), ge=-1, description=N_("-1: all"))


class Slice(TextOp):
    id = "str_slice"
    title = _("Slice text")
    description = _(
        "Keep the characters from start to stop (Python slice, negative = from the end)."
    )
    icon = "mdi.content-cut"
    method = "slice"

    class Params(series.ColumnParams):
        start: int | None = Field(None, title=N_("Start"))
        stop: int | None = Field(None, title=N_("Stop"))
        step: int | None = Field(None, title=N_("Step"))


class Pad(TextOp):
    id = "str_pad"
    title = _("Pad text")
    description = _("Fill text up to a minimum width (e.g. leading zeros).")
    icon = "mdi.format-indent-increase"
    method = "pad"
    positional = ("width",)

    class Params(series.ColumnParams):
        width: int = Field(title=N_("Width"), ge=0)
        side: Literal["left", "right", "both"] = Field("left", title=N_("Side"))
        fillchar: str = Field(" ", title=N_("Fill character"), min_length=1, max_length=1)


class Length(TextOp):
    id = "str_len"
    title = _("Text length")
    description = _("Number of characters of each text.")
    icon = "mdi.counter"
    method = "len"

    class Params(series.ColumnParams):
        suffix: str = Field(
            "_len",
            title=N_("Suffix for new columns"),
            description=N_("Empty: replace the columns. Otherwise the results are new columns."),
        )


class Repeat(TextOp):
    id = "str_repeat"
    title = _("Repeat text")
    description = _("Repeat each text n times.")
    icon = "mdi.repeat"
    method = "repeat"
    positional = ("repeats",)

    class Params(series.ColumnParams):
        repeats: int = Field(2, title=N_("Repeats"), ge=0)


type TestMode = Literal["contains", "startswith", "endswith", "match", "fullmatch"]


class _TestOptions(base.Params):
    """Shared by "Test text" and "Filter rows by text"."""

    mode: TestMode = Field("contains", title=N_("Test"))
    pat: str = Field(title=N_("Pattern"), min_length=1)
    case: bool = Field(True, title=N_("Case sensitive"))
    regex: bool = Field(
        True,
        title=N_("Regular expression"),
        description=N_("Only for 'contains'; 'match' and 'fullmatch' always use one."),
    )

    @model_validator(mode="after")
    def _check_mode(self) -> Self:
        if self.mode in ("startswith", "endswith") and not self.case:
            raise ValueError("startswith / endswith are always case sensitive")
        if self.mode != "contains" and not self.regex:
            raise ValueError("only 'contains' can switch off regular expressions")
        return self


def _test_kwargs(params: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if not params.case:
        kwargs["case"] = False
    if not params.regex:
        kwargs["regex"] = False
    return kwargs


class Test(TextOp):
    id = "str_test"
    title = _("Test text")
    description = _("True / False per cell: contains, starts with, ends with or matches a pattern.")
    icon = "mdi.text-search"
    method_param = "mode"
    positional = ("pat",)

    class Params(series.ColumnParams, _TestOptions):
        suffix: str = Field(
            "_match",
            title=N_("Suffix for new columns"),
            description=N_("Empty: replace the columns. Otherwise the results are new columns."),
        )


class FilterText(base.Op):
    id = "filter_text"
    title = _("Filter rows by text")
    description = _("Keep the rows whose text contains, starts with, ... a pattern.")
    category = categories.FILTER
    icon = "mdi.filter-variant"

    class Params(_TestOptions):
        column: str = Field(title=N_("Column"), json_schema_extra={"widget": "column"})
        invert: bool = Field(False, title=N_("Keep the other rows"))

    @classmethod
    def _mask(cls, params: Params, column: pd.Series) -> pd.Series:
        kwargs = _test_kwargs(params)
        return getattr(column.str, params.mode)(params.pat, **kwargs, na=False)

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        mask = cls._mask(params, frame[params.column])
        return frame[~mask if params.invert else mask]

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        func = f"{series.column_code(var, params.column)}.str.{params.mode}"
        mask = base.format_call(
            func, [base.literal(params.pat)], {**_test_kwargs(params), "na": False}
        )
        return f"{output} = {var}[{'~' if params.invert else ''}{mask}]"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:  # noqa: PLR0911
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if not (isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name)):
            return None
        var = value.value.id
        if var not in bound:
            return None
        mask = value.slice
        invert = isinstance(mask, ast.UnaryOp) and isinstance(mask.op, ast.Invert)
        if isinstance(mask, ast.UnaryOp) and invert:
            mask = mask.operand
        chain = series.unchain(mask)
        if chain is None:
            return None
        column = series.chain_column(*chain, var)
        links = chain[1]
        if column is None or len(links) != 3 or links[1] != series.Link("attr", "str"):  # noqa: PLR2004
            return None
        call = links[2]
        try:
            args, kwargs = call.literal_args()
        except ValueError:
            return None
        if call.kind != "call" or len(args) != 1 or kwargs.pop("na", None) is not False:
            return None
        params = cls.Params(
            column=column,
            mode=call.name,  # ty: ignore[invalid-argument-type]
            pat=args[0],
            invert=invert,
            **kwargs,
        )
        return series.confirm(cls, params, [var], output, stmt)


class _ExpandOp(base.Op):
    """Text -> several new columns: `df.join(df["a"].str.<method>(...).add_prefix("a_"))`."""

    category = categories.TEXT
    method: str

    @classmethod
    def call(cls, params: Any) -> tuple[list[Any], dict[str, Any]]:
        raise NotImplementedError

    @classmethod
    def prefix(cls, params: Any) -> str:
        return f"{params.column}_" if params.prefix is None else params.prefix

    @classmethod
    def apply(cls, params: Any, *inputs: Frame) -> Frame:
        frame = inputs[0]
        args, kwargs = cls.call(params)
        parts = getattr(frame[params.column].str, cls.method)(*args, **kwargs)
        if prefix := cls.prefix(params):
            parts = parts.add_prefix(prefix)
        return frame.join(parts)

    @classmethod
    def to_code(cls, params: Any, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        args, kwargs = cls.call(params)
        func = f"{series.column_code(var, params.column)}.str.{cls.method}"
        parts = base.format_call(func, list(map(base.literal, args)), kwargs)
        if prefix := cls.prefix(params):
            parts += f".add_prefix({base.literal(prefix)})"
        return f"{output} = {var}.join({parts})"

    @classmethod
    def params_from(cls, column: str, args: list[Any], kwargs: dict[str, Any], prefix: str) -> Any:
        raise NotImplementedError

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:  # noqa: PLR0911
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        outer = series.unchain(value)
        if outer is None:
            return None
        root, links = outer
        if not (
            isinstance(root, ast.Name)
            and root.id in bound
            and len(links) == 1
            and links[0].kind == "call"
            and links[0].name == "join"
            and len(links[0].args) == 1
            and not links[0].kwargs
        ):
            return None
        var = root.id
        inner = series.unchain(links[0].args[0])
        if inner is None:
            return None
        column = series.chain_column(*inner, var)
        parts = inner[1]
        if column is None or len(parts) not in (3, 4) or parts[1] != series.Link("attr", "str"):
            return None
        call = parts[2]
        if call.kind != "call" or call.name != cls.method:
            return None
        try:
            args, kwargs = call.literal_args()
            prefix = ""
            if len(parts) == 4:  # noqa: PLR2004
                add = parts[3]
                prefix_args, prefix_kwargs = add.literal_args()
                if add.name != "add_prefix" or len(prefix_args) != 1 or prefix_kwargs:
                    return None
                prefix = prefix_args[0]
        except ValueError:
            return None
        params = cls.params_from(column, args, kwargs, prefix)
        return series.confirm(cls, params, [var], output, stmt)


def _prefix_param(prefix: str, column: str) -> str | None:
    return None if prefix == f"{column}_" else prefix


class Extract(_ExpandOp):
    id = "str_extract"
    title = _("Extract with regular expression")
    description = _(
        "New columns from the groups of a regular expression; named groups (?P<name>...) "
        "name the columns."
    )
    icon = "mdi.regex"
    method = "extract"

    class Params(base.Params):
        column: str = Field(title=N_("Column"), json_schema_extra={"widget": "column"})
        pat: str = Field(
            title=N_("Regular expression"), min_length=1, examples=[r"(?P<number>\d+)\s?kW"]
        )
        prefix: str | None = Field(
            None,
            title=N_("Prefix of the new columns"),
            description=N_("Default: the column name and '_'."),
        )

    @classmethod
    def call(cls, params: Params) -> tuple[list[Any], dict[str, Any]]:
        return [params.pat], {}

    @classmethod
    def params_from(
        cls, column: str, args: list[Any], kwargs: dict[str, Any], prefix: str
    ) -> Params:
        if len(args) != 1 or kwargs:
            msg = "extract: expected only the pattern"
            raise ValueError(msg)
        return cls.Params(column=column, pat=args[0], prefix=_prefix_param(prefix, column))


class Split(_ExpandOp):
    id = "str_split"
    title = _("Split text into columns")
    description = _("Split text at a separator into new columns.")
    icon = "mdi.call-split"
    method = "split"

    class Params(base.Params):
        column: str = Field(title=N_("Column"), json_schema_extra={"widget": "column"})
        pat: str | None = Field(None, title=N_("Separator"), description=N_("Empty: whitespace."))
        n: int = Field(-1, title=N_("Maximum splits"), ge=-1, description=N_("-1: all"))
        regex: bool = Field(False, title=N_("Regular expression"))
        prefix: str | None = Field(
            None,
            title=N_("Prefix of the new columns"),
            min_length=1,
            description=N_("Default: the column name and '_'."),
        )

    @classmethod
    def call(cls, params: Params) -> tuple[list[Any], dict[str, Any]]:
        args = [] if params.pat is None else [params.pat]
        kwargs: dict[str, Any] = {}
        if params.n != -1:
            kwargs["n"] = params.n
        if params.regex:
            kwargs["regex"] = True
        kwargs["expand"] = True
        return args, kwargs

    @classmethod
    def params_from(
        cls, column: str, args: list[Any], kwargs: dict[str, Any], prefix: str
    ) -> Params:
        if kwargs.pop("expand", None) is not True or len(args) > 1:
            msg = "split: expected expand=True"
            raise ValueError(msg)
        return cls.Params(
            column=column,
            pat=args[0] if args else None,
            prefix=_prefix_param(prefix, column),
            **kwargs,
        )
