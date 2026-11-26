"""Fixtures for the engine tests."""

import importlib.util

import pandas as pd
import pytest

from datacook.engine import Session


# App (Qt) tests live in tests/app/. They are skipped where Qt is not installed, e.g. the
# free-threaded (3.14t) CI job: PySide6 / PyQt6 have no cp314t wheels yet.
collect_ignore = [] if importlib.util.find_spec("PySide6") else ["app"]


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame({
        "k": [1, 2, 3, 1, 2],
        "x": [1.5, None, 3.0, 4.0, 3.0],
        "s": ["a", "b", None, "d", "b"],
        "i": [10, 20, 30, 40, 50],
    }).convert_dtypes(dtype_backend="pyarrow")


@pytest.fixture
def other() -> pd.DataFrame:
    return pd.DataFrame({"k": [1, 2, 4], "label": ["one", "two", "four"]}).convert_dtypes(
        dtype_backend="pyarrow"
    )


@pytest.fixture
def session():
    with Session() as s:
        yield s
