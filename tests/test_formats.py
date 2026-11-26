"""Format registry, readers / writers round trips, project files."""

import json
import sqlite3
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from datacook.engine import Session, parser, project
from datacook.engine.formats import FormatRegistry
from datacook.engine.ops import rows, sources


if TYPE_CHECKING:
    import pathlib


@pytest.fixture
def formats() -> FormatRegistry:
    return FormatRegistry()


def test_registry_lists_basic_formats(formats: FormatRegistry) -> None:
    by_id = {f.id: f for f in formats.formats()}
    assert set(by_id) >= {
        "csv",
        "parquet",
        "excel",
        "json",
        "feather",
        "clipboard",
        "sqlite",
        "script",
        "project",
    }
    assert by_id["csv"].reader is sources.ReadCsv
    assert by_id["csv"].writer is not None
    assert by_id["excel"].extra == "excel"
    assert by_id["sqlite"].writer is None
    assert formats.reader_for("a/b.PARQUET") is sources.ReadParquet
    assert formats.writer_for("x.py").id == "script"
    with pytest.raises(KeyError, match="no reader"):
        formats.reader_for("x.unknown")


@pytest.mark.parametrize("suffix", [".csv", ".parquet", ".xlsx"])
def test_write_read_roundtrip(
    suffix: str, frame, formats: FormatRegistry, session: Session, tmp_path: pathlib.Path
) -> None:
    src = session.add(sources.InlineData.record(data=frame.to_dict("list")))
    path = tmp_path / f"data{suffix}"
    formats.write(session, src.id, path)
    node = formats.read(session, path)
    result = session.materialize(node.id)
    assert result.columns.tolist() == frame.columns.tolist()
    assert result["k"].tolist() == frame["k"].tolist()
    assert result["s"].isna().tolist() == frame["s"].isna().tolist()
    assert all(isinstance(dt, pd.ArrowDtype) for dt in result.dtypes)
    # the generated code reads the file the same way
    namespace: dict = {}
    exec(session.code([node.id]), namespace)
    pd.testing.assert_frame_equal(namespace["df"], result)


def test_feather_and_json_readers(
    frame, formats: FormatRegistry, session: Session, tmp_path
) -> None:
    frame.to_feather(tmp_path / "a.feather")
    frame.to_json(tmp_path / "a.jsonl", orient="records", lines=True)
    feather = session.materialize(formats.read(session, tmp_path / "a.feather").id)
    pd.testing.assert_frame_equal(feather, frame)
    node = formats.read(session, tmp_path / "a.jsonl", lines=True)
    assert "lines=True" in session.code([node.id])
    assert session.materialize(node.id)["s"].tolist()[:2] == ["a", "b"]


def test_sqlite_reader(session: Session, tmp_path) -> None:
    db = tmp_path / "data.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE t (a INTEGER, b TEXT)")
        con.executemany("INSERT INTO t VALUES (?, ?)", [(1, "x"), (2, "y")])
    con.close()
    record = sources.ReadSqlite.record(path=str(db), query="SELECT * FROM t WHERE a > 1")
    node = session.add(record)
    assert session.materialize(node.id).to_dict("list") == {"a": [2], "b": ["y"]}
    text = session.code([node.id])
    assert "import sqlite3" in text
    assert parser.parse(text, session.registry).records == [record]


def test_clipboard_reader(session: Session, monkeypatch) -> None:
    calls = []

    def fake_read_clipboard(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame({"a": [1]})

    monkeypatch.setattr(pd, "read_clipboard", fake_read_clipboard)
    node = session.add(sources.ReadClipboard.record())
    assert session.materialize(node.id)["a"].tolist() == [1]
    assert calls == [{"dtype_backend": "pyarrow"}]
    text = session.code([node.id])
    assert 'df = pd.read_clipboard(dtype_backend="pyarrow")' in text
    assert parser.parse(text, session.registry).records == [node.record]


def test_reader_code_roundtrip(session: Session) -> None:
    for record in [
        sources.ReadCsv.record(path="x.csv", sep=";", decimal=","),
        sources.ReadParquet.record(path="x.parquet", columns=["a"]),
        sources.ReadFeather.record(path="x.arrow"),
        sources.ReadJson.record(path="x.json", orient="records"),
        sources.ReadExcel.record(path="x.xlsx", sheet_name="Data"),
    ]:
        node = session.add(record)
        assert parser.parse(session.code([node.id]), session.registry).records == [record]
    assert 'pd.read_csv("x.csv", sep=";", decimal=",", dtype_backend="pyarrow")' in session.code()


def test_script_writer(frame, formats: FormatRegistry, session: Session, tmp_path) -> None:
    src = session.add(sources.InlineData.record(data=frame.to_dict("list")))
    head = session.add(rows.Head.record(n=2), [src])
    formats.write(session, head.id, tmp_path / "out.py")
    namespace: dict = {}
    exec((tmp_path / "out.py").read_text(), namespace)
    pd.testing.assert_frame_equal(namespace["df"], session.materialize(head.id))


def test_project_roundtrip(frame, formats: FormatRegistry, session: Session, tmp_path) -> None:
    frame.to_csv(tmp_path / "in.csv", index=False)
    src = formats.read(session, tmp_path / "in.csv")
    a = session.add(rows.SortRows.record(by=["x"]), [src], name="sorted", comment="by x")
    session.add(rows.Head.record(n=2), [a])
    path = tmp_path / "p.datacook"
    formats.write(session, a.id, path)
    data = json.loads(path.read_text())
    assert data["format"] == "datacook-project"
    assert data["version"] == project.VERSION
    assert data["nodes"][1]["op"] == "sort_rows"
    with Session() as loaded:
        project.load(loaded, path)
        assert loaded.nodes() == session.nodes()
        assert loaded.code() == session.code()
        last = loaded.nodes()[-1].id
        pd.testing.assert_frame_equal(loaded.materialize(last), session.materialize(last))


def test_project_errors(session: Session) -> None:
    with pytest.raises(project.ProjectError, match="not a DataCook"):
        project.from_dict(session, {"format": "x"})
    with pytest.raises(project.ProjectError, match="version"):
        project.from_dict(session, {"format": project.FORMAT, "version": 99, "nodes": []})
    bad = {"format": project.FORMAT, "version": 1, "nodes": [{"id": "a", "op": "nope"}]}
    with pytest.raises(project.ProjectError, match="nope"):
        project.from_dict(session, bad)
