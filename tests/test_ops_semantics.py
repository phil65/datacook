"""What the phase 4 ops do (results, missing-value policy, parser edge cases).

`test_ops.py` checks apply == generated code == parsed code for every op; this file checks
the results themselves.
"""

import pandas as pd
import pyarrow as pa
import pydantic
import pytest

from datacook.engine import default_ops, parser
from datacook.engine.ops import OpError, categorical, columns, missing, rows, values


@pytest.fixture
def nan_frame() -> pd.DataFrame:
    """An arrow float column holding NaN (a value) and nulls (missing)."""
    floats = pa.array([1.0, float("nan"), None, 4.0])
    return pd.DataFrame({
        "f": pd.array(floats, dtype="float64[pyarrow]"),
        "s": pd.array(["a", None, "c", "a"], dtype="string[pyarrow]"),
        "i": pd.array([1, None, 3, -999], dtype="int64[pyarrow]"),
    })


def _parse_one(code: str):
    parsed = parser.parse(code, default_ops(), inputs=["df"])
    assert len(parsed.records) == 1
    return parsed.records[0]


# --- missing values -----------------------------------------------------------------------


def test_nan_is_a_value_until_converted(nan_frame) -> None:
    assert nan_frame["f"].isna().tolist() == [False, False, True, False]
    result = missing.NanToMissing.apply(missing.NanToMissing.Params(), nan_frame)
    assert result["f"].isna().tolist() == [False, True, True, False]
    assert result.dtypes.tolist() == nan_frame.dtypes.tolist()
    pd.testing.assert_frame_equal(result[["s", "i"]], nan_frame[["s", "i"]])


def test_replace_with_missing_keeps_arrow_dtypes(nan_frame) -> None:
    params = values.ReplaceValues.Params(to_replace=[-999], columns=["i"])
    result = values.ReplaceValues.apply(params, nan_frame)
    assert result["i"].isna().tolist() == [False, True, False, True]
    assert result.dtypes.tolist() == nan_frame.dtypes.tolist()


def test_replace_rejects_nan() -> None:
    with pytest.raises(pydantic.ValidationError, match="NaN to missing"):
        values.ReplaceValues.Params(to_replace=[float("nan")])


def test_replace_with_different_values_per_column_stays_code() -> None:
    record = _parse_one('df = df.replace({"a": 1, "b": 2}, 0)')
    assert record.op_id == "custom_code"


def test_fill_statistic(nan_frame) -> None:
    params = missing.FillWithStatistic.Params(columns=["i"], statistic="max")
    assert missing.FillWithStatistic.apply(params, nan_frame)["i"].tolist() == [1, 3, 3, -999]
    params = missing.FillWithStatistic.Params(columns=["s"], statistic="mode")
    assert missing.FillWithStatistic.apply(params, nan_frame)["s"].tolist() == [
        "a",
        "a",
        "c",
        "a",
    ]


def test_interpolate_linear() -> None:
    frame = pd.DataFrame({"v": pd.array([0, None, None, 3, None], dtype="int64[pyarrow]")})
    params = missing.Interpolate.Params(columns=["v"], limit_area="inside")
    result = missing.Interpolate.apply(params, frame)["v"]
    assert result.iloc[:4].tolist() == [0.0, 1.0, 2.0, 3.0]
    assert result.isna().iloc[4]


def test_filter_missing_and_drop_missing_columns(nan_frame) -> None:
    result = missing.FilterMissing.apply(missing.FilterMissing.Params(), nan_frame)
    assert result.index.tolist() == [1, 2]
    params = missing.DropMissingColumns.Params(how="any")
    assert missing.DropMissingColumns.apply(params, nan_frame).columns.tolist() == []


def test_dropna_on_columns_is_not_drop_rows() -> None:
    record = _parse_one('df = df.dropna(axis="columns")')
    assert record.op_id == "drop_missing_columns"
    assert _parse_one("df = df.dropna(thresh=2)").op_id == "custom_code"


# --- general / columns ----------------------------------------------------------------------


def test_move_columns(frame) -> None:
    params = columns.MoveColumns.Params(columns=["i", "x"], position="first")
    assert columns.MoveColumns.apply(params, frame).columns.tolist() == ["i", "x", "k", "s"]
    params = columns.MoveColumns.Params(columns=["k"], position="last")
    assert columns.MoveColumns.apply(params, frame).columns.tolist() == ["x", "s", "i", "k"]


def test_combine_columns_missing_values(frame) -> None:
    params = columns.CombineColumns.Params(columns=["s", "k"], name="sk", sep="/")
    assert columns.CombineColumns.apply(params, frame)["sk"].tolist() == [
        "a/1",
        "b/2",
        "/3",
        "d/1",
        "b/2",
    ]
    params = columns.CombineColumns.Params(columns=["s", "k"], name="sk", na_rep=None)
    assert columns.CombineColumns.apply(params, frame)["sk"].isna().tolist() == [
        False,
        False,
        True,
        False,
        False,
    ]


def test_calculate_columns(frame) -> None:
    params = columns.CalculateColumns.Params(expr="y = i / 10\nz = y + k")
    result = columns.CalculateColumns.apply(params, frame)
    assert result["z"].tolist() == [2.0, 4.0, 6.0, 5.0, 7.0]
    with pytest.raises(pydantic.ValidationError):
        columns.CalculateColumns.Params(expr="i * 2")
    with pytest.raises(OpError, match="not a frame"):
        columns.CalculateColumns.apply(columns.CalculateColumns.Params(expr="i == 2"), frame)


def test_select_dtypes_needs_a_type() -> None:
    with pytest.raises(pydantic.ValidationError, match="include or exclude"):
        columns.SelectDtypes.Params()


def test_downcast_keeps_arrow(frame) -> None:
    result = columns.Downcast.apply(columns.Downcast.Params(columns=["k"]), frame)
    assert str(result["k"].dtype) == "int8[pyarrow]"


def test_duplicate_columns(frame) -> None:
    params = columns.DuplicateColumns.Params(columns=["k"], suffix=" (2)")
    result = columns.DuplicateColumns.apply(params, frame)
    assert result.columns.tolist() == ["k", "x", "s", "i", "k (2)"]
    assert _parse_one(columns.DuplicateColumns.to_code(params, ["df"], "df")).params == params


def test_slice_and_top_k(frame) -> None:
    params = rows.SliceRows.Params(start=1, step=2)
    assert rows.SliceRows.apply(params, frame)["i"].tolist() == [20, 40]
    params = rows.NLargest.Params(n=2, columns=["i"])
    assert rows.NLargest.apply(params, frame)["i"].tolist() == [50, 40]


def test_filter_isin_invert_keeps_missing(frame) -> None:
    params = rows.FilterIsIn.Params(column="s", values=["a", "b"], invert=True)
    result = rows.FilterIsIn.apply(params, frame)
    assert result["i"].tolist() == [30, 40]


def test_clip_and_abs(frame) -> None:
    neg = frame.assign(x=-frame["x"])
    result = values.Abs.apply(values.Abs.Params(columns=["x"]), neg)
    pd.testing.assert_series_equal(result["x"], frame["x"])
    params = values.Clip.Params(columns=["i"], upper=25)
    assert values.Clip.apply(params, frame)["i"].tolist() == [10, 20, 25, 25, 25]


def test_whole_frame_form_needs_optional_columns() -> None:
    """`df.abs()` is not "Absolute values" (that op names its columns): custom code."""
    assert _parse_one("df = df.abs()").op_id == "custom_code"
    assert _parse_one("df = df.ffill()").op_id == "ffill"


def test_frame_call_forms_with_other_arguments_are_custom_code() -> None:
    """Keywords the params lack: not the op (like `CallOp`), parsed as custom code."""
    assert _parse_one("df = df.ffill(axis=1)").op_id == "custom_code"
    assert _parse_one('df = df.assign(**df[["x"]].ffill(axis=1))').op_id == "custom_code"
    assert _parse_one('df = df.assign(**df["x"].ffill())').op_id == "custom_code"
    record = _parse_one('df = df.assign(**df[["x"]].clip(upper=2))')
    assert record == values.Clip.record(columns=["x"], upper=2.0)


# --- categorical ----------------------------------------------------------------------------


@pytest.fixture
def cat_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "my col": pd.Series(["lo", "hi", None, "lo"], dtype="category"),
        "n": [1, 2, 3, 4],
    })


def test_category_ops(cat_frame) -> None:
    col = "my col"
    frame = categorical.AddCategories.apply(
        categorical.AddCategories.Params(column=col, new_categories=["mid"]), cat_frame
    )
    assert frame[col].cat.categories.tolist() == ["hi", "lo", "mid"]
    frame = categorical.ReorderCategories.apply(
        categorical.ReorderCategories.Params(
            column=col, new_categories=["lo", "mid", "hi"], ordered=True
        ),
        frame,
    )
    assert frame[col].cat.ordered
    assert frame[col].max() == "hi"
    frame = categorical.RemoveUnusedCategories.apply(
        categorical.RemoveUnusedCategories.Params(column=col), frame
    )
    assert frame[col].cat.categories.tolist() == ["lo", "hi"]
    frame = categorical.RemoveCategories.apply(
        categorical.RemoveCategories.Params(column=col, removals=["hi"]), frame
    )
    assert frame[col].isna().tolist() == [False, True, True, False]
    frame = categorical.RenameCategories.apply(
        categorical.RenameCategories.Params(column=col, new_categories={"lo": "low"}), frame
    )
    assert frame[col].tolist()[0] == "low"
    assert cat_frame[col].cat.categories.tolist() == ["hi", "lo"]  # input untouched


def test_category_code_with_any_column_name(cat_frame) -> None:
    params = categorical.AsOrdered.Params(column="my col")
    code = categorical.AsOrdered.to_code(params, ["df"], "df")
    assert code == 'df = df.assign(**{"my col": df["my col"].cat.as_ordered()})'
    assert _parse_one(code) == categorical.AsOrdered.record(params)
    params = categorical.AsOrdered.Params(column="class")  # a keyword: no `class=...`
    assert "**{" in categorical.AsOrdered.to_code(params, ["df"], "df")


def test_category_op_has_no_suffix() -> None:
    """One `column`, no suffix: a result under another name is not the op."""
    assert _parse_one('df = df.assign(c2=df["c"].cat.as_ordered())').op_id == "custom_code"
    code = 'df = df.assign(c=df["c"].cat.as_ordered(), d=df["d"].cat.as_ordered())'
    assert _parse_one(code).op_id == "custom_code"


def test_category_op_on_other_column(cat_frame) -> None:
    with pytest.raises(OpError, match=r"n: Can only use \.cat accessor"):
        categorical.AsOrdered.apply(categorical.AsOrdered.Params(column="n"), cat_frame)
