from __future__ import annotations

import logging

import pandas as pd

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset, signals
from processanalyzer.plugintypes import readerplugin

logger = logging.getLogger(__name__)


class ClipboardReader(readerplugin.ReaderPlugin):
    menu_label = "from clipboard"
    plugin_id = "reader.clipboard"
    icon = iconnames.CLIPBOARD

    def read(self, path=None):
        try:
            df = pd.read_clipboard(na_values=[None], parse_dates=["d"])
            ds = dataset.DataSet(data=df, name="Clipboard")
            ds.log(
                "|ds| = pandas.read_clipboard(na_values=[None], parse_dates=['d'])",
                imports=["pandas"],
                operation="import",
                description="Import from Clipboard",
            )
            signals.signals.add_dataset_and_focus.emit(ds)
        except ValueError as e:
            logger.exception(e)
