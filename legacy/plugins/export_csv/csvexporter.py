from __future__ import annotations

import pathlib
import logging

import pandas as pd

import prettyqt.custom_widgets.dataset as fo
from pydantic import Field

from processanalyzer.constants import iconnames
from processanalyzer.core.application import _
from processanalyzer.methods import base, methods
from processanalyzer.plugintypes import exportplugin

logger = logging.getLogger(__name__)


class ToCsvMethod(methods.ExportMethod):
    icon = iconnames.TABLE
    description = _("Export to CSV")
    short_desc = _("Export to CSV")
    obj = pd.DataFrame.to_csv

    class Params(base.BaseModel):
        path_or_buf: pathlib.Path | str | None = Field(None, title=_("Path"))
        sep: str = Field(",", title=_("Separator"), min_length=1)
        decimal: str | None = Field(",", title=_("Decimal sign"), min_length=1)
        index: bool = Field(title=_("Include index"))
        header: bool | list[str] = Field(True, title=_("Include headers"))
        na_rep: str = Field("nan", title=_("Value for NaN"))


class CSVExporter(exportplugin.ExportPlugin):
    extension = ".csv"
    menu_label = "CSV file"
    icon = iconnames.TABLE

    def export(self, ds):
        class Dialog(fo.DataSet):
            path_or_buf = fo.File("Path", formats=self.extension)
            sep = fo.String("Separator", value=";", notempty=True)
            decimal = fo.String("Decimal sign", value=",", notempty=True)
            index = fo.Bool("Include index")
            header = fo.Bool("Include headers", value=True)
            na_rep = fo.String("Value for NaN", value="nan")

        dlg = Dialog(title="Export as .csv file", icon=self.icon)

        if not dlg.edit():
            return None
        keyword_args = dlg.to_dict()
        method = ToCsvMethod(**keyword_args)
        self.run(method.apply_method, ds)
