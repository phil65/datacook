from __future__ import annotations

import pyreadstat

from pydantic import Field

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset
from processanalyzer.core.application import _
from processanalyzer.methods import base, methods
from processanalyzer.plugintypes import filereaderplugin


class StataParams(base.BaseModel):
    dates_as_pandas_datetime: bool = Field(title=_("Dates as DateTime Type"))


class BaseStataMethod(methods.BaseMethod):
    short_desc = "UNDEFINED"
    icon = iconnames.BINARY
    description = "Import Stata file"
    imports = ["pyreadstat"]
    Params = StataParams

    def apply_method(self, path):
        keyword_args = self.params.to_dict()
        method_name = self.obj.__name__
        df, meta = self.obj(str(path), **keyword_args)
        title = meta.table_name or path.name
        ds = dataset.DataSet(data=df, name=title)
        ds.log(
            f"|ds|, _ = pyreadstat.{method_name}(|ORIGIN||OPTKWARGS|)",
            imports=["pyreadstat"],
            operation="import",
            origin=path,
            description=f"Import from {path.suffix}",
            kwargs=keyword_args,
        )
        return ds


class ReadPorMethod(BaseStataMethod):
    obj = pyreadstat.read_por
    short_desc = "Read .por file"


class ReadSavMethod(BaseStataMethod):
    obj = pyreadstat.read_sav
    short_desc = "Read .sav file"


class ReadXportMethod(BaseStataMethod):
    obj = pyreadstat.read_xport
    short_desc = "Read .xport file"


class ReadDtaMethod(BaseStataMethod):
    obj = pyreadstat.read_dta
    short_desc = "Read .dta file"


class StataReader(filereaderplugin.FileReaderPlugin):
    menu_label = "Stata / SAS file"
    extensions = {
        "SPSS por file": [".por"],
        "SPSS sav file": [".sav", ".zsav"],
        "SAS Xport file": [".xpt"],
        # "SAS catalog file": [".sas7bcat"],
        "STATA dta file": [".dta"],
    }
    plugin_id = "reader.stata"
    icon = iconnames.BINARY

    def read_file(self, path):
        if path.suffix in self.extensions["SPSS por file"]:
            method = ReadPorMethod()
        elif path.suffix in self.extensions["SPSS sav file"]:
            method = ReadSavMethod()
            # kwargs["apply_value_formats"] = True
        elif path.suffix in self.extensions["SAS Xport file"]:
            method = ReadXportMethod()
        elif path.suffix in self.extensions["STATA dta file"]:
            method = ReadDtaMethod()
        else:
            return None
        ds = method.apply_method(path)
        yield ds
