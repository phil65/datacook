"""Op test cases of the text, date / time and time series ops (WP4.3, WP4.4).

`CASES`: case -> (op class, params kwargs); all run on `frame()`. `GOLDEN`: the code.
"""

import pandas as pd

from datacook.engine.ops import dates, strings, timeseries


def frame(*, arrow: bool = True) -> pd.DataFrame:
    """Text, date / time (tz-aware and naive) and numeric columns, with missing values.

    `arrow=False`: numpy / pandas default dtypes (datetime64, float64, str).
    """
    t = pd.to_datetime([
        "2024-03-31 00:59:50",
        "2024-03-31 01:00:10",
        "2024-03-31 01:00:20",
        "2024-03-31 01:01:30",
        "2024-03-31 01:01:40",
        "2024-03-31 01:03:00",
    ]).tz_localize("UTC")
    df = pd.DataFrame({
        "t": t.tz_convert("Europe/Berlin"),
        "naive": t.tz_localize(None),
        "x": [1.5, None, 3.0, 4.0, 2.0, 6.0],
        "g": ["a", "b", "a", "b", "a", "b"],
        "s": [" Foo,bar ", "baz", None, "Qux-12", "a,b,c", "kw 12"],
        "when": [
            "01.02.2024 10:00",
            "03.04.2024 11:30",
            None,
            "05.06.2024 00:00",
            "07.08.2024 09:15",
            "09.10.2024 23:59",
        ],
        "year": [2020.5, 2000.0, None, 1999.25, 2024.75, 2010.0],
        "epoch": [0, 60, 120, 600, 660, 720],
    })
    return df.convert_dtypes(dtype_backend="pyarrow") if arrow else df


CASES = {
    # text
    "str_case": (strings.ChangeCase, {"columns": ["s", "g"], "case": "upper"}),
    "str_case_suffix": (
        strings.ChangeCase,
        {"columns": ["s"], "case": "title", "suffix": "_title"},
    ),
    "str_strip": (strings.Strip, {"columns": ["s"]}),
    "str_strip_chars": (strings.Strip, {"columns": ["s"], "side": "right", "to_strip": " 12"}),
    "str_replace": (strings.Replace, {"columns": ["s"], "pat": "a", "repl": "A"}),
    "str_replace_regex": (
        strings.Replace,
        {"columns": ["s"], "pat": r"(\w+)-(\d+)", "repl": r"\2-\1", "regex": True, "case": False},
    ),
    "str_slice": (strings.Slice, {"columns": ["s"], "start": 1, "stop": -1}),
    "str_pad": (strings.Pad, {"columns": ["g"], "width": 3, "fillchar": "0"}),
    "str_len": (strings.Length, {"columns": ["s", "g"]}),
    "str_repeat": (strings.Repeat, {"columns": ["g"], "repeats": 3}),
    "str_test": (strings.Test, {"columns": ["s"], "pat": "a", "regex": False, "case": False}),
    "str_test_startswith": (
        strings.Test,
        {"columns": ["s"], "mode": "startswith", "pat": "b", "suffix": ""},
    ),
    "filter_text": (strings.FilterText, {"column": "s", "pat": "a"}),
    "filter_text_invert": (
        strings.FilterText,
        {"column": "s", "mode": "fullmatch", "pat": r"\w+-\d+", "invert": True},
    ),
    "str_extract": (strings.Extract, {"column": "s", "pat": r"(?P<word>[a-zA-Z]+)\W*(\d+)"}),
    "str_extract_prefix": (
        strings.Extract,
        {"column": "s", "pat": r"(?P<number>\d+)", "prefix": ""},
    ),
    "str_split": (strings.Split, {"column": "s", "pat": ",", "n": 1}),
    "str_split_whitespace": (strings.Split, {"column": "s", "prefix": "part_"}),
    # date / time
    "to_datetime": (dates.ToDatetime, {"columns": ["when"], "format": "%d.%m.%Y %H:%M"}),
    "to_datetime_epoch": (
        dates.ToDatetime,
        {"columns": ["epoch"], "unit": "s", "utc": True, "suffix": "_time"},
    ),
    "float_year_to_datetime": (dates.FloatYearToDatetime, {"columns": ["year"], "suffix": "_date"}),
    "dt_parts": (
        dates.DatetimeParts,
        {
            "column": "t",
            "parts": ["year", "month", "day", "hour", "day_of_week", "date", "quarter"],
        },
    ),
    "dt_parts_names": (
        dates.DatetimeParts,
        {"column": "naive", "parts": ["month_name", "day_name"]},
    ),
    "dt_strftime": (dates.Strftime, {"columns": ["t", "naive"], "date_format": "%d.%m.%Y %H:%M"}),
    "tz_localize": (
        dates.TzLocalize,
        {"columns": ["naive"], "tz": "Europe/Berlin", "nonexistent": "shift_forward"},
    ),
    "tz_localize_remove": (dates.TzLocalize, {"columns": ["t"], "tz": None}),
    "tz_convert": (dates.TzConvert, {"columns": ["t"], "tz": "America/New_York"}),
    "dt_round": (dates.RoundTime, {"columns": ["naive"], "how": "round", "freq": "1min"}),
    "dt_floor": (dates.RoundTime, {"columns": ["t"], "freq": "1h", "suffix": "_hour"}),
    # time series
    "set_time_column": (timeseries.SetTimeColumn, {"time_column": "t"}),
    "resample": (
        timeseries.Resample,
        {
            "time_column": "t",
            "rule": "1min",
            "aggregations": [
                {"column": "x", "func": "mean"},
                {"column": "s", "func": "count", "name": "n"},
            ],
        },
    ),
    "resample_groups": (
        timeseries.Resample,
        {
            "time_column": "naive",
            "rule": "2min",
            "by": ["g"],
            "aggregations": [{"column": "x", "func": "max", "name": "max x"}],
            "closed": "right",
            "label": "right",
        },
    ),
    "upsample": (timeseries.Upsample, {"time_column": "t", "rule": "20s"}),
    "upsample_interpolate": (
        timeseries.Upsample,
        {"time_column": "naive", "rule": "30s", "method": "asfreq"},
    ),
    "seconds_since_start": (timeseries.SecondsSinceStart, {"time_column": "t"}),
    "detect_gaps": (timeseries.DetectGaps, {"time_column": "t", "max_gap": "30s"}),
    "detect_gaps_numeric": (
        timeseries.DetectGaps,
        {"time_column": "epoch", "max_gap": 100, "name": "part"},
    ),
    "rolling": (timeseries.Rolling, {"columns": ["x"], "window": 3, "suffix": "_avg"}),
    "rolling_time": (
        timeseries.Rolling,
        {
            "columns": ["x", "epoch"],
            "window": "60s",
            "func": "max",
            "time_column": "t",
            "min_periods": 1,
            "center": True,
        },
    ),
    "expanding": (timeseries.Expanding, {"columns": ["x"], "suffix": "_cumsum"}),
    "expanding_mean": (
        timeseries.Expanding,
        {"columns": ["x", "epoch"], "func": "mean", "min_periods": 2},
    ),
    "shift": (
        timeseries.Shift,
        {"columns": ["x"], "periods": -1, "fill_value": 0.0, "suffix": "_next"},
    ),
    "diff": (timeseries.Diff, {"columns": ["x", "t"], "suffix": "_diff"}),
    "pct_change": (timeseries.PctChange, {"columns": ["x"], "periods": 2}),
    "tolerance_bands": (timeseries.ToleranceBands, {"columns": ["x"], "window": 3, "pct": 0.1}),
    "tolerance_bands_time": (
        timeseries.ToleranceBands,
        {"columns": ["x", "epoch"], "window": "2min", "pct": 0.25, "time_column": "t"},
    ),
}
GOLDEN = {
    "str_case": 'df = df.assign(s=df["s"].str.upper(), g=df["g"].str.upper())',
    "str_case_suffix": 'df = df.assign(s_title=df["s"].str.title())',
    "str_strip": 'df = df.assign(s=df["s"].str.strip())',
    "str_strip_chars": 'df = df.assign(s=df["s"].str.rstrip(to_strip=" 12"))',
    "str_replace": 'df = df.assign(s=df["s"].str.replace("a", "A"))',
    "str_replace_regex": (
        "df = df.assign(\n"
        '    s=df["s"].str.replace("(\\\\w+)-(\\\\d+)", "\\\\2-\\\\1", regex=True, case'
        "=False),\n"
        ")"
    ),
    "str_slice": 'df = df.assign(s=df["s"].str.slice(start=1, stop=-1))',
    "str_pad": 'df = df.assign(g=df["g"].str.pad(3, fillchar="0"))',
    "str_len": 'df = df.assign(s_len=df["s"].str.len(), g_len=df["g"].str.len())',
    "str_repeat": 'df = df.assign(g=df["g"].str.repeat(3))',
    "str_test": 'df = df.assign(s_match=df["s"].str.contains("a", case=False, regex=False))',
    "str_test_startswith": 'df = df.assign(s=df["s"].str.startswith("b"))',
    "filter_text": 'df = df[df["s"].str.contains("a", na=False)]',
    "filter_text_invert": 'df = df[~df["s"].str.fullmatch("\\\\w+-\\\\d+", na=False)]',
    "str_extract": (
        'df = df.join(df["s"].str.extract("(?P<word>[a-zA-Z]+)\\\\W*(\\\\d+)").add_prefix("s_"))'
    ),
    "str_extract_prefix": 'df = df.join(df["s"].str.extract("(?P<number>\\\\d+)"))',
    "str_split": 'df = df.join(df["s"].str.split(",", n=1, expand=True).add_prefix("s_"))',
    "str_split_whitespace": 'df = df.join(df["s"].str.split(expand=True).add_prefix("part_"))',
    "to_datetime": 'df = df.assign(when=pd.to_datetime(df["when"], format="%d.%m.%Y %H:%M"))',
    "to_datetime_epoch": (
        'df = df.assign(epoch_time=pd.to_datetime(df["epoch"], unit="s", utc=True))'
    ),
    "float_year_to_datetime": (
        "df = df.assign(\n"
        '    year_date=pd.to_datetime((df["year"].astype("float64") // 1).astyp'
        'e("Int64").astype("string"), format="%Y") + pd.to_timedelta(df["year"]'
        '.astype("float64") % 1 * 365.25, unit="D"),\n'
        ")"
    ),
    "dt_parts": (
        "df = df.assign(\n"
        '    t_year=df["t"].dt.year,\n'
        '    t_month=df["t"].dt.month,\n'
        '    t_day=df["t"].dt.day,\n'
        '    t_hour=df["t"].dt.hour,\n'
        '    t_day_of_week=df["t"].dt.day_of_week,\n'
        '    t_date=df["t"].dt.date,\n'
        '    t_quarter=df["t"].dt.quarter,\n'
        ")"
    ),
    "dt_parts_names": (
        "df = df.assign(\n"
        '    naive_month_name=df["naive"].dt.month_name(),\n'
        '    naive_day_name=df["naive"].dt.day_name(),\n'
        ")"
    ),
    "dt_strftime": (
        "df = df.assign(\n"
        '    t=df["t"].dt.strftime("%d.%m.%Y %H:%M"),\n'
        '    naive=df["naive"].dt.strftime("%d.%m.%Y %H:%M"),\n'
        ")"
    ),
    "tz_localize": (
        "df = df.assign(\n"
        '    naive=df["naive"].dt.tz_localize("Europe/Berlin", nonexistent="shi'
        'ft_forward"),\n'
        ")"
    ),
    "tz_localize_remove": 'df = df.assign(t=df["t"].dt.tz_localize(None))',
    "tz_convert": 'df = df.assign(t=df["t"].dt.tz_convert("America/New_York"))',
    "dt_round": 'df = df.assign(naive=df["naive"].dt.round("1min"))',
    "dt_floor": 'df = df.assign(t_hour=df["t"].dt.floor("1h"))',
    "set_time_column": 'df = df.sort_values("t", kind="stable", ignore_index=True)',
    "resample": (
        "df = (\n"
        '    df.resample("1min", on="t")\n'
        '    .agg(x_mean=("x", "mean"), n=("s", "count"))\n'
        "    .reset_index()\n"
        ")"
    ),
    "resample_groups": (
        "df = (\n"
        '    df.groupby(["g", pd.Grouper(key="naive", freq="2min", closed="righ'
        't", label="right")])\n'
        '    .agg(**{"max x": ("x", "max")})\n'
        "    .reset_index()\n"
        ")"
    ),
    "upsample": 'df = df.set_index("t").resample("20s").ffill().reset_index()',
    "upsample_interpolate": 'df = df.set_index("naive").resample("30s").asfreq().reset_index()',
    "seconds_since_start": 'df = df.assign(secs=(df["t"] - df["t"].min()).dt.total_seconds())',
    "detect_gaps": (
        "df = df.assign(\n"
        '    segment=df["t"].diff().gt(pd.Timedelta("30s")).fillna(False).astyp'
        'e("int64").cumsum() + 1,\n'
        ")"
    ),
    "detect_gaps_numeric": (
        "df = df.assign(\n"
        '    part=df["epoch"].diff().gt(100.0).fillna(False).astype("int64").cu'
        "msum() + 1,\n"
        ")"
    ),
    "rolling": 'df = df.assign(x_avg=df["x"].rolling(3).mean())',
    "rolling_time": (
        "df = df.assign(\n"
        '    x=df.rolling("60s", on="t", min_periods=1, center=True)["x"].max()'
        ",\n"
        '    epoch=df.rolling("60s", on="t", min_periods=1, center=True)["epoch'
        '"].max(),\n'
        ")"
    ),
    "expanding": 'df = df.assign(x_cumsum=df["x"].expanding().sum())',
    "expanding_mean": (
        "df = df.assign(\n"
        '    x=df["x"].expanding(min_periods=2).mean(),\n'
        '    epoch=df["epoch"].expanding(min_periods=2).mean(),\n'
        ")"
    ),
    "shift": 'df = df.assign(x_next=df["x"].shift(periods=-1, fill_value=0.0))',
    "diff": 'df = df.assign(x_diff=df["x"].diff(), t_diff=df["t"].diff())',
    "pct_change": 'df = df.assign(x=df["x"].pct_change(periods=2))',
    "tolerance_bands": (
        "df = df.assign(\n"
        '    x_lower=df["x"].rolling(3, center=True, min_periods=1).min().clip('
        'upper=df["x"] * (1 - 0.1)),\n'
        '    x_upper=df["x"].rolling(3, center=True, min_periods=1).max().clip('
        'lower=df["x"] * (1 + 0.1)),\n'
        ")"
    ),
    "tolerance_bands_time": (
        "df = df.assign(\n"
        '    x_lower=df.rolling("2min", center=True, min_periods=1, on="t")["x"'
        '].min().clip(upper=df["x"] * (1 - 0.25)),\n'
        '    x_upper=df.rolling("2min", center=True, min_periods=1, on="t")["x"'
        '].max().clip(lower=df["x"] * (1 + 0.25)),\n'
        '    epoch_lower=df.rolling("2min", center=True, min_periods=1, on="t")'
        '["epoch"].min().clip(upper=df["epoch"] * (1 - 0.25)),\n'
        '    epoch_upper=df.rolling("2min", center=True, min_periods=1, on="t")'
        '["epoch"].max().clip(lower=df["epoch"] * (1 + 0.25)),\n'
        ")"
    ),
}
