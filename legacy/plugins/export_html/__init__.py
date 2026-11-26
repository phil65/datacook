from __future__ import annotations

import pathlib

import pandas as pd
import prettyqt.custom_widgets.dataset as fo
from pydantic import Field

from processanalyzer.constants import iconnames
from processanalyzer.core.application import _
from processanalyzer.methods import base, methods
from processanalyzer.plugintypes import exportplugin

ALIGNMENTS = [
    ("left", "Left"),
    ("right", "Right"),
    ("center", "Center"),
    ("justify", "Justify"),
]


class ToHtmlMethod(methods.ExportMethod):
    icon = iconnames.WEB
    description = _("Export to HTML")
    short_desc = _("Export to HTML")
    obj = pd.DataFrame.to_html

    class Params(base.BaseModel):
        buf: pathlib.Path | str | None = Field(None, title=_("Path"))
        justify: str | None = Field(None, title=_("Alignment"), mapping=ALIGNMENTS)
        index: bool = Field(True, title=_("Include index"))
        header: bool = Field(True, title=_("Include headers"))
        na_rep: str | None = Field("NaN", title=_("Value for NaN"))
        # justify: str | None = Field(title=_("Justify"), default=None)
        # bold_rows: bool = Field(title=_("Bold row labels"), default=True)


class HTMLExporter(exportplugin.ExportPlugin):
    extension = ".html"
    menu_label = "HTML file"
    icon = iconnames.WEB

    def export(self, ds):
        class Dialog(fo.DataSet):
            buf = fo.File("Path", self.extension)
            justify = fo.Enum("Alignment", ALIGNMENTS)
            index = fo.Bool("Include index").set_pos(col=1)
            header = fo.Bool("Include headers", value=True).set_pos(col=1)
            na_rep = fo.String("Value for NaN", value="nan")

        dlg = Dialog(title="Export as .html file", icon=self.icon)

        if not dlg.edit():
            return None

        keyword_args = dlg.to_dict()
        method = ToHtmlMethod(**keyword_args)
        self.run(method.apply_method, ds)
