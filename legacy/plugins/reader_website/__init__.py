from __future__ import annotations

import functools
import logging

import pandas as pd

import prettyqt.custom_widgets.dataset as fo
from processanalyzer.constants import iconnames
from processanalyzer.core import dataset
from processanalyzer.plugintypes import readerplugin

logger = logging.getLogger(__name__)


class WebsiteReader(readerplugin.ReaderPlugin):
    menu_label = "from website"
    plugin_id = "reader.website"
    icon = iconnames.WEB

    def read(self, path=None):
        class Dialog(fo.DataSet):
            url = fo.String("Website URL", notempty=True)

        dlg = Dialog(
            title=self.menu_label,
            icon=self.icon,
            comment=(
                "Read tables from a website. Enter the URL and "
                "the plugin will try to scan the website for tables."
            ),
        )

        if not dlg.edit():
            return None

        dct = dlg.to_dict()
        gen = functools.partial(yield_datasets, dct["url"])
        self.yield_async(gen)


def yield_datasets(url):
    try:
        dfs = pd.read_html(url)
        for i, df in enumerate(dfs):
            ds = dataset.DataSet(data=df, name=url)
            ds.log(
                f"|ds| = pandas.read_html(|ORIGIN|)[{i}]",
                imports=["pandas"],
                operation="import",
                origin=url,
                description=f"Import from {url}",
            )
            yield ds
    except (UnicodeEncodeError, ValueError) as e:
        logger.exception(e)
