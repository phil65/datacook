"""Tests for `datacook` package."""

import numpy as np

from datacook.util import helpers


def test_move_in_list():
    pass


def test_format_kwargs():
    dct = dict(a="test", b=2.5, c=np.nan)
    result = helpers.format_kwargs(dct)
    assert result == "a='test', b=2.5, c=numpy.nan"


def test_infer_type():
    assert helpers.infer_type("2") == 2  # noqa: PLR2004
    assert helpers.infer_type("2.1") == 2.1  # noqa: PLR2004
    assert helpers.infer_type("abc") == "abc"


def test_format_name():
    assert helpers.format_name(["a", "b"]) == "a | b"
    assert helpers.format_name(5) == "5"
    assert helpers.format_name("test") == "test"


def test_is_nan():
    assert not helpers.is_nan(0)
    assert not helpers.is_nan(1)
    assert not helpers.is_nan(2)
    assert helpers.is_nan(float("nan"))
    assert helpers.is_nan(np.nan)
