"""Whole-tree / path scripts and parsing them back."""

import pandas as pd
import pytest

from datacook.engine import Session, codegen, parser
from datacook.engine.node import Node
from datacook.engine.ops import base, code, columns, combine, missing, rows, sources
from datacook.i18n import _


@pytest.fixture
def tree(session: Session):
    src = session.add(
        sources.InlineData.record(data={"k": [1, 2, 3, 1], "x": [1.5, None, 3.0, 4.0]}),
        name="raw",
    )
    sort = session.add(rows.SortRows.record(by=["x"], ascending=False), [src])
    fill = session.add(missing.FillForward.record(), [sort])
    ren = session.add(columns.RenameColumns.record(columns={"x": "y"}), [src], name="Renamed")
    merged = session.add(combine.Merge.record(how="left", on=["k"]), [fill, ren])
    custom = session.add(code.CustomCode.record(code='df["z"] = df["k"] * 2'), [merged])
    agg = session.add(
        combine.GroupByAggregate.record(by=["k"], aggregations=[{"column": "z", "func": "sum"}]),
        [custom],
    )
    return {n: session[node.id] for n, node in locals().items() if hasattr(node, "record")}


TREE_SCRIPT = """\
import numpy as np
import pandas as pd

# raw
df_raw = pd.DataFrame({"k": [1, 2, 3, 1], "x": [1.5, None, 3.0, 4.0]}).convert_dtypes(dtype_backend="pyarrow")

# Sort rows
df = df_raw.sort_values(by=["x"], ascending=False)

# Fill forward
df = df.ffill()

# Renamed
df_renamed = df_raw.rename(columns={"x": "y"})

# Merge
df = df.merge(df_renamed, how="left", on=["k"])

# Custom code
df["z"] = df["k"] * 2

# Group and aggregate
df = df.groupby(["k"], as_index=False).agg(z_sum=("z", "sum"))
"""  # noqa: E501


def test_tree_script_golden(session: Session, tree) -> None:
    assert session.code() == TREE_SCRIPT


def test_script_spans(session: Session, tree) -> None:
    multi = session.add(
        code.CustomCode.record(code='df["a"] = 1\ndf["b"] = 2'), [tree["agg"]], name="two lines"
    )
    script = session.render_code()
    lines = script.text.splitlines()
    assert script.text == session.code()
    assert list(script.spans) == [n.id for n in session.nodes()]
    assert script.spans[tree["src"].id] == (4, 5)
    assert script.spans[tree["sort"].id] == (7, 8)
    assert script.spans[multi.id] == (len(lines) - 2, len(lines))
    for node in session.nodes():
        first, last = script.spans[node.id]
        assert lines[first - 1].startswith("# ")
        assert lines[last - 1]
        assert last == len(lines) or not lines[last]  # a blank line follows each block
    # a subset keeps spans consistent with its own text
    sub = session.render_code([tree["ren"].id])
    assert sub.spans == {tree["src"].id: (3, 4), tree["ren"].id: (6, 7)}
    assert (
        codegen.script_spans({n.id: n for n in session.nodes()}, session.registry, [tree["ren"].id])
        == sub.spans
    )


def test_script_spans_without_imports() -> None:
    class Constant(base.Op):
        id = "test_constant"
        title = _("Constant")
        n_inputs = 0
        imports = ()

        @classmethod
        def to_code(cls, params, inputs, output) -> str:
            return f"{output} = 1"

    node = Node("n1", Constant.record())
    registry = {Constant.id: Constant}
    script = codegen.render({node.id: node}, registry)  # ty: ignore[invalid-argument-type]
    assert script.text == "# Constant\ndf = 1\n"
    assert script.spans == {"n1": (1, 2)}


def test_script_reproduces_every_node(session: Session, tree) -> None:
    for node in session.nodes():
        namespace: dict = {}
        exec(session.code([node.id]), namespace)
        last = parser.parse(session.code([node.id]), session.registry).steps[-1].output
        pd.testing.assert_frame_equal(namespace[last], session.materialize(node.id))


def test_branches_get_own_variables(session: Session, tree) -> None:
    head = session.add(rows.Head.record(n=2), [tree["sort"]])
    text = session.code()
    # the sort result feeds two steps now: both branches get their own variable
    assert "df = df_raw.sort_values" in text
    assert "df2 = df.ffill()" in text
    assert "df3 = df.head(2)" in text
    namespace: dict = {}
    exec(text, namespace)
    out = parser.parse(text, session.registry)
    for step, node in zip(out.steps, session.nodes(), strict=True):
        assert step.record == node.record
    pd.testing.assert_frame_equal(namespace["df2"], session.materialize(tree["agg"].id))
    pd.testing.assert_frame_equal(namespace["df3"], session.materialize(head.id))


def test_parse_rebuilds_tree(session: Session, tree) -> None:
    text = session.code()
    with Session() as other:
        created = other.import_script(text)
        assert [n.record for n in created] == [n.record for n in session.nodes()]
        index = {n.id: i for i, n in enumerate(session.nodes())}
        assert [tuple(created.index(other[p]) for p in n.parents) for n in created] == [
            tuple(index[p] for p in n.parents) for n in session.nodes()
        ]
        assert [n.name for n in created] == [n.name for n in session.nodes()]
        assert other.code() == text


def test_unknown_statements_become_custom_code(session: Session) -> None:
    text = (
        "import pandas as pd\n\n"
        'df = pd.DataFrame({"a": [3, 1, 2]}).convert_dtypes(dtype_backend="pyarrow")\n'
        'df = df.sort_values(by=["a"])\n\n'
        "# my step\n"
        'df["b"] = df["a"] + 1\n'
        "df = df.head(2)  # mixed block: one custom step\n\n"
        "df = df.head(1)\n"
    )
    parsed = parser.parse(text, session.registry)
    assert [s.record.op_id for s in parsed.steps] == [
        "inline_data",
        "sort_rows",
        "custom_code",
        "head",
    ]
    assert parsed.steps[2].name == "my step"
    assert parsed.steps[2].record.params.code == (  # ty: ignore[unresolved-attribute]
        'df["b"] = df["a"] + 1\ndf = df.head(2)  # mixed block: one custom step'
    )
    nodes = session.import_script(text)
    assert session.materialize(nodes[-1].id).to_dict("list") == {"a": [1], "b": [2]}


def test_parse_errors_have_line_numbers(session: Session) -> None:
    with pytest.raises(parser.ParseError) as info:
        parser.parse("import pandas as pd\n\ndf = df.sort_values(by=\n", session.registry)
    assert info.value.lineno == 3
    with pytest.raises(parser.ParseError, match="line 2: sort_rows") as info:
        parser.parse(
            '\ndf = df.sort_values(by="x", na_position="middle")', session.registry, ["df"]
        )
    assert info.value.lineno == 2
    with pytest.raises(parser.ParseError, match=r"line 1:.*no 'df'"):
        parser.parse("print('hi')\n", session.registry)


def test_non_literal_arguments_are_custom_code(session: Session) -> None:
    parsed = parser.parse("df = df.head(n)\n", session.registry, ["df"])
    assert parsed.steps[0].record.op_id == "custom_code"
