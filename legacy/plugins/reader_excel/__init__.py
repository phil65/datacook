from __future__ import annotations

import pandas as pd

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin
from processanalyzer.methods import methods


class ReadExcelMethod(methods.BaseMethod):
    short_desc = "Read Excel file"
    obj = pd.read_excel
    icon = iconnames.TABLE
    description = "Import CSV file"
    imports = ["pandas"]

    def apply_method(self, path):
        ds = dataset.DataSet(data=pd.read_excel(path), name=path.name)
        match path.suffix:
            case ".ods":
                engine = "odf"
            case ".xlsb":
                engine = "pyxlsb"
            case ".xlsx" | ".xlsm":
                engine = "openpyxl"
            case _:
                engine = "xlrd"
        ds.log(
            f"|ds| = pandas.read_excel(|ORIGIN|, engine='{engine}')",
            imports=["pandas"],
            operation="import",
            origin=path,
            description="Import from Excel file",
        )
        return ds


class ExcelReader(filereaderplugin.FileReaderPlugin):
    extensions = {
        "Excel files": [".xls", ".xlsx", ".xlsm"],
        "Excel binary files": [".xlsb"],
        "OpenDocument spreadsheets": [".ods"],
    }
    menu_label = "Excel file"
    plugin_id = "reader.excel"
    icon = iconnames.EXCEL

    def read_file(self, path):
        method = ReadExcelMethod()
        ds = method.apply_method(path)
        yield ds

        # for df in pf.iter_row_groups():
        #     yield pf.to_pandas()
