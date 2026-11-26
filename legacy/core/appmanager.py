from __future__ import annotations

import pandas as pd
import logging
import pathlib
import time

from collections.abc import Mapping

from bidict import bidict

from processanalyzer import plugintypes
from processanalyzer.codeviewer import codeviewermixin, codeeditor
from processanalyzer.core import config
from processanalyzer.core.application import _
from processanalyzer.util import helpers

logger = logging.getLogger(__name__)


class AppManager:
    languages: Mapping = bidict(en=_("English"), de=_("German"))

    def __init__(self, *args, **kwargs):
        """
        initialize our app manager
        """
        self.codeviewers = {codeeditor.CodeEditor.name: codeeditor.CodeEditor}
        self.context_actions = []
        self.filereaders = []
        self.remote_readers = []
        self.exporters = []
        self.docks = []
        self.sidebar_items = []
        self.dtw_plugins = []
        self.selected_codeviewer = codeeditor.CodeEditor

    def load_plugins(self):
        """
        load plugins from plugin folder
        """
        logger.info("Collecting plugins...")
        now = time.time()
        self.codeviewers = {
            p.name: p for p in codeviewermixin.CodeViewerMixin.__subclasses__()
        }
        self.context_actions = plugintypes.PluginAction.__subclasses__()
        self.filereaders = [p() for p in plugintypes.FileReaderPlugin.__subclasses__()]
        self.remote_readers = [p() for p in plugintypes.ReaderPlugin.__subclasses__()]
        self.exporters = [p() for p in plugintypes.ExportPlugin.__subclasses__()]
        self.docks = plugintypes.DockPlugin.__subclasses__()
        self.sidebar_items = plugintypes.SidebarPlugin.__subclasses__()
        self.dtw_plugins = [p() for p in plugintypes.DTWPlugin.__subclasses__()]

        current_codeviewer = config.settings.default_codeviewer
        self.selected_codeviewer = self.codeviewers.get(current_codeviewer)
        logger.debug(f"Plugins collected. Process took {time.time() - now} seconds.")

    def supported_filetypes(self) -> list[str]:
        lists = [p.supported_extensions() for p in self.filereaders]
        return list({f"*{item}" for sublist in lists for item in sublist})

    def readers_for_path(self, path: pathlib.Path):
        return [p for p in self.filereaders if p.is_valid_reader_for(path)]

    def get_estimators(self, *types: str) -> list:
        from processanalyzer.core import estimator

        estimator_classes = [
            i for i in helpers.get_subclasses(estimator.Estimator) if i.alias is not None
        ]
        return (
            [
                est
                for typ in types
                for est in estimator_classes
                if est.identifier == typ
            ]
            if types
            else estimator_classes
        )

    def get_class_for_instance(self, instance):
        if isinstance(instance, pd.DataFrame):
            from processanalyzer.core import dataset

            return dataset.DataSet
        estimators = self.get_estimators()
        typ = type(instance)
        for est_model in estimators:
            if typ == est_model.obj:
                logger.info("found model for %s", typ)
                return est_model
        return None


instance = AppManager()
