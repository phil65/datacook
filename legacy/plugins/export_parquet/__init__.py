from __future__ import annotations

import pandas as pd
from pydantic import Field

from processanalyzer.constants import iconnames
from processanalyzer.core.application import _
from processanalyzer.methods import base, methods
from processanalyzer.plugintypes import exportplugin

COMPRESSIONS = ["gzip", "brotli", None]  # "snappy"
FILE_SCHEMES = ["SIMPLE"]
ENGINES = ["pyarrow", "fastparquet"]


class ToParquetMethod(methods.ExportMethod):
    icon = iconnames.WEB
    description = _("Export to Parquet")
    short_desc = _("Export to Parquet")
    obj = pd.DataFrame.to_parquet

    class Params(base.BaseModel):
        compression: str | None = Field(
            "gzip", title=_("Compression mode"), mapping=COMPRESSIONS
        )
        # file_scheme = Field(title=_("File scheme"), mapping=FILE_SCHEMES)
        engine: str = Field("pyarrow", title=_("Engine"), mapping=ENGINES)


class ParquetExporter(exportplugin.ExportPlugin):
    extension = ".parquet"
    menu_label = "Parquet file"
    icon = iconnames.FILE

    def export(self, ds):
        path = self.get_path()

        if not path:
            return None
        method = ToParquetMethod()
        self.run(method.apply_method, ds)
