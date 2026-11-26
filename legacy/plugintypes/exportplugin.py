from __future__ import annotations

from prettyqt import widgets

from processanalyzer.constants import iconnames
from processanalyzer.core import threads
from processanalyzer.core.application import _
from processanalyzer.plugintypes import baseplugin


class ExportPlugin(baseplugin.BasePlugin):
    plugin_category = "Export"
    extension = ".*"

    def export(self, df):
        """
        write to cache
        """
        pass

    def run(self, fn, *args, **kwargs):
        worker = threads.Worker(fn, *args, **kwargs)
        worker.signals.finished.connect(self.finished)
        threads.pool.start(worker, set_busy=True, message=_("Exporting..."))

    @classmethod
    def get_path(cls):
        dlg = widgets.FileDialog(mode="save", caption=_("Save data file"))
        dlg.set_extension_filter({_("Data file"): [cls.extension]})
        result = dlg.open_file()
        if result:
            return result[0]

    def finished(self):
        popup = widgets.MessageBox(
            icon="information", title=_("Export"), text=_("Export successful.")
        )
        popup.set_icon(iconnames.PROPERTIES)
        popup.main_loop()


if __name__ == "__main__":
    app = widgets.app()
    plg = ExportPlugin()
    plg.finished()
    print(plg.get_path())
