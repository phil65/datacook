"""Source ops (no inputs): file readers, clipboard, SQLite, inline data.

Readers default to pyarrow-backed dtypes (`dtype_backend="pyarrow"`): arrow strings and
nullable numbers use about half the memory of numpy object columns.
"""

import ast
import contextlib
import math
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import Field, field_validator

from datacook.engine import categories
from datacook.engine.ops import base
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from datacook.engine.frames import Frame


type DtypeBackend = Literal["pyarrow", "numpy_nullable"]


class ReadOp(base.CallOp):
    """A reader: a source op with file extensions (the format registry looks them up)."""

    n_inputs = 0
    category = categories.SOURCE
    icon = "mdi.file-table-outline"
    positional: ClassVar[tuple[str, ...]] = ("path",)
    always: ClassVar[tuple[str, ...]] = ("dtype_backend",)
    extensions: ClassVar[tuple[str, ...]] = ()
    format_id: ClassVar[str] = ""


class ReadCsv(ReadOp):
    id = "read_csv"
    format_id = "csv"
    title = _("CSV file")
    description = _("Read a comma separated values file.")
    function = "pd.read_csv"
    extensions = (".csv", ".tsv", ".txt")

    class Params(base.Params):
        path: str = Field(title=N_("File"), json_schema_extra={"widget": "file"})
        sep: str | None = Field(",", title=N_("Separator"))
        decimal: str = Field(".", title=N_("Decimal separator"))
        encoding: str | None = Field(None, title=N_("Encoding"))
        skiprows: int | None = Field(None, title=N_("Skip rows"), ge=0)
        dtype_backend: DtypeBackend = Field("pyarrow", title=N_("Data types"))


class ReadParquet(ReadOp):
    id = "read_parquet"
    format_id = "parquet"
    title = _("Parquet file")
    description = _("Read an Apache Parquet file.")
    function = "pd.read_parquet"
    extensions = (".parquet", ".pq")

    class Params(base.Params):
        path: str = Field(title=N_("File"), json_schema_extra={"widget": "file"})
        columns: list[str] | None = Field(None, title=N_("Columns"))
        dtype_backend: DtypeBackend = Field("pyarrow", title=N_("Data types"))


class ReadFeather(ReadOp):
    id = "read_feather"
    format_id = "feather"
    title = _("Feather / Arrow IPC file")
    description = _("Read an Arrow IPC (Feather v2) file.")
    function = "pd.read_feather"
    extensions = (".feather", ".arrow", ".ipc")

    class Params(base.Params):
        path: str = Field(title=N_("File"), json_schema_extra={"widget": "file"})
        columns: list[str] | None = Field(None, title=N_("Columns"))
        dtype_backend: DtypeBackend = Field("pyarrow", title=N_("Data types"))


class ReadJson(ReadOp):
    id = "read_json"
    format_id = "json"
    title = _("JSON file")
    description = _("Read a JSON file (records, columns, ... or JSON lines).")
    function = "pd.read_json"
    extensions = (".json", ".jsonl", ".ndjson")

    class Params(base.Params):
        path: str = Field(title=N_("File"), json_schema_extra={"widget": "file"})
        orient: Literal["split", "records", "index", "columns", "values", "table"] | None = Field(
            None, title=N_("Layout")
        )
        lines: bool = Field(False, title=N_("JSON lines"))
        dtype_backend: DtypeBackend = Field("pyarrow", title=N_("Data types"))


class ReadExcel(ReadOp):
    id = "read_excel"
    format_id = "excel"
    title = _("Excel file")
    description = _("Read a sheet of an Excel workbook.")
    function = "pd.read_excel"
    extensions = (".xlsx", ".xlsm")
    requires = ("openpyxl",)
    extra = "excel"

    class Params(base.Params):
        path: str = Field(title=N_("File"), json_schema_extra={"widget": "file"})
        sheet_name: str | int = Field(0, title=N_("Sheet"))
        skiprows: int | None = Field(None, title=N_("Skip rows"), ge=0)
        dtype_backend: DtypeBackend = Field("pyarrow", title=N_("Data types"))


class ReadClipboard(ReadOp):
    id = "read_clipboard"
    format_id = "clipboard"
    title = _("Clipboard")
    description = _("Read a table from the clipboard (e.g. copied from a spreadsheet).")
    icon = "mdi.clipboard-text-outline"
    function = "pd.read_clipboard"
    positional = ()

    class Params(base.Params):
        sep: str = Field(r"\s+", title=N_("Separator"))
        dtype_backend: DtypeBackend = Field("pyarrow", title=N_("Data types"))


class ReadSqlite(base.Op):
    """`pd.read_sql_query(query, sqlite3.connect(path))`."""

    id = "read_sqlite"
    title = _("SQLite database")
    description = _("Run a query against a SQLite database file.")
    category = categories.SOURCE
    icon = "mdi.database-search-outline"
    n_inputs = 0
    imports = ("import sqlite3", "import pandas as pd")
    extensions: ClassVar[tuple[str, ...]] = (".sqlite", ".sqlite3", ".db")
    format_id: ClassVar[str] = "sqlite"

    class Params(base.Params):
        path: str = Field(title=N_("File"), json_schema_extra={"widget": "file"})
        query: str = Field(title=N_("Query"), examples=["SELECT * FROM my_table"])
        dtype_backend: DtypeBackend = Field("pyarrow", title=N_("Data types"))

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import sqlite3

        import pandas as pd

        with contextlib.closing(sqlite3.connect(params.path)) as con:
            return pd.read_sql_query(params.query, con, dtype_backend=params.dtype_backend)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        con = f"sqlite3.connect({base.literal(params.path)})"
        args = [base.literal(params.query), con]
        call = base.format_call(
            "pd.read_sql_query", args, {"dtype_backend": params.dtype_backend}, len(output) + 3
        )
        return f"{output} = {call}"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if not (
            isinstance(value, ast.Call)
            and base.dotted_name(value.func) == "pd.read_sql_query"
            and len(value.args) == 2  # noqa: PLR2004
        ):
            return None
        con = value.args[1]
        if not (
            isinstance(con, ast.Call)
            and base.dotted_name(con.func) == "sqlite3.connect"
            and len(con.args) == 1
        ):
            return None
        try:
            query = base.literal_value(value.args[0])
            path = base.literal_value(con.args[0])
            kwargs = {kw.arg: base.literal_value(kw.value) for kw in value.keywords if kw.arg}
        except ValueError:
            return None
        return base.Match(cls.Params(path=path, query=query, **kwargs), (), output)


class InlineData(base.Op):
    """A small table typed in (or pasted) by the user, stored in the project."""

    id = "inline_data"
    title = _("Table data")
    description = _("A table given as columns of values.")
    category = categories.SOURCE
    icon = "mdi.table-edit"
    n_inputs = 0

    class Params(base.Params):
        data: dict[str, list[Any]] = Field(title=N_("Columns"))

        @field_validator("data", mode="before")
        @classmethod
        def _missing_to_none(cls, data: Any) -> Any:
            """NaN / pd.NA -> None (missing values in the generated literal)."""
            import pandas as pd

            if not isinstance(data, dict):
                return data
            return {
                k: [
                    None if v is pd.NA or (isinstance(v, float) and math.isnan(v)) else v
                    for v in col
                ]
                if isinstance(col, list)
                else col
                for k, col in data.items()
            }

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import pandas as pd

        return pd.DataFrame(params.data).convert_dtypes(dtype_backend="pyarrow")

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        data = base.literal(params.data)
        return f'{output} = pd.DataFrame({data}).convert_dtypes(dtype_backend="pyarrow")'

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "convert_dtypes"
            and isinstance(value.func.value, ast.Call)
            and base.dotted_name(value.func.value.func) == "pd.DataFrame"
            and len(value.func.value.args) == 1
        ):
            return None
        try:
            data = base.literal_value(value.func.value.args[0])
        except ValueError:
            return None
        return base.Match(cls.Params(data=data), (), output)
