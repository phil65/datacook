from __future__ import annotations

import inspect
import logging
from typing import Any, ClassVar

import pandas as pd

from datacook.methods import base
from datacook.util import helpers


logger = logging.getLogger(__name__)


class BaseMethod:
    short_desc = "UNDEFINED"
    icon: str | None = None
    description: str | None = None
    comment: str | None = None
    # the wrapped pandas callable (function, method or accessor method)
    obj: Any = None
    imports: ClassVar[list[str]] = []

    class Params(base.BaseModel):
        pass

    def __init__(self, *args, **kwargs):
        self.params = self.Params(*args, **kwargs)

    @property
    def method_name(self) -> str:
        """Name of the wrapped pandas callable."""
        if self.obj is None:
            msg = f"{type(self).__name__} does not wrap a callable"
            raise TypeError(msg)
        return self.obj.__name__

    # def has_params(self) -> bool:
    #     dct = {a: b for a, b in self.get_param_values() if a != "name"}
    #     return bool(dct)

    def get_nondefault_params(self) -> dict[str, Any]:
        if self.obj is None:
            raise TypeError
        sig = inspect.signature(self.obj)
        dct = {p.name: p.default for p in sig.parameters.values() if p.default is not p.empty}
        return {
            k: v
            for k, v in self.params.to_dict().items()
            if (k in dct and dct[k] != v) or k not in dct
        }


class ExportMethod(BaseMethod):
    def apply_method(self, ds):
        keyword_args = self.get_nondefault_params()
        method_name = self.method_name
        getattr(ds, method_name)(**keyword_args)
        ds.log(
            f"|ds|.{method_name}(|KWARGS|)",
            operation="export",
            description=self.short_desc,
            kwargs=keyword_args,
        )
        return ds


class DatasetMethod(BaseMethod):
    accessor = ""
    same_shape = False

    def apply_method(self, ds, columns=None):
        ds = ds.copy()
        log = self.log_template(columns)
        if columns is None:
            apply_to_partial = False
            columns = ds.columns.tolist()
        else:
            apply_to_partial = True
        keyword_args = self.get_nondefault_params()
        method_name = self.method_name
        if self.accessor:
            base = getattr(ds[columns], self.accessor.rstrip("."))
            new = getattr(base, method_name)(**keyword_args)
        else:
            new = getattr(ds[columns], method_name)(**keyword_args)
        if isinstance(new, pd.Series):
            convert = ".to_frame()"
            new = new.to_frame()
        else:
            convert = ""
        if apply_to_partial:
            ds.instance[columns] = new
        else:
            ds.instance = new
        ds.log(
            f"{log}{convert}",
            description=self.short_desc,
            kwargs=keyword_args,
            imports=self.imports,
        )
        return ds

    def log_template(self, columns=None):
        method_name = self.method_name
        start = f"|ds|[{columns}] = |ds|[{columns}]" if columns is not None else "|ds| = |ds|"
        return f"{start}.{self.accessor}{method_name}(|KWARGS|)"

    def preview_log(self, columns=None):
        text = self.log_template(columns)
        dct = self.get_nondefault_params()
        text = text.replace("|KWARGS|", helpers.format_kwargs(dct))
        return text.replace("|OPTKWARGS|", helpers.format_kwargs(dct, prepend_comma=True))


class FilterMethod(BaseMethod):
    accessor = ""

    def apply_method(self, ds):
        ds = ds.copy()
        keyword_args = self.get_nondefault_params()
        method_name = self.method_name
        if self.accessor:
            base = getattr(ds, self.accessor.rstrip("."))
            new = getattr(base, method_name)(**keyword_args)
        else:
            new = getattr(ds, method_name)(**keyword_args)
        ds.instance = new
        ds.log(
            f"|ds| = |ds|.{method_name}(|KWARGS|)",
            description=self.short_desc,
            kwargs=keyword_args,
            imports=self.imports,
        )
        return ds

    def log_template(self):
        method_name = self.method_name
        return f"|ds| = |ds|[|ds|[...].{self.accessor}{method_name}(|KWARGS|)]"

    def preview_log(self, columns=None):
        text = self.log_template()
        text = text.replace("|ds|", f"ds{columns}") if columns else text.replace("|ds|", "ds")
        dct = self.get_nondefault_params()
        text = text.replace("|KWARGS|", helpers.format_kwargs(dct))
        return text.replace("|OPTKWARGS|", helpers.format_kwargs(dct, prepend_comma=True))


class DatasetPtMethod(DatasetMethod):
    accessor = "pt."
    imports: ClassVar[list[str]] = ["pandastools"]


class SeriesMethod(BaseMethod):
    accessor = ""

    def apply_method(self, ds, col):
        keyword_args = self.get_nondefault_params()
        method_name = self.method_name
        if self.accessor:
            base = getattr(ds[col], self.accessor.rstrip("."))
            ds[col] = getattr(base, method_name)(**keyword_args)
        else:
            ds[col] = getattr(ds[col], method_name)(**keyword_args)
        ds.log(
            self.log_template(col),
            description=self.short_desc,
            kwargs=keyword_args,
            imports=self.imports,
        )
        return ds

    def log_template(self, col):
        method_name = self.method_name
        return f"|ds|[{col!r}] = |ds|[{col!r}].{self.accessor}{method_name}(|KWARGS|)"

    def preview_log(self, col):
        text = self.log_template(col)
        text = text.replace("|ds|", "ds")
        dct = self.get_nondefault_params()
        text = text.replace("|KWARGS|", helpers.format_kwargs(dct))
        return text.replace("|OPTKWARGS|", helpers.format_kwargs(dct, prepend_comma=True))


class IndexMethod(BaseMethod):
    accessor = ""

    def apply_method(self, ds, level=None):
        keyword_args = self.get_nondefault_params()
        method_name = self.method_name
        base = getattr(ds.index, self.accessor.rstrip(".")) if self.accessor else ds.index
        ds.index = getattr(base, method_name)(**keyword_args)
        ds.log(
            self.log_template(),
            description=self.short_desc,
            kwargs=keyword_args,
            imports=self.imports,
        )
        return ds

    def log_template(self):
        method_name = self.method_name
        return f"|ds|.index = |ds|.index.{self.accessor}{method_name}(|KWARGS|)"

    def preview_log(self):
        text = self.log_template()
        text = text.replace("|ds|", "ds")
        dct = self.get_nondefault_params()
        text = text.replace("|KWARGS|", helpers.format_kwargs(dct))
        return text.replace("|OPTKWARGS|", helpers.format_kwargs(dct, prepend_comma=True))


class StringMethod(SeriesMethod):
    accessor = "str."


class DateTimeMethod(SeriesMethod):
    accessor = "dt."


class CategoryMethod(BaseMethod):
    def apply_method(self, ds, col):
        method = self.method_name
        keyword_args = self.get_nondefault_params()
        getattr(ds[col].cat, method)(**keyword_args)
        ds.log(
            f"|ds|{[col]}.cat.{method}(|KWARGS|)",
            description=self.short_desc,
            kwargs=keyword_args,
        )
        return ds
