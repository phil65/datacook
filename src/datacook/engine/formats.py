"""Format registry: file extension -> reader op / writer, with Params model and extra.

Readers are source ops (`datacook.ops`, `n_inputs = 0`, with `extensions`), so a file read
is an ordinary root node and appears in the generated code. Writers (`datacook.writers`)
export a node: its frame (CSV, Parquet, Excel) or the session (script, project).
"""

from dataclasses import dataclass
import functools
import importlib.util
import pathlib
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field

from datacook.engine.ops import Params as BaseParams, default_ops
from datacook.engine.registry import WRITERS_GROUP, Registry
from datacook.i18n import N_, LazyText, _


if TYPE_CHECKING:
    from datacook.engine.ops import Op
    from datacook.engine.session import Session


class Writer:
    id: ClassVar[str]
    title: ClassVar[LazyText]
    extensions: ClassVar[tuple[str, ...]]
    Params: ClassVar[type[BaseParams]]
    requires: ClassVar[tuple[str, ...]] = ()
    extra: ClassVar[str | None] = None

    @classmethod
    def write(cls, session: Session, node_id: str, path: str | pathlib.Path, params: Any) -> None:
        raise NotImplementedError

    @classmethod
    def available(cls) -> bool:
        return all(importlib.util.find_spec(mod) is not None for mod in cls.requires)


class _FrameWriter(Writer):
    method: ClassVar[str]

    @classmethod
    def write(cls, session: Session, node_id: str, path: str | pathlib.Path, params: Any) -> None:
        frame = session.materialize(node_id)
        getattr(frame, cls.method)(path, **params.model_dump())


class WriteCsv(_FrameWriter):
    id = "csv"
    title = _("CSV file")
    extensions = (".csv", ".txt")
    method = "to_csv"

    class Params(BaseParams):
        sep: str = Field(",", title=N_("Separator"))
        decimal: str = Field(".", title=N_("Decimal separator"))
        index: bool = Field(False, title=N_("Write index"))


class WriteParquet(_FrameWriter):
    id = "parquet"
    title = _("Parquet file")
    extensions = (".parquet", ".pq")
    method = "to_parquet"

    class Params(BaseParams):
        compression: str | None = Field("snappy", title=N_("Compression"))
        index: bool | None = Field(None, title=N_("Write index"))


class WriteExcel(_FrameWriter):
    id = "excel"
    title = _("Excel file")
    extensions = (".xlsx",)
    method = "to_excel"
    requires = ("openpyxl",)
    extra = "excel"

    class Params(BaseParams):
        sheet_name: str = Field("Sheet1", title=N_("Sheet"))
        index: bool = Field(False, title=N_("Write index"))


class WriteScript(Writer):
    """The generated Python script for the node (or the whole tree)."""

    id = "script"
    title = _("Python script")
    extensions = (".py",)

    class Params(BaseParams):
        whole_tree: bool = Field(False, title=N_("Whole tree"))

    @classmethod
    def write(cls, session: Session, node_id: str, path: str | pathlib.Path, params: Any) -> None:
        code = session.code(None if params.whole_tree else [node_id])
        pathlib.Path(path).write_text(code, encoding="utf-8")


class WriteProject(Writer):
    """The whole session as a project file."""

    id = "project"
    title = _("DataCook project")
    extensions = (".datacook",)

    class Params(BaseParams):
        pass

    @classmethod
    def write(cls, session: Session, node_id: str, path: str | pathlib.Path, params: Any) -> None:
        from datacook.engine import project

        project.save(session, path)


@functools.cache
def default_writers() -> Registry[type[Writer]]:
    return Registry[type[Writer]](WRITERS_GROUP)


@dataclass(frozen=True, slots=True)
class Format:
    """One entry of the format registry (a reader and/or a writer for some extensions)."""

    id: str
    title: str
    extensions: tuple[str, ...]
    reader: type[Op] | None
    writer: type[Writer] | None

    @property
    def extra(self) -> str | None:
        for part in (self.reader, self.writer):
            if part is not None and part.extra:
                return part.extra
        return None

    def available(self) -> bool:
        return all(x.available() for x in (self.reader, self.writer) if x is not None)


class FormatRegistry:
    def __init__(
        self,
        ops: Registry[type[Op]] | None = None,
        writers: Registry[type[Writer]] | None = None,
    ) -> None:
        self.ops = ops if ops is not None else default_ops()
        self.writers = writers if writers is not None else default_writers()

    def readers(self) -> list[type[Op]]:
        return [op for op in self.ops if op.n_inputs == 0 and getattr(op, "format_id", "")]

    def formats(self) -> list[Format]:
        result: dict[str, Format] = {}
        for op in self.readers():
            fid = getattr(op, "format_id", "")
            exts = getattr(op, "extensions", ())
            result[fid] = Format(fid, str(op.title), exts, op, None)
        for writer in self.writers:
            current = result.get(writer.id)
            if current is None:
                result[writer.id] = Format(
                    writer.id, str(writer.title), writer.extensions, None, writer
                )
            else:
                exts = tuple(dict.fromkeys((*current.extensions, *writer.extensions)))
                result[writer.id] = Format(current.id, current.title, exts, current.reader, writer)
        return list(result.values())

    def reader_for(self, path: str | pathlib.Path) -> type[Op]:
        suffix = pathlib.Path(path).suffix.lower()
        for op in self.readers():
            if suffix in getattr(op, "extensions", ()):
                return op
        msg = f"no reader for {suffix!r} files"
        raise KeyError(msg)

    def writer_for(self, path: str | pathlib.Path) -> type[Writer]:
        suffix = pathlib.Path(path).suffix.lower()
        for writer in self.writers:
            if suffix in writer.extensions:
                return writer
        msg = f"no writer for {suffix!r} files"
        raise KeyError(msg)

    def read(self, session: Session, path: str | pathlib.Path, **options: Any):
        """Add a reader node for `path` (reader chosen by extension)."""
        op = self.reader_for(path)
        return session.add(op.record(path=str(path), **options))

    def write(
        self,
        session: Session,
        node_id: str,
        path: str | pathlib.Path,
        **options: Any,
    ) -> None:
        writer = self.writer_for(path)
        writer.write(session, node_id, path, writer.Params(**options))
