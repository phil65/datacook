"""Text, date / time and time series ops (WP4.3, WP4.4).

apply == exec(to_code), parse(to_code) == record and golden code, on pyarrow dtypes, numpy
dtypes and an empty frame.
"""

import pandas as pd
import pytest

from datacook.engine import Session, default_ops, parser, timecol
from datacook.engine.ops import OpError, sources
from datacook.engine.ops.dates import DatetimeParts, ToDatetime
from datacook.engine.ops.strings import ChangeCase, FilterText, Test
from datacook.engine.ops.timeseries import (
    DetectGaps,
    Resample,
    Rolling,
    SecondsSinceStart,
    SetTimeColumn,
    ToleranceBands,
)
from tests.op_cases_text_time import CASES, GOLDEN, frame


VARIANTS = {
    "arrow": lambda: frame(),
    "numpy": lambda: frame(arrow=False),
    "empty": lambda: frame().iloc[:0],
}


@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize("case", sorted(CASES))
def test_apply_equals_generated_code(case: str, variant: str) -> None:
    op, kwargs = CASES[case]
    params = op.Params(**kwargs)
    data = VARIANTS[variant]()
    text = op.to_code(params, ["df"], "df")
    namespace = {"pd": pd, "df": data}
    exec(text, namespace)
    expected = op.apply(params, data)
    pd.testing.assert_frame_equal(namespace["df"], expected)
    pd.testing.assert_frame_equal(data, VARIANTS[variant]())  # input untouched


@pytest.mark.parametrize("case", sorted(CASES))
def test_golden_code(case: str) -> None:
    op, kwargs = CASES[case]
    assert op.to_code(op.Params(**kwargs), ["df"], "df") == GOLDEN[case]


@pytest.mark.parametrize("case", sorted(CASES))
def test_parse_generated_code(case: str) -> None:
    op, kwargs = CASES[case]
    record = op.record(**kwargs)
    parsed = parser.parse(op.to_code(record.params, ["df_a"], "df_b"), default_ops(), ["df_a"])
    assert parsed.records == [record]
    assert parsed.steps[0].parents == (-1,)


def test_results() -> None:
    data = frame()
    out = ChangeCase.apply(ChangeCase.Params(columns=["s"], case="upper"), data)
    assert out["s"].tolist()[:3] == [" FOO,BAR ", "BAZ", pd.NA]
    assert str(out["s"].dtype) == str(data["s"].dtype)  # stays a pyarrow string
    flags = Test.apply(Test.Params(columns=["s"], pat="b"), data)["s_match"]
    assert flags.tolist() == [True, True, pd.NA, False, True, False]
    kept = FilterText.apply(FilterText.Params(column="s", pat="B", case=False), data)
    assert kept["s"].tolist() == [" Foo,bar ", "baz", "a,b,c"]  # missing text: not kept
    secs = SecondsSinceStart.apply(SecondsSinceStart.Params(time_column="t"), data)["secs"]
    assert secs.tolist() == [0.0, 20.0, 30.0, 100.0, 110.0, 190.0]
    gaps = DetectGaps.apply(DetectGaps.Params(time_column="t", max_gap="30s"), data)
    assert gaps["segment"].tolist() == [1, 1, 1, 2, 2, 3]
    bands = ToleranceBands.apply(ToleranceBands.Params(columns=["x"], window=3, pct=0.1), data)
    assert bands["x_lower"].tolist()[:3] == pytest.approx([1.35, 1.5, 2.7])
    assert bands["x_upper"].tolist()[:3] == pytest.approx([1.65, 3.0, 4.0])
    parts = DatetimeParts.apply(DatetimeParts.Params(column="t", parts=["hour"]), data)
    assert parts["t_hour"].tolist() == [1, 3, 3, 3, 3, 3]  # local time, across the DST change


def test_resample_keeps_time_as_column() -> None:
    params = Resample.Params(
        time_column="t", rule="1min", aggregations=[{"column": "x", "func": "sum"}]
    )
    out = Resample.apply(params, frame())
    assert list(out.columns) == ["t", "x_sum"]
    assert isinstance(out.index, pd.RangeIndex)
    assert str(out["t"].dt.tz) == "Europe/Berlin"


def test_window_params_validation() -> None:
    with pytest.raises(ValueError, match="time column"):
        Rolling.Params(columns=["x"], window="10s")
    with pytest.raises(ValueError, match="case sensitive"):
        Test.Params(columns=["s"], mode="startswith", pat="a", case=False)


def test_set_time_column_rejects_text() -> None:
    with pytest.raises(OpError, match="convert it"):
        SetTimeColumn.apply(SetTimeColumn.Params(time_column="s"), frame())


def test_parse_does_not_confuse_ops() -> None:
    """Similar statements of other ops are not taken for these ops (and vice versa)."""
    ops = default_ops()
    text = 'df = df.sort_values(by=["t"])\n\ndf = df.assign(s=df["s"].str.upper().str.strip())'
    parsed = parser.parse(text, ops, ["df"])
    assert [r.op_id for r in parsed.records] == ["sort_rows", "custom_code"]
    text = 'df = df.assign(s=pd.to_datetime(df["s"], foo=1))'
    with pytest.raises(parser.ParseError, match="to_datetime"):
        parser.parse(text, ops, ["df"])


def test_time_column_from_steps() -> None:
    data = {"a": ["2024-01-01 10:00", "2024-01-01 10:01"], "b": ["10:00", "09:00"], "x": [1, 2]}
    with Session() as session:
        root = session.add(sources.InlineData.record(data=data))
        dates = session.add(ToDatetime.record(columns=["a", "b"]), [root])
        assert timecol.time_column(session, dates.id) is None  # not computed yet
        session.materialize(dates.id)
        assert timecol.time_column(session, dates.id) == "a"  # first date / time column
        step = session.add(SetTimeColumn.record(time_column="b"), [dates])
        child = session.add(ToDatetime.record(columns=["x"], unit="s"), [step])
        assert timecol.time_column(session, child.id) == "b"  # from the steps
        session.materialize(child.id)
        assert timecol.time_column(session, child.id) == "b"
        assert session.materialize(child.id)["b"].is_monotonic_increasing
        renamed = session.add(
            Resample.record(time_column="gone", aggregations=[{"column": "x", "func": "sum"}]),
            [child],
        )
        assert timecol.time_column(session, renamed.id) == "gone"  # not computed: trusted
    assert timecol.time_fields(Rolling.Params) == ["time_column"]
