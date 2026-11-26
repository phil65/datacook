from __future__ import annotations

import pathlib
import sys

from processanalyzer.constants import iconnames
from processanalyzer.core import pluginmanager


class BasePlugin:
    Settings = None
    settings = None
    plugin_id: str = ""
    name: str = ""
    version: str = ""
    author: str = ""
    icon: str = iconnames.WIDGET
    context_label: str = "Not set"

    def get_plugin_info(cls):
        mod = sys.modules[cls.__module__]
        if mod.__file__ is None:
            raise FileNotFoundError
        path = pathlib.Path(mod.__file__).parent
        return pluginmanager.instance.plugins.get(path.name)
