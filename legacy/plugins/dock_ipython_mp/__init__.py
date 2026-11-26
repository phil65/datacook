from __future__ import annotations

import errno
import logging
import multiprocessing
import os
import sys
import time

# import asyncio

import IPython
from prettyqt import core, widgets
from qtconsole.client import QtKernelClient
from qtconsole.rich_jupyter_widget import RichJupyterWidget

from processanalyzer.constants import iconnames
from processanalyzer.core import application, signals, threads
from processanalyzer.plugintypes import contextmenuplugin, sidebarplugin

logger = logging.getLogger(__name__)


# ipython = IPython.get_ipython()
# ipython.magic(f"gui qt{qt.QT_VERSION}")

# asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def run_server(connection_file):
    IPython.embed_kernel(
        local_ns=sys._getframe(1).f_locals,
        connection_file=os.fspath(connection_file),
        gui="qt6",
    )


class Signals(core.Object):
    """
    Defines the signals available for this widget

    """

    execute_code = core.Signal(str)


class IpythonMPDock(sidebarplugin.SidebarPlugin):
    plugin_id = "dock.ipython_mp"
    icon = iconnames.PYTHON
    signals = Signals()
    DEFAULT_POSITION = "right"
    context_label = "IPython (MP)"

    def __init__(self, *args, **kwargs):
        super().__init__(parent=kwargs.get("parent"))
        # self.settings = Settings(title=self.context_label,
        #                          icon=self.icon)
        layout = widgets.BoxLayout("horizontal", self, margin=0)
        self.console_widget = ConsoleWidget()
        self.console_widget.evaluated.connect(signals.signals.add_dataset_and_focus)
        # logger.info(dir(self.console_widget.kernel_manager))
        # logger.info(dir(self.console_widget.kernel_manager.kernel))
        self.signals.execute_code.connect(self.execute)
        # self.console_widget.kernel_manager.kernel.push({"icon": self.icon})
        # self.console_widget.execute("import pydataset", hidden=False, interactive=True)
        layout += self.console_widget

    def execute(self, code):
        win = widgets.Application.get_mainwindow()
        win.set_tab(self)
        self.console_widget.execute(code, hidden=False, interactive=True)

    def unregister(self):
        logger.info("Shutting down kernel...")
        self.jupyter_widget.kernel_client.stop_channels()
        self.jupyter_widget.kernel_manager.shutdown_kernel()
        # self.signals.pull_var.connect(self.console_widget.eval)
        # # push some variables to the console
        # objects = dict(clc=self.console_widget.clear, window=window)
        # self.signals.push_vars.emit(objects)


class IPythonExecuteAction(contextmenuplugin.PluginAction):
    icon = iconnames.PYTHON
    description = "Execute code in Python MP console"
    short_desc = "Execute code in Python MP console"

    def is_visible(self):
        data = list(self.selected_data())
        return len(data) == 1 and hasattr(data[0], "history")

    def process(self, **kwargs):
        data = list(self.selected_data())
        code = data[0].history.as_code()
        IpythonMPDock.signals.execute_code.emit(str(code))


class ConsoleWidget(widgets.WidgetMixin, RichJupyterWidget):
    """
    Convenience class for a live IPython console widget.
    We can replace the standard banner using the customBanner argument
    """

    evaluated = core.Signal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        widgets.Application.call_on_exit(self.stop)
        # self.exit_requested.connect(self.stop)
        widgets.Application.styleHints().colorSchemeChanged.connect(
            self.adjust_style_to_palette
        )
        self.adjust_style_to_palette()
        self.connection_file = application.CACHE_DIR / f"connection-{os.getpid()}.json"
        self.p = multiprocessing.Process(target=run_server, args=(self.connection_file,))
        self.p.daemon = True
        self.p.start()
        logger.info("waiting for connection file creation....")
        worker = threads.Worker(self.wait_for_connection_file)
        worker.signals.finished.connect(self.initialize)
        threads.pool.start(worker, message="Initializing Ipython console...")

    def adjust_style_to_palette(self):
        pal = widgets.Application.get_palette()
        style = "linux" if pal.is_dark() else "lightbg"
        self.set_default_style(style)

    def wait_for_connection_file(self):
        for i in range(1000):
            try:
                st = os.stat(self.connection_file)
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    raise
            else:
                if st.st_size > 0:
                    # time.sleep(0.1)
                    logger.info("Connection file found.")
                    break
            time.sleep(0.1)

    def stop(self):
        logger.info("shutting down IPython MP kernel")
        self.kernel_client.stop_channels()
        self.kernel_client.shutdown()
        self.p.terminate()
        self.connection_file.unlink(missing_ok=True)
        logger.info("shutdown successful.")

    def initialize(self):
        kernel_client = QtKernelClient(connection_file=os.fspath(self.connection_file))
        kernel_client.load_connection_file()  # can throw FileNotFoundError
        kernel_client.start_channels()
        self.kernel_client = kernel_client

    def push_vars(self, var_dict):
        """
        Given a dictionary containing name / value pairs, push those variables
        to the IPython console widget
        """
        self.kernel_client[0].push(var_dict)
        for key in var_dict.keys():
            self._append_plain_text(f'\nadded "{key}" object to namespace\n', True)

    def eval(self, obj_name: str):
        """Pull object with name *obj_name from namespace."""
        try:
            data = self.kernel_manager.kernel.shell.ev(obj_name)
        except NameError as e:
            logging.exception(e)
            return None
        self.print_text(f'\nread "{obj_name}" object to namespace\n', True)
        self.evaluated.emit(data)

    def clear(self):
        """
        Clears the terminal
        """
        self._control.clear()

        # self.kernel_manager

    def print_text(self, text: str, before_prompt: bool = False):
        """
        Prints some plain text to the console
        """
        self._append_plain_text(text)

    def execute_command(self, command: str):
        """
        Execute a command in the frame of the console widget
        """
        self._execute(command, False)


if __name__ == "__main__":
    app = widgets.app()
    app.set_style("fusion")
    console_widget = ConsoleWidget()
    print(dir(console_widget))
    console_widget.show()
    app.main_loop()
