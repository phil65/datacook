"""Every starter op: apply == exec(to_code), parse(to_code) == record, golden code."""

import typing
from typing import TYPE_CHECKING

import pandas as pd
import pydantic
import pytest

from datacook.engine import default_ops, parser
from datacook.engine.ops import OpError, OpRecord, base, code, combine, rows
from tests import op_cases_text_time
from tests.op_cases import CASES


if TYPE_CHECKING:
    from datacook.engine.ops import Op


GOLDEN = {
    "select_columns": 'df = df[["s", "k"]]',
    "drop_columns": 'df = df.drop(columns=["i"])',
    "rename_columns": 'df = df.rename(columns={"x": "value", "s": "name"})',
    "astype": 'df = df.astype({"i": "float32", "k": "string[pyarrow]"})',
    "filter_rows": 'df = df.query("x > 1.5 and k != 2")',
    "sort_rows": 'df = df.sort_values(by=["k", "x"], ascending=[True, False])',
    "sort_rows_defaults": 'df = df.sort_values(by=["x"])',
    "head": "df = df.head(3)",
    "sample": "df = df.sample(n=2, random_state=7)",
    "drop_duplicates": 'df = df.drop_duplicates(subset=["s"], keep="last")',
    "fill_missing": 'df = df.fillna({"x": 0.0, "s": "?"})',
    "ffill": "df = df.ffill()",
    "bfill": "df = df.bfill(limit=1)",
    "drop_missing": 'df = df.dropna(subset=["x"])',
    "move_columns": 'df = df[["s", "i", *df.columns.drop(["s", "i"])]]',
    "move_columns_last": 'df = df[[*df.columns.drop(["k"]), "k"]]',
    "sort_columns": 'df = df.sort_index(axis="columns", ascending=False)',
    "add_prefix": 'df = df.add_prefix("col_")',
    "add_suffix": 'df = df.add_suffix("_1")',
    "select_dtypes": 'df = df.select_dtypes(include=["number"])',
    "select_dtypes_exclude": 'df = df.select_dtypes(exclude=["number", "category"])',
    "convert_dtypes": 'df = df.convert_dtypes(dtype_backend="pyarrow")',
    "convert_dtypes_numpy": 'df = df.convert_dtypes(dtype_backend="numpy_nullable")',
    "downcast": 'df = df.assign(**df[["k", "i"]].apply(pd.to_numeric, downcast="integer"))',
    "duplicate_columns": 'df = df.join(df[["x", "s"]].add_suffix("_copy"))',
    "combine_columns": (
        'df = df.assign(label=df["s"].astype("string").str.cat(\n'
        '    df[["k", "x"]].astype("string"),\n'
        '    sep=" ",\n'
        '    na_rep="",\n'
        "))"
    ),
    "combine_columns_missing": (
        'df = df.assign(**{"s k": df["s"].astype("string").str.cat(\n'
        '    df[["k"]].astype("string"),\n'
        '    sep="-",\n'
        "    na_rep=None,\n"
        ")})"
    ),
    "calculate_columns": 'df = df.eval("y = x * 2 + i\\nbig = y > 40")',
    "tail": "df = df.tail(2)",
    "nlargest": 'df = df.nlargest(2, columns=["x"])',
    "nsmallest": 'df = df.nsmallest(2, columns=["k", "i"], keep="all")',
    "slice_rows": "df = df.iloc[1:-1]",
    "slice_rows_step": "df = df.iloc[::2]",
    "filter_isin": 'df = df[df["s"].isin(["a", "b"])]',
    "filter_isin_invert": 'df = df[~df["k"].isin([1])]',
    "reset_index": "df = df.reset_index(drop=True)",
    "abs": 'df = df.assign(**df[["x"]].abs())',
    "clip": 'df = df.assign(**df[["x", "i"]].clip(lower=2.0, upper=35.0))',
    "replace_values": "df = df.replace(3.0, 0.0)",
    "replace_values_missing": 'df = df.replace({"s": ["a", "d"]}, pd.NA)',
    "ffill_columns": 'df = df.assign(**df[["x"]].ffill())',
    "fill_statistic": 'df = df.fillna(df[["x"]].median())',
    "fill_statistic_mode": 'df = df.fillna(df[["s"]].mode().head(1).squeeze(axis=0))',
    "interpolate": 'df = df.assign(**df[["x"]].interpolate(limit_direction="both"))',
    "drop_missing_columns": 'df = df.dropna(axis="columns", how="any")',
    "isna": "df = df.isna()",
    "filter_missing": "df = df[df.isna().any(axis=1)]",
    "filter_missing_columns": 'df = df[df[["x", "s"]].isna().all(axis=1)]',
    "nan_to_missing": "df = df.mask(lambda d: d != d)",
    "nan_to_missing_columns": 'df = df.assign(**df[["x"]].mask(lambda d: d != d))',
    "cat_add_categories": 'df = df.assign(c=df["c"].cat.add_categories(["z"]))',
    "cat_remove_categories": 'df = df.assign(c=df["c"].cat.remove_categories(["a"]))',
    "cat_rename_categories": (
        'df = df.assign(c=df["c"].cat.rename_categories({"a": "A", "b": "B"}))'
    ),
    "cat_reorder_categories": (
        'df = df.assign(c=df["c"].cat.reorder_categories(["d", "b", "a"], ordered=True))'
    ),
    "cat_set_categories": 'df = df.assign(c=df["c"].cat.set_categories(["b", "d", "e"]))',
    "cat_as_ordered": 'df = df.assign(c=df["c"].cat.as_ordered())',
    "cat_as_unordered": 'df = df.assign(c=df["c"].cat.as_unordered())',
    "cat_remove_unused": 'df = df.assign(c=df["c"].cat.remove_unused_categories())',
    "merge": 'df = df.merge(df_right, how="left", on=["k"])',
    "groupby_aggregate": (
        'df = df.groupby(["k"], as_index=False).agg(x_sum=("x", "sum"), largest=("i", "max"))'
    ),
    "groupby_aggregate_names": (
        'df = df.groupby(["s"], as_index=False, dropna=False).agg(**{"mean x": ("x", "mean")})'
    ),
    "custom_code": 'df["twice"] = df["i"] * 2\ndf = df[df["twice"] > 20]',
}
TRANSFORM_OPS = {op.id for op in default_ops() if op.n_inputs > 0}


def _inputs(op: type[Op], frame: pd.DataFrame, other: pd.DataFrame) -> list[pd.DataFrame]:
    return [frame, other][: op.n_inputs]


@pytest.fixture
def op_frame(frame) -> pd.DataFrame:
    """The engine test frame plus a categorical column `c` (categories a, b, d)."""
    return frame.assign(c=frame["s"].astype("category"))


def _run_both(op: type[Op], params, inputs: list[pd.DataFrame]) -> tuple[object, object]:
    """`(op.apply result, exec(to_code) result)`; an exception is returned as its type."""
    names = ["df", "df_right"][: op.n_inputs]
    try:
        applied: object = op.apply(params, *inputs)
    except Exception as e:  # noqa: BLE001
        applied = type(e)
    namespace = {"pd": pd, **dict(zip(names, inputs))}
    try:
        exec(op.to_code(params, names, "df"), namespace)
        executed: object = namespace["df"]
    except Exception as e:  # noqa: BLE001
        executed = type(e)
    return applied, executed


@pytest.mark.parametrize("case", sorted(CASES))
def test_apply_equals_generated_code(case: str, op_frame, other) -> None:
    op, kwargs = CASES[case]
    params = op.Params(**kwargs)
    inputs = _inputs(op, op_frame, other)
    names = ["df", "df_right"][: op.n_inputs]
    text = op.to_code(params, names, "df")
    assert text == GOLDEN[case]
    namespace = {"pd": pd, **dict(zip(names, inputs))}
    exec(text, namespace)
    expected = op.apply(params, *inputs)
    pd.testing.assert_frame_equal(namespace["df"], expected)
    # copy-on-write: the inputs are untouched
    pd.testing.assert_frame_equal(inputs[0], op_frame)


@pytest.mark.parametrize("variant", ["empty", "numpy", "all_missing"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_edge_cases(case: str, variant: str, op_frame, other) -> None:
    """Empty frames, numpy dtypes, all-missing columns: apply and the code agree."""
    op, kwargs = CASES[case]
    match variant:
        case "empty":
            data = op_frame.iloc[:0]
        case "numpy":
            data = op_frame.astype({"k": "int64", "x": "float64", "i": "int64", "s": object})
        case _:
            data = op_frame.assign(x=pd.Series([None] * 5, dtype="float64[pyarrow]"))
    applied, executed = _run_both(op, op.Params(**kwargs), _inputs(op, data, other))
    if isinstance(applied, pd.DataFrame) and isinstance(executed, pd.DataFrame):
        pd.testing.assert_frame_equal(applied, executed)
    else:
        assert applied == executed
    if variant == "empty" and op.id not in {"custom_code", "sample"}:  # sample: n > rows
        assert isinstance(applied, pd.DataFrame), f"{case} fails on an empty frame"


@pytest.mark.parametrize("case", sorted(CASES))
def test_parse_generated_code(case: str) -> None:
    op, kwargs = CASES[case]
    record = op.record(**kwargs)
    names = ["df", "df_right"][: op.n_inputs]
    parsed = parser.parse(op.to_code(record.params, names, "df"), default_ops(), inputs=names)
    assert parsed.records == [record]
    assert parsed.steps[0].parents == tuple(-1 - i for i in range(op.n_inputs))


def test_every_transform_op_has_a_case() -> None:
    cases = [*CASES.values(), *op_cases_text_time.CASES.values()]
    assert {op.id for op, _ in cases} == TRANSFORM_OPS


def test_ops_metadata() -> None:
    for op in default_ops():
        assert op.id
        assert str(op.title)
        assert op.icon.startswith("mdi.")
        assert issubclass(op.Params, base.Params)
        op.Params.model_json_schema()  # usable as a form / tool schema


def test_record_json_roundtrip() -> None:
    from datacook.engine.ops import record_from_json

    for op, kwargs in CASES.values():
        record = op.record(**kwargs)
        assert record_from_json(record.to_json()) == record


def test_params_are_immutable() -> None:
    params = rows.Head.Params(n=2)
    with pytest.raises(ValueError, match="frozen"):
        params.n = 3  # ty: ignore[invalid-assignment]


def test_custom_code_does_not_modify_input(frame) -> None:
    params = code.CustomCode.Params(code='df["k"] = 0')
    result = code.CustomCode.apply(params, frame)
    assert (result["k"] == 0).all()
    assert frame["k"].tolist() == [1, 2, 3, 1, 2]


def test_custom_code_errors(frame) -> None:
    with pytest.raises(OpError, match="line 1"):
        code.CustomCode.apply(code.CustomCode.Params(code="df = ("), frame)
    with pytest.raises(OpError, match="DataFrame"):
        code.CustomCode.apply(code.CustomCode.Params(code="df = 1"), frame)


def test_custom_code_with_other_variables(frame) -> None:
    params = code.CustomCode.Params(code='df["z"] = 1\nif True:\n    df = df.head(2)')
    text = code.CustomCode.to_code(params, ["df_a"], "df_b")
    assert text == (
        "def custom_step(df):\n"
        '    df["z"] = 1\n'
        "    if True:\n"
        "        df = df.head(2)\n"
        "    return df\n"
        "df_b = custom_step(df_a)"
    )
    namespace = {"df_a": frame}
    exec(text, namespace)
    pd.testing.assert_frame_equal(namespace["df_b"], code.CustomCode.apply(params, frame))
    assert "df" not in namespace
    parsed = parser.parse(text, default_ops(), inputs=["df_a"])
    assert parsed.records == [OpRecord("custom_code", params)]
    assert parsed.steps[0].parents == (-1,)
    assert parsed.variables == {"df_b": 0}


def test_literals_roundtrip() -> None:
    import ast
    import math

    for value in ["it's", 'say "x"', "a\\b\n", [1, (2,), {"k": None}], 1.5, True]:
        assert base.literal_value(ast.parse(base.literal(value), mode="eval").body) == value
    nan = base.literal_value(ast.parse(base.literal(float("nan")), mode="eval").body)
    assert math.isnan(nan)
    assert base.literal(float("-inf")) == 'float("-inf")'


COLUMN_FIELDS = {"by", "subset", "columns", "on", "left_on", "right_on", "column", "dtype"}


def _models(model: type[pydantic.BaseModel]):
    yield model
    for field in model.model_fields.values():
        for arg in (field.annotation, *typing.get_args(field.annotation)):
            for inner in (arg, *typing.get_args(arg)):
                if isinstance(inner, type) and issubclass(inner, pydantic.BaseModel):
                    yield from _models(inner)


def test_column_fields_have_widget_hints() -> None:
    """Fields holding column names tell the app to offer a column chooser."""
    seen = 0
    for op in default_ops():
        if op.n_inputs == 0:
            continue  # readers: column names of the file, there is no input frame
        for model in _models(op.Params):
            for name, field in model.model_fields.items():
                if name not in COLUMN_FIELDS:
                    continue
                extra = field.json_schema_extra
                assert isinstance(extra, dict), f"{op.id}.{name}"
                assert extra.get("widget") in {"column", "columns", "column_map"}, f"{op.id}.{name}"
                seen += 1
    assert seen >= 12
    schema = combine.Merge.Params.model_json_schema()["properties"]
    assert schema["right_on"]["widget"] == "columns"
    assert schema["right_on"]["input"] == 1
