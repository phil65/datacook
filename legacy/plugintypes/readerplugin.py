from __future__ import annotations

from processanalyzer.core import signals, threads
from processanalyzer.core.application import _
from processanalyzer.plugintypes import baseplugin


class ReaderPlugin(baseplugin.BasePlugin):
    plugin_category = "RemoteReader"

    @classmethod
    def yield_async(cls, generator):
        worker = threads.Worker(load, generator)
        threads.pool.start(worker, set_busy=False, message=_("Importing..."))

    def read(self, paths=None):
        pass


def load(generator):
    datasets = [ds for ds in generator()]
    signals.signals.add_datasets.emit(datasets)
