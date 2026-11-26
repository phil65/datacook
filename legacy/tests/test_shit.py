"""Tests for `datacook` package."""

import pytest

from datacook.core import dataset
from datacook.methods.pandas import (
    datasetmethods,
    mergemethods,
    pandasmethods,
    stringmethods,
)


methods = [
    (datasetmethods.SelectDtypesMethod, dict(include=["bool"])),
    (datasetmethods.ConvertDtypesMethod, dict()),
    (datasetmethods.IsNaMethod, dict()),
    (datasetmethods.AbsMethod, dict()),
    (datasetmethods.QueryMethod, dict(expr="a < b")),
    (datasetmethods.AddPrefixMethod, dict(prefix="test")),
    (datasetmethods.AddSuffixMethod, dict(suffix="test")),
    (datasetmethods.ResetIndexMethod, dict()),
    (datasetmethods.RemoveIndexMethod, dict()),
    (datasetmethods.SetIndexMethod, dict(keys=["a"])),
    (datasetmethods.SortValuesMethod, dict(by=["a"])),
    (datasetmethods.SortIndexMethod, dict()),
    #    (datasetmethods.ReorderLevelsMethod, dict(order=[None])),
    (datasetmethods.DropMethod, dict(labels=["a"], axis=1)),
    (datasetmethods.DropDuplicatesMethod, dict()),
    (datasetmethods.InterpolateMethod, dict()),
    (datasetmethods.ShiftMethod, dict()),
    (datasetmethods.ClipMethod, dict()),
    (datasetmethods.ReplaceMethod, dict(to_replace="a", value="b")),
    (datasetmethods.DiffMethod, dict()),
    (datasetmethods.ReindexMethod, dict()),
    (datasetmethods.RenameMethod, dict(mapper={"a": "c"}, axis=1)),
    (datasetmethods.DropNaMethod, dict()),
    (datasetmethods.FillNaMethod, dict(method="bfill")),
    (datasetmethods.FillNaMethod, dict(method=None, value=0)),
    (datasetmethods.ReplaceWithNaMethod, dict(to_replace="z")),
    #    (datasetmethods.StackMethod, dict()),
    (datasetmethods.TransposeMethod, dict()),
    (datasetmethods.AsFreqMethod, dict(freq="1s")),
    (datasetmethods.MeltMethod, dict()),
    (datasetmethods.PivotMethod, dict(columns="a", index="b", values="c")),
    (datasetmethods.PivotTableMethod, dict(columns="a", index="b")),
    (datasetmethods.SampleMethod, dict(random_state=1)),
    (datasetmethods.NSmallestMethod, dict(n=2, columns=["a"])),
    (datasetmethods.NLargestMethod, dict(n=2, columns=["a"])),
    (datasetmethods.CorrMethod, dict()),
    (datasetmethods.RankMethod, dict()),
    (datasetmethods.ModeMethod, dict()),
    (datasetmethods.DescribeMethod, dict()),
    (datasetmethods.VarMethod, dict()),
    (datasetmethods.CovMethod, dict()),
]

string_methods = [
    (stringmethods.UpperMethod, dict()),
    (stringmethods.LowerMethod, dict()),
    (stringmethods.CapitalizeMethod, dict()),
    (stringmethods.SliceMethod, dict()),
    (stringmethods.ContainsMethod, dict(pat="a")),
    (stringmethods.ExtractMethod, dict(pat="(a)")),
    (stringmethods.MatchMethod, dict(pat="a")),
    (stringmethods.ReplaceMethod, dict(pat="a", repl="b")),
    (stringmethods.RepeatMethod, dict(repeats=2)),
    (stringmethods.SplitMethod, dict(pat="a")),
]

cat_methods = [
]

merge_methods: list = [
    (mergemethods.CorrWithMethod, dict()),
    (mergemethods.MergeMethod, dict()),
    # (mergemethods.AppendMethod, dict()),
]


def test_dataset(ds):
    ds.set_comment("testcomment")
    ds.instance = ds.reset_index()
    assert ds.comment == "testcomment"
    ds2 = ds.copy()
    method = pandasmethods.ConcatMethod(join="outer", axis=0)
    new = method.apply_method([ds, ds2])
    assert isinstance(new, dataset.DataSet)
    assert new.title == "2 merged datasets"
    # assert new.comment == "testcomment"


def test_dataset_merge(ds):
    ds1 = ds.copy()
    ds2 = ds.copy()
    method = pandasmethods.ConcatMethod(join="outer", axis=0)
    df = method.apply_method([ds1, ds2])
    hist = df.history.as_code()
    code = """import pandas

# Test
ds_1 = pandas.DataFrame(dict(a=["a", "b", "c"], b=["d", "e", "f"]))

# Test
ds_2 = pandas.DataFrame(dict(a=["a", "b", "c"], b=["d", "e", "f"]))

# Merge 2 datasets
ds = pandas.concat([ds_1, ds_2], sort=False)"""
    assert str(hist) == code
    # filepath = pathlib.Path(path)
    # reader = guihelpers.reader_for_path(filepath)
    # reader.read(filepath)


@pytest.mark.parametrize(("m", "kwargs"), methods)
def test_datasetmethods(m, kwargs, int_ds):
    method = m(**kwargs)
    result = method.apply_method(int_ds)
    result2 = result.history.evaluate()
    assert result2.equals(result.instance)


@pytest.mark.parametrize(("m", "kwargs"), methods)
def test_datasetmethods_on_partial(m, kwargs, int_ds):
    if not m.same_shape:
        return
    method = m(**kwargs)
    result = method.apply_method(int_ds, columns=["a"])
    result2 = result.history.evaluate()
    assert result2.equals(result.instance)


@pytest.mark.parametrize(("m", "kwargs"), string_methods)
def test_stringmethods(m, kwargs, ds):
    method = m(**kwargs)
    result = method.apply_method(ds, col="a")
    result2 = result.history.evaluate()
    assert result2.equals(result.instance)


@pytest.mark.parametrize(("m", "kwargs"), cat_methods)
def test_catmethods(m, kwargs, cat_ds):
    method = m(**kwargs)
    result = method.apply_method(cat_ds, col="a")
    result2 = result.history.evaluate()
    assert result2.equals(result.instance)


# @pytest.mark.parametrize("m, kwargs", merge_methods)
# def test_mergemethod(m, kwargs, int_ds):
#     ds_2 = int_ds.copy()
#     method = m(**kwargs)
#     result = method.apply_method(int_ds, ds_2)
#     result2 = result.history.evaluate()
#     assert result2.equals(result.instance)
