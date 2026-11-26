from __future__ import annotations

import codecs
import csv
import logging
import pathlib

import chardet
import pandas as pd
from pydantic import Field

# from pandas._typing import FilePathOrBuffer

from prettyqt import core, custom_widgets, widgets

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset, signals, threads
from processanalyzer.core.application import _
from processanalyzer.gui import tablecontainer
from processanalyzer.methods import base, methods
from processanalyzer.plugintypes import filereaderplugin

REGEX_ONE_CHAR = r"\S{1}"

logger = logging.getLogger(__name__)

DEFAULT_NA = """‘’, ‘#N/A’, ‘#N/A N/A’, ‘#NA’, ‘-1.#IND’,
‘-1.#QNAN’, ‘-NaN’, ‘-nan’, ‘1.#IND’,
‘1.#QNAN’, ‘<NA>’, ‘N/A’, ‘NA’, ‘NULL’,
‘NaN’, ‘n/a’, ‘nan’, ‘null’"""

ENCODINGS = ["utf-8", "iso-8859-1", "ascii", "utf-16", "utf-32", "utf-8-sig"]


class ReadCsvMethod(methods.BaseMethod):
    short_desc = "Read .csv file"
    obj = pd.read_csv
    icon = iconnames.TABLE
    description = "Import CSV file"
    imports = ["pandas"]

    class Params(base.BaseModel):
        # filepath_or_buffer: pathlib.Path | str | None = base.File(
        #     label=_("File path")
        # )
        sep: str = Field(",", title=_("Separator"))
        header: int | list[int] | None | str = Field("infer", title=_("Header"))
        decimal: str = Field(".", title=_("Decimal sign"))
        encoding: str | None = Field(None, title=_("Encoding"))
        nrows: int | None = Field(None, title=_("Limit rows"))
        na_values: list[str] | None = Field(None, title=_("Value for missing data"))
        keep_default_na: bool = Field(True, title=_("Detect default NA values"))

    def apply_method(self, path):
        keyword_args = self.params.to_dict()
        df = pd.read_csv(str(path), **keyword_args)
        ds = dataset.DataSet(data=df, name=path.name)
        ds.log(
            "|ds| = pandas.read_csv(|ORIGIN||OPTKWARGS|)",
            imports=self.imports,
            operation="import",
            origin=path,
            description=f"Import from {path.suffix}",
            kwargs=keyword_args,
        )
        return ds


class CsvReader(filereaderplugin.FileReaderPlugin):
    menu_label = "CSV File"
    extensions = {"Csv files": [".csv", ".tsv"], "Text files": [".txt"]}
    plugin_id = "reader.csv"
    icon = iconnames.TABLE

    def read(self, paths=None):
        dlg = CSVImportDialog(paths=paths, extensions=self.extensions)
        dlg.show_blocking()


def guess_encoding(path: pathlib.Path) -> str | None:
    if not path.exists():
        return None
    # encoding = self._detector.detect(path)
    num_bytes = min(1024, path.stat().st_size)
    with path.open(mode="rb") as file:
        raw = file.read(num_bytes)
    if raw.startswith(codecs.BOM_UTF8):
        logger.info("BOM detected")
        return "utf-8-sig"
    else:
        encoding = chardet.detect(raw)["encoding"].lower()
        logger.info(f"Auto-detected {encoding}")
        return encoding


def sniff_delimiter(filename: pathlib.Path) -> str:
    with filename.open() as csvfile:
        header = csvfile.__next__()
    sniffer = csv.Sniffer()
    dialect = sniffer.sniff(header)
    logger.info(f"detected {dialect.delimiter!r} as delimiter")
    return dialect.delimiter


def sniff_has_header(filename: pathlib.Path) -> bool:
    with filename.open() as csvfile:
        return csv.Sniffer().has_header(csvfile.read(16384))


class CSVImportDialog(widgets.Dialog):
    update_status = core.Signal(str)

    def __init__(self, extensions, paths=None, parent=None):
        super().__init__(title="Import CSV", icon=iconnames.TABLE, parent=parent)
        self.encoding = "utf-8"
        self.paths = paths
        self.extensions = extensions
        self._filename = self.paths[0] if self.paths else None
        self._delimiter = None
        self._decimal = None
        self._na_value = ""
        self._header: int | None = 0
        # self._detector = Detector()

        self.set_layout("grid")
        btn_choose_file = custom_widgets.FileChooserButton(extensions, mode="open")
        btn_choose_file.value_changed.connect(self.update_file)

        self.box[0, 0] = widgets.Label("Choose file")
        self.box[0, 1:3] = btn_choose_file

        self.cb_encoding = widgets.ComboBox()
        self.cb_encoding.add_items(ENCODINGS)
        self.cb_encoding.activated.connect(self.update_encoding)
        self.chk_default_na = widgets.CheckBox(checked=True)
        self.chk_default_na.value_changed.connect(self.preview)
        self.lineedit_additional_na = widgets.LineEdit()
        self.lineedit_additional_na.value_changed.connect(self.update_na_value)

        self.box[1, 0] = widgets.Label("File encoding")
        self.box[1, 1] = self.cb_encoding
        self.box[2, 0] = custom_widgets.IconLabel(
            "Detect default NA values", tooltip=DEFAULT_NA
        )
        self.box[2, 1] = self.chk_default_na
        self.box[2, 2] = widgets.Label("Custom NA value")
        self.box[2, 3] = self.lineedit_additional_na

        self.chk_header = widgets.CheckBox(checked=True)
        self.chk_header.value_changed.connect(self.update_header)

        self.box[1, 2] = widgets.Label("Header available?")
        self.box[1, 3] = self.chk_header
        # self.box[2, 2] = widgets.Label("Skip lines")
        # self.box[2, 3:4] = widgets.lineEdit("Skip lines")
        label_delimiter = widgets.Label("Column delimiter")
        self.widget_delimiter = custom_widgets.SelectionWidget()
        items = {";": "Semicolon", "\t": "Tab", ",": "Comma"}
        self.widget_delimiter.add_items(items)
        self.widget_delimiter.add_custom(label=_("Other"), regex=REGEX_ONE_CHAR)
        self._delimiter = self.widget_delimiter.current_choice()
        self.widget_delimiter.value_changed.connect(self.update_delimiter)

        self.box[3, 0] = label_delimiter
        self.box[3, 1:3] = self.widget_delimiter

        self.widget_decimal = custom_widgets.SelectionWidget()
        items = {".": "Point", ",": "Comma"}
        self.widget_decimal.add_items(items)
        self.widget_decimal.add_custom(label=_("Other"), regex=REGEX_ONE_CHAR)
        self._decimal = self.widget_decimal.current_choice()
        self.widget_decimal.value_changed.connect(self.update_decimal)

        self.box[4, 0] = widgets.Label("Decimal sign")
        self.box[4, 1:3] = self.widget_decimal

        self.table = tablecontainer.TableContainer()
        self.box[5:7, 0:3] = self.table

        button_box = widgets.DialogButtonBox()
        button_box.add_button("Load data", callback=self.accept)
        button_box.add_button("Cancel", role="reject", callback=self.reject)
        self.box[9, 2:3] = button_box
        self.status_bar = widgets.StatusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.box[8, 0:3] = self.status_bar

        self.update_status.connect(self.update_status_bar)
        if self._filename:
            btn_choose_file.set_path(self._filename)
            self.update_file(self._filename)

    @core.Slot(str)
    def update_status_bar(self, message):
        self.status_bar.show_message(message, 5000)

    @core.Slot(int)
    def update_header(self, state):
        self._header = 0 if state else None
        self.preview()

    @core.Slot(pathlib.Path)
    def update_file(self, filename):
        self._filename = filename
        detected = guess_encoding(filename)
        if detected:
            self.encoding = detected
            self.cb_encoding.setCurrentText(self.encoding)
        delimiter = sniff_delimiter(filename)
        self.widget_delimiter.select_radio_by_data(delimiter)
        has_header = sniff_has_header(filename)
        self.chk_header.set_value(has_header)
        self.preview()

    def update_encoding(self, index):
        self.encoding = self.cb_encoding.itemText(index)
        self.preview()

    def update_delimiter(self, delimiter):
        self._delimiter = delimiter
        self.preview()

    def update_decimal(self, decimal):
        self._decimal = decimal
        self.preview()

    def update_na_value(self, na_value):
        self._na_value = na_value
        self.preview()

    def preview(self):
        worker = threads.Worker(self.load_df, preview=True)
        worker.signals.result.connect(self.load)
        threads.pool.start(worker)

    def load(self, ds):
        self.table.set_ds(ds, read_only=True)
        self.table.show_icons()
        if ds is not None:
            self.update_status.emit("Preview generated.")

    def load_df(self, preview=False):
        if not self._filename or not self._filename.exists():
            self.update_status.emit(f"File {self._filename} could not be read.")
            return None
        keyword_args = dict(
            sep=self._delimiter,
            header=self._header,
            index_col=False,
            decimal=self._decimal,
            keep_default_na=self.chk_default_na.get_value(),
            na_values=[self._na_value] if self._na_value else [],
            encoding=self.encoding,
        )
        if preview:
            keyword_args["nrows"] = 100
        method = ReadCsvMethod(**keyword_args)
        try:
            ds = method.apply_method(self._filename)
            if preview:
                ds.set_history(None)
            return ds

        except (UnicodeDecodeError, UnboundLocalError) as e:
            self.update_status.emit(str(e))
            logger.exception(e)

    def accept(self):
        if self.table.has_ds():
            worker = threads.Worker(self.load_df, preview=False)
            worker.signals.result.connect(signals.signals.add_dataset_and_focus)
            threads.pool.start(
                worker, set_busy=True, message=f"Importing {self._filename}..."
            )
        super().accept()


if __name__ == "__main__":
    app = widgets.app()
    reader = CsvReader()
    reader.read()
    app.main_loop()
