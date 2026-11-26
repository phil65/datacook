from __future__ import annotations

import win32com.client as win32

from processanalyzer.constants import iconnames
from processanalyzer.core import application, dataset, threads
from processanalyzer.plugintypes import contextmenuplugin


class OpenInExcelAction(contextmenuplugin.PluginAction):
    icon = iconnames.EXCEL
    description = "Open in Excel"
    short_desc = "Open in Excel"

    def is_visible(self):
        if len(self.indexes) != 1:
            return False
        data = next(self.selected_data())
        if isinstance(data, dataset.DataSet):
            return True

    def process(self, **kwargs):
        worker = threads.Worker(self.open_in_excel)
        threads.pool.start(worker, message="Opening...")

    def open_in_excel(self):
        ds = next(self.selected_data())
        # Define the full path for the output file
        out_file = application.CACHE_DIR / "temp.xlsx"
        # Save the file as Excel
        ds.to_excel(out_file)
        # Open up Excel and make it visible
        excel = win32.gencache.EnsureDispatch("Excel.Application")
        # throws pywintypes.com_error if not installed
        excel.Visible = True
        # Open up the file
        excel.Workbooks.Open(out_file)
