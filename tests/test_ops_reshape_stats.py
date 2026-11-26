"""Reshape, combine and statistics ops (WP4.6, WP4.7): results, concat with n inputs.

`test_ops.py` checks apply == generated code == parsed code for every op case.
"""

import pandas as pd
import pydantic
import pytest

from datacook.engine import Session, default_ops, parser, recipes
from datacook.engine.ops import combine, reshape, rows, sources, stats


def _parse_one(code: str, inputs: tuple[str, ...] = ("df",)):
    parsed = parser.parse(code, default_ops(), inputs=list(inputs))
    assert len(parsed.records) == 1
    return parsed.records[0]


# --- concat: two or more inputs ------------------------------------------------------------


def _roots(session: Session, n: int) -> list[str]:
    return [
        session.add(sources.InlineData.record(data={"a": [i, i + 10], "b": [str(i)] * 2})).id
        for i in range(n)
    ]


def test_concat_three_inputs(session: Session) -> None:
    roots = _roots(session, 3)
    node = session.add(combine.Concat.record(), roots)
    assert session.materialize(node.id)["a"].tolist() == [0, 10, 1, 11, 2, 12]
    text = session.code([node.id])
    assert "pd.concat([df, df2, df3], ignore_index=True)" in text
    namespace: dict = {}
    exec(text, namespace)
    output = parser.parse(text, session.registry).steps[-1].output
    pd.testing.assert_frame_equal(namespace[output], session.materialize(node.id))
    with Session() as other:
        created = other.import_script(text)
        assert len(created[-1].parents) == 3
        assert other.code() == text


def test_concat_needs_two_inputs(session: Session) -> None:
    (root,) = _roots(session, 1)
    with pytest.raises(ValueError, match="2 or more"):
        session.add(combine.Concat.record(), [root])
    assert _parse_one("df = pd.concat([df])").op_id == "custom_code"
    record = _parse_one("df = pd.concat([df, b], axis='columns')", ("df", "b"))
    assert record == combine.Concat.record(axis="columns")


def test_concat_recipe_keeps_inputs(session: Session) -> None:
    src = session.add(sources.InlineData.record(data={"a": [3, 1, 2]})).id
    heads = [session.add(rows.Head.record(n=n), [src]).id for n in (1, 2)]
    tail = session.add(rows.Tail.record(n=1), [src]).id
    concat = session.add(combine.Concat.record(), [*heads, tail]).id
    recipe = recipes.from_path(session, concat, start=src, name="stack")
    assert recipe.steps[-1].inputs == (0, 1, 2)
    again = recipes.loads(recipe.dumps())
    assert again.steps == recipe.steps
    added = recipes.apply(session, again, src)
    assert session.materialize(added[-1].id)["a"].tolist() == [3, 3, 1, 2]


# --- reshape ---------------------------------------------------------------------------------


@pytest.fixture
def sales() -> pd.DataFrame:
    return pd.DataFrame({
        "region": ["n", "n", "s", "s", "s"],
        "year": [2023, 2024, 2023, 2024, 2024],
        "amount": [1.0, 2.0, 3.0, 4.0, 5.0],
    }).convert_dtypes(dtype_backend="pyarrow")


def test_unpivot_then_pivot_roundtrip(sales) -> None:
    wide = reshape.Pivot.apply(
        reshape.Pivot.Params(index=["region"], columns="year", values="amount", aggfunc="sum"),
        sales,
    )
    assert wide.columns.tolist() == ["region", "2023", "2024"]  # labels as text
    assert wide["2024"].tolist() == [2.0, 9.0]
    long = reshape.Unpivot.apply(
        reshape.Unpivot.Params(id_vars=["region"], var_name="year", value_name="amount"), wide
    )
    assert long.columns.tolist() == ["region", "year", "amount"]
    assert long["amount"].sum() == sales["amount"].sum()


def test_pivot_totals(sales) -> None:
    params = reshape.Pivot.Params(
        index=["region"],
        columns="year",
        values="amount",
        aggfunc="sum",
        margins=True,
        margins_name="Total",
    )
    result = reshape.Pivot.apply(params, sales)
    assert result["region"].tolist() == ["n", "s", "Total"]
    assert result["Total"].tolist() == [3.0, 12.0, 15.0]


def test_crosstab_counts_shares_totals(sales) -> None:
    params = reshape.Crosstab.Params(index=["region"], columns="year")
    assert reshape.Crosstab.apply(params, sales)["2024"].tolist() == [1, 2]
    params = reshape.Crosstab.Params(
        index=["region"], columns="year", normalize="index", margins=True
    )
    result = reshape.Crosstab.apply(params, sales)
    assert result["region"].tolist() == ["n", "s", "All"]
    assert result["2024"].tolist() == pytest.approx([0.5, 2 / 3, 0.6])


def test_transpose_with_header(sales) -> None:
    params = reshape.Transpose.Params(header="region", names="field")
    result = reshape.Transpose.apply(params, sales)
    assert result.columns.tolist() == ["field", "n", "n", "s", "s", "s"]
    assert result["field"].tolist() == ["year", "amount"]


# --- statistics ------------------------------------------------------------------------------


def test_summary_tables_have_label_columns(frame) -> None:
    described = stats.Describe.apply(stats.Describe.Params(columns=["x", "i"]), frame)
    assert described.columns.tolist() == ["statistic", "x", "i"]
    assert described["statistic"].tolist()[:2] == ["count", "mean"]
    var = stats.Variance.apply(stats.Variance.Params(), frame)
    assert var.columns.tolist() == ["column", "variance"]
    assert var["column"].tolist() == ["k", "x", "i"]  # text column skipped
    corr = stats.Correlation.apply(stats.Correlation.Params(columns=["k", "i"]), frame)
    assert corr.columns.tolist() == ["column", "k", "i"]
    assert corr["k"].tolist()[0] == pytest.approx(1.0)
    cov = stats.Covariance.apply(stats.Covariance.Params(columns=["i"]), frame)
    assert cov["i"].tolist() == [250.0]


def test_corrwith_matches_columns_by_name(frame, other) -> None:
    result = stats.CorrelationWith.apply(stats.CorrelationWith.Params(), frame, frame * 2)
    assert result["column"].tolist() == ["k", "x", "i"]
    assert result["correlation"].tolist() == pytest.approx([1.0, 1.0, 1.0])
    dropped = stats.CorrelationWith.apply(stats.CorrelationWith.Params(drop=True), frame, other)
    assert dropped["column"].tolist() == ["k"]


def test_value_counts_and_mode(frame) -> None:
    counts = stats.ValueCounts.apply(stats.ValueCounts.Params(subset=["s"]), frame)
    assert counts.to_dict("list") == {"s": ["b", "a", "d"], "count": [2, 1, 1]}
    shares = stats.ValueCounts.apply(
        stats.ValueCounts.Params(subset=["s"], normalize=True, dropna=False), frame
    )
    assert shares.columns.tolist() == ["s", "proportion"]
    assert shares["proportion"].sum() == pytest.approx(1.0)
    mode = stats.Mode.apply(stats.Mode.Params(columns=["k", "s"]), frame)
    assert mode["s"].tolist()[0] == "b"
    assert mode["k"].tolist() == [1, 2]


def test_rank_and_bins(frame) -> None:
    ranked = stats.Rank.apply(stats.Rank.Params(columns=["i"], method="dense"), frame)
    assert ranked["i_rank"].tolist() == [1, 2, 3, 4, 5]
    binned = stats.Bin.apply(
        stats.Bin.Params(columns=["i"], bins=[0, 25, 60], labels=["low", "high"]), frame
    )
    assert binned["i_bin"].astype("string").tolist() == ["low", "low", "high", "high", "high"]
    equal = stats.Bin.apply(stats.Bin.Params(columns=["x"], bins=2, suffix=""), frame)
    assert equal["x"].cat.categories.size == 2
    with pytest.raises(pydantic.ValidationError, match="ascending"):
        stats.Bin.Params(columns=["x"], bins=[3.0, 1.0])
    with pytest.raises(pydantic.ValidationError, match="2 labels"):
        stats.Bin.Params(columns=["x"], bins=[0.0, 1.0, 2.0], labels=["a"])


def test_binned_column_materializes_in_a_session(session: Session) -> None:
    src = session.add(sources.InlineData.record(data={"x": [1.0, 2.0, 3.0, 4.0]})).id
    node = session.add(stats.Bin.record(columns=["x"], bins=2), [src])
    assert len(session.materialize(node.id)) == 4
