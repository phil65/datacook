"""Fixtures for the DataCook core tests."""

from __future__ import annotations

import pytest

from datacook.core import dataset


@pytest.fixture
def ds():
    ds = dataset.DataSet(dict(a=["a", "b", "c"], b=["d", "e", "f"]))
    ds.log(
        '|ds| = pandas.DataFrame(dict(a=["a", "b", "c"], b=["d", "e", "f"]))',
        imports=["pandas"],
        operation="import",
        description="Test",
    )
    return ds


@pytest.fixture
def cat_ds():
    cat_ds = dataset.DataSet(dict(a=["a", "b", "c"], b=["d", "e", "f"]))
    cat_ds["a"] = cat_ds["a"].astype("category")
    cat_ds.log(
        '|ds| = pandas.DataFrame(dict(a=["a", "b", "c"], b=["d", "e", "f"]))',
        '|ds|["a"] = |ds|["a"].astype("category")',
        imports=["pandas"],
        operation="import",
        description="Test",
    )
    return cat_ds


@pytest.fixture
def int_ds():
    ds = dataset.DataSet(dict(a=[1, 2, 3], b=[4, 5, 6], c=[4, 5, 6]))
    ds.log(
        "|ds| = pandas.DataFrame(dict(a=[1,2,3], b=[4,5,6], c=[4,5,6]))",
        imports=["pandas"],
        operation="import",
    )
    return ds


@pytest.fixture
def nested_dct():
    return {
        "lastName": "Smith",
        "age": 25,
        "address": {"streetAddress": "21 2nd Street", "postalCode": "10021"},
        "phoneNumber": [
            {"type": "home", "number": "212 555-1234"},
            {"type": "fax", "number": ("646 555-4567")},
        ],
    }
