"""Op test cases: (op class, params kwargs, number of inputs)."""

from datacook.engine.ops import categorical, code, columns, combine, missing, rows, values


CASES = {
    "select_columns": (columns.SelectColumns, {"columns": ["s", "k"]}),
    "drop_columns": (columns.DropColumns, {"columns": ["i"]}),
    "rename_columns": (columns.RenameColumns, {"columns": {"x": "value", "s": "name"}}),
    "astype": (columns.ChangeDtypes, {"dtype": {"i": "float32", "k": "string[pyarrow]"}}),
    "filter_rows": (rows.FilterRows, {"expr": "x > 1.5 and k != 2"}),
    "sort_rows": (rows.SortRows, {"by": ["k", "x"], "ascending": [True, False]}),
    "sort_rows_defaults": (rows.SortRows, {"by": ["x"]}),
    "head": (rows.Head, {"n": 3}),
    "sample": (rows.Sample, {"n": 2, "random_state": 7}),
    "drop_duplicates": (rows.DropDuplicates, {"subset": ["s"], "keep": "last"}),
    "fill_missing": (missing.FillMissing, {"value": {"x": 0.0, "s": "?"}}),
    "ffill": (missing.FillForward, {}),
    "bfill": (missing.FillBackward, {"limit": 1}),
    "drop_missing": (missing.DropMissing, {"how": "any", "subset": ["x"]}),
    # WP4.1 general / columns
    "move_columns": (columns.MoveColumns, {"columns": ["s", "i"]}),
    "move_columns_last": (columns.MoveColumns, {"columns": ["k"], "position": "last"}),
    "sort_columns": (columns.SortColumns, {"ascending": False}),
    "add_prefix": (columns.AddPrefix, {"prefix": "col_"}),
    "add_suffix": (columns.AddSuffix, {"suffix": "_1"}),
    "select_dtypes": (columns.SelectDtypes, {"include": ["number"]}),
    "select_dtypes_exclude": (columns.SelectDtypes, {"exclude": ["number", "category"]}),
    "convert_dtypes": (columns.ConvertDtypes, {}),
    "convert_dtypes_numpy": (columns.ConvertDtypes, {"dtype_backend": "numpy_nullable"}),
    "downcast": (columns.Downcast, {"columns": ["k", "i"]}),
    "duplicate_columns": (columns.DuplicateColumns, {"columns": ["x", "s"]}),
    "combine_columns": (columns.CombineColumns, {"columns": ["s", "k", "x"], "name": "label"}),
    "combine_columns_missing": (
        columns.CombineColumns,
        {"columns": ["s", "k"], "name": "s k", "sep": "-", "na_rep": None},
    ),
    "calculate_columns": (columns.CalculateColumns, {"expr": "y = x * 2 + i\nbig = y > 40"}),
    "tail": (rows.Tail, {"n": 2}),
    "nlargest": (rows.NLargest, {"n": 2, "columns": ["x"]}),
    "nsmallest": (rows.NSmallest, {"n": 2, "columns": ["k", "i"], "keep": "all"}),
    "slice_rows": (rows.SliceRows, {"start": 1, "stop": -1}),
    "slice_rows_step": (rows.SliceRows, {"step": 2}),
    "filter_isin": (rows.FilterIsIn, {"column": "s", "values": ["a", "b"]}),
    "filter_isin_invert": (rows.FilterIsIn, {"column": "k", "values": [1], "invert": True}),
    "reset_index": (rows.ResetIndex, {"drop": True}),
    "abs": (values.Abs, {"columns": ["x"]}),
    "clip": (values.Clip, {"columns": ["x", "i"], "lower": 2.0, "upper": 35.0}),
    "replace_values": (values.ReplaceValues, {"to_replace": [3.0], "value": 0.0}),
    "replace_values_missing": (
        values.ReplaceValues,
        {"to_replace": ["a", "d"], "columns": ["s"]},
    ),
    # WP4.2 missing values
    "ffill_columns": (missing.FillForward, {"columns": ["x"]}),
    "fill_statistic": (missing.FillWithStatistic, {"columns": ["x"], "statistic": "median"}),
    "fill_statistic_mode": (missing.FillWithStatistic, {"columns": ["s"], "statistic": "mode"}),
    "interpolate": (missing.Interpolate, {"columns": ["x"], "limit_direction": "both"}),
    "drop_missing_columns": (missing.DropMissingColumns, {"how": "any"}),
    "isna": (missing.IsMissing, {}),
    "filter_missing": (missing.FilterMissing, {}),
    "filter_missing_columns": (missing.FilterMissing, {"columns": ["x", "s"], "how": "all"}),
    "nan_to_missing": (missing.NanToMissing, {}),
    "nan_to_missing_columns": (missing.NanToMissing, {"columns": ["x"]}),
    # WP4.5 categorical
    "cat_add_categories": (categorical.AddCategories, {"column": "c", "new_categories": ["z"]}),
    "cat_remove_categories": (
        categorical.RemoveCategories,
        {"column": "c", "removals": ["a"]},
    ),
    "cat_rename_categories": (
        categorical.RenameCategories,
        {"column": "c", "new_categories": {"a": "A", "b": "B"}},
    ),
    "cat_reorder_categories": (
        categorical.ReorderCategories,
        {"column": "c", "new_categories": ["d", "b", "a"], "ordered": True},
    ),
    "cat_set_categories": (
        categorical.SetCategories,
        {"column": "c", "new_categories": ["b", "d", "e"]},
    ),
    "cat_as_ordered": (categorical.AsOrdered, {"column": "c"}),
    "cat_as_unordered": (categorical.AsUnordered, {"column": "c"}),
    "cat_remove_unused": (categorical.RemoveUnusedCategories, {"column": "c"}),
    "merge": (combine.Merge, {"how": "left", "on": ["k"]}),
    "groupby_aggregate": (
        combine.GroupByAggregate,
        {
            "by": ["k"],
            "aggregations": [
                {"column": "x", "func": "sum"},
                {"column": "i", "func": "max", "name": "largest"},
            ],
        },
    ),
    "groupby_aggregate_names": (
        combine.GroupByAggregate,
        {
            "by": ["s"],
            "aggregations": [{"column": "x", "func": "mean", "name": "mean x"}],
            "dropna": False,
        },
    ),
    "custom_code": (
        code.CustomCode,
        {"code": 'df["twice"] = df["i"] * 2\ndf = df[df["twice"] > 20]'},
    ),
}
