from __future__ import annotations

import pathlib
import webbrowser
import os.path as osp
import os
import logging
import time
import multiprocessing

import nbconvert
import nbformat
from notebook import notebookapp
from notebook.utils import url_path_join, url_escape
from traitlets.config import Config
import prettyqt.custom_widgets.dataset as fo
from prettyqt import widgets

from processanalyzer.constants import iconnames
from processanalyzer.core import application
from processanalyzer.plugintypes import exportplugin

logger = logging.getLogger(__name__)

OUTPUT_OPTS = [
    ("notebook", "Notebook file"),
    ("html", "As HTML"),
    ("open", "Open with iPython"),
]


class Settings(fo.DataSet):
    append_ds_head = fo.Bool("Call head() at end of each cell", value=True)
    how = fo.Enum("Output", choices=OUTPUT_OPTS)


def find_best_server(filename):
    """Find the best server to open a notebook with."""
    servers = [
        si
        for si in notebookapp.list_running_servers()
        if filename.startswith(si["notebook_dir"])
    ]
    try:
        return max(servers, key=lambda si: len(si["notebook_dir"]))
    except ValueError:
        return None


def run_server(filename, nbdir):
    cfg = Config()
    cfg.NotebookApp.file_to_run = os.path.abspath(filename)
    cfg.NotebookApp.notebook_dir = nbdir
    # cfg.NotebookApp.browser = "BuiltInBrowser"
    cfg.NotebookApp.open_browser = False
    # cfg.NotebookApp.token = ""
    logger.info("starting server for %s", nbdir)
    notebookapp.launch_new_instance(config=cfg, argv=[])


def shutdown_server(server_info):
    logger.info("shutting down server %s", server_info)
    notebookapp.shutdown_server(server_info, log=logger)


class NBServerError(Exception):
    """Exception for notebook server errors."""


def get_server_info(filename):
    """
    Open a notebook using the best available server.
    Returns information about the selected server.
    """
    filename = osp.abspath(filename)
    server_info = find_best_server(filename)

    if server_info is not None:
        logger.info("Using existing server at %s", server_info["notebook_dir"])
        return server_info
    else:
        home_dir = str(pathlib.Path.home())
        nbdir = home_dir if filename.startswith(home_dir) else osp.dirname(filename)
        logger.info("Starting new server")
        p = multiprocessing.Process(target=run_server, args=(filename, nbdir))
        p.daemon = True
        p.start()

        # Wait ~25 secs for the server to be up
        for _x in range(100):
            server_info = find_best_server(filename)
            if server_info is not None:
                break
            else:
                time.sleep(0.25)

        if server_info is None:
            raise NBServerError()

        # Kill the server at exit
        widgets.Application.call_on_exit(lambda: shutdown_server(server_info))

        return server_info


class NotebookExporter(exportplugin.ExportPlugin):
    extension = ".ipynb"
    menu_label = "Notebook file"
    plugin_id = "export.notebook"
    icon = iconnames.PYTHON

    def export(self, ds):
        self.settings = Settings()
        nb = nbformat.v4.new_notebook()
        import_str = "%matplotlib notebook\n" + ds.history.import_block(recursive=True)
        nb["cells"] = [
            nbformat.v4.new_markdown_cell("## Imports"),
            nbformat.v4.new_code_cell(import_str),
        ]
        if ds.comment:
            nb["cells"].append(nbformat.v4.new_markdown_cell(ds.comment))
        for history in ds.history.deepcopy().iter_tree(recursive=True):
            if self.settings.append_ds_head:
                history.cmds.append("\n|ds|.head()")
            code = history.prepared_code_block(comments=False).strip("\n")
            text = f"## {history.description}"
            # kwargs_text = "  |  ".join(history.kwargs_to_list()).replace("=", ": ")
            # if kwargs_text:
            #     text += f"\n\n{kwargs_text}"
            nb["cells"].append(nbformat.v4.new_markdown_cell(text))
            nb["cells"].append(nbformat.v4.new_code_cell(code))
        match self.settings.how:
            case "html":
                path = self.get_path()
                if not path:
                    return None
                html_exporter = nbconvert.HTMLExporter()
                (body, resources) = html_exporter.from_notebook_node(nb)
                self.run(self.write_file, path, body)
            case "notebook":
                path = self.get_path()
                if not path:
                    return None
                self.write_notebook(nb, path)
            case "open":
                path = application.CACHE_DIR / "notebook.ipynb"
                self.write_notebook(nb, path)
                # ds.log(f"Test",
                #        imports=["nbformat"],
                #        operation="export",
                #        description="Export as IPython notebook")

    def write_notebook(self, nb, path):
        nbformat.write(nb, str(path))
        server_info = get_server_info(str(path))
        path = os.path.relpath(str(path), start=server_info["notebook_dir"])
        if os.name == "nt":
            path = path.replace("\\", "/")
        # Server url to send requests to
        server_url = server_info["url"]
        # Server token
        token = server_info["token"]
        url = url_path_join(server_url, "notebooks", url_escape(path))
        file_url = url + f"?token={token}"
        logger.info(file_url)
        webbrowser.open(file_url)

    def write_file(self, path, text):
        with open(str(path), "w") as f:
            f.write(text)
        webbrowser.open(path)
