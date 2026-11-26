from __future__ import annotations

import tabula

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin


class PDFReader(filereaderplugin.FileReaderPlugin):
    menu_label = "PDF file"
    extensions = {"PDF files": [".pdf"]}
    plugin_id = "reader.pdf"
    icon = iconnames.PDF

    def read_file(self, path):
        ds = dataset.DataSet(data=tabula.read_pdf(path), name=path.name)
        ds.log(
            "|ds| = tabula.read_pdf(|ORIGIN|)",
            imports=["tabula"],
            operation="import",
            origin=path,
            description="Import from PDF",
        )
        yield ds
