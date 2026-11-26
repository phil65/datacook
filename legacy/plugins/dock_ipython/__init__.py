from __future__ import annotations

import logging

from qtconsole.inprocess import QtInProcessKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget

from prettyqt import core, widgets, qt
from processanalyzer.constants import iconnames
from processanalyzer.core import dataset, signals
from processanalyzer.gui import toolbars
from processanalyzer.plugintypes import contextmenuplugin, sidebarplugin

logger = logging.getLogger(__name__)


class Signals(core.Object):
    """
    Defines the signals available for this widget

    """

    push_vars = core.Signal(dict)
    pull_var = core.Signal(str)


class IPythonDockWidget(sidebarplugin.SidebarPlugin):
    signals = Signals()
    DEFAULT_POSITION = "right"
    plugin_id = "dock.ipython"
    icon = iconnames.PYTHON
    context_label = "IPython"

    def __init__(self, *args, **kwargs):
        super().__init__(parent=kwargs.get("parent"))
        layout = widgets.BoxLayout("horizontal", parent=self, margin=0)
        self.console_widget = ConsoleWidget(parent_widget=self)
        layout += self.console_widget
        self.signals.push_vars.connect(self.push_vars)
        self.signals.pull_var.connect(self.console_widget.eval)
        # push some variables to the console
        objects = {"clc": self.console_widget.clear, "window": kwargs.get("parent")}
        self.console_widget.push_vars(objects)

    def push_vars(self, var_dict):
        win = widgets.Application.get_mainwindow()
        win.set_tab(self)
        self.console_widget.push_vars(var_dict)

    # def delete(self):
    #     self.console_widget.kernel_client.stop_channels()
    #     self.console_widget.kernel_manager.shutdown_kernel()
    #     logger.info("here")


class IPythonAction(contextmenuplugin.PluginAction):
    icon = iconnames.PYTHON
    description = "Push to IPython console"
    short_desc = "Push to IPython console"

    def process(self, **kwargs):
        data = list(self.selected_data())
        objects = dict(data=data[0]) if len(data) == 1 else dict(data=data)
        IPythonDockWidget.signals.push_vars.emit(objects)


class ConsoleWidget(widgets.WidgetMixin, RichJupyterWidget):
    """
    Convenience class for a live IPython console widget.
    We can replace the standard banner using the customBanner argument
    """

    def __init__(self, *args, **kwargs):
        self.parent_widget = kwargs.pop("parent_widget")
        super().__init__(*args, **kwargs)

        toolbar = self.get_toolbar()
        self.layout().setMenuBar(toolbar)

        lines = [
            "IPython console.\n\n",
            "following objects have been loaded:\n",
            "app: instance of current application\n\n",
        ]
        self.banner = "".join(lines)
        self.font_size = 6
        self.gui_completion = "droplist"
        widgets.Application.styleHints().colorSchemeChanged.connect(
            self.adjust_style_to_palette
        )
        self.adjust_style_to_palette()
        self.kernel_manager = QtInProcessKernelManager()
        self.kernel_manager.start_kernel(show_banner=False)

        def _abort_queues(kernel):
            """override to prevent breaking when exception occurs"""
            pass

        self.kernel_manager.kernel._abort_queues = _abort_queues
        self.kernel_manager.kernel.log.setLevel(logging.CRITICAL)
        self.kernel_manager.kernel.gui = "qt"
        self.kernel_manager.kernel.shell.enable_matplotlib(gui="inline")
        self.kernel_client = self._kernel_manager.client()
        self.kernel_client.start_channels()

        def stop():
            logger.info("shutting down IPython kernel...")
            self.kernel_client.stop_channels()
            self.kernel_manager.shutdown_kernel()
            logger.info("shutdown successful.")

        widgets.Application.call_on_exit(stop)
        # self.exit_requested.connect(stop)

    def adjust_style_to_palette(self):
        pal = widgets.Application.get_palette()
        style = "linux" if pal.is_dark() else "lightbg"
        self.set_default_style(style)

    def push_vars(self, var_dict):
        """
        Given a dictionary containing name / value pairs, push those variables
        to the IPython console widget
        """
        self.kernel_manager.kernel.shell.push(var_dict)
        for key in var_dict.keys():
            self._append_plain_text(f'\nadded "{key}" object to namespace\n', True)

    def eval(self, obj_name):
        """
        Pull object with name *obj_name from namespace
        """
        try:
            data = self.kernel_manager.kernel.shell.ev(obj_name)
        except NameError as e:
            logger.exception(e)
            return None
        if not isinstance(data, dataset.DataSet):
            logger.error("Error: Can only read datasets")
            return None
        self._append_plain_text(f'\nread "{obj_name}" object to namespace\n', True)
        signals.signals.add_dataset_and_focus.emit(data)

    def clear(self):
        """
        Clears the terminal
        """
        self._control.clear()

        # self.kernel_manager

    def print_text(self, text):
        """
        Prints some plain text to the console
        """
        self._append_plain_text(text)

    def execute_command(self, command):
        """
        Execute a command in the frame of the console widget
        """
        self._execute(command, False)

    def get_toolbar(self):
        tb = toolbars.ToolBar()
        tb.add_action("Extract dataset", iconnames.EXTRACT, self.add_as_dataset)
        return tb

    def add_as_dataset(self):
        var_name = widgets.InputDialog.get_text(
            "Name of variable to read", "IPython dock", iconnames.EXTRACT, "ds"
        )
        if var_name:
            self.eval(var_name)


if __name__ == "__main__":
    app = widgets.app()
    app.set_style("fusion")
    dlg = IPythonDockWidget(app)
    dlg.show()
    app.main_loop()
