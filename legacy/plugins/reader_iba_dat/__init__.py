from __future__ import annotations

import logging
import pathlib

import ibadatfile

import prettyqt.custom_widgets.dataset as fo
from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin

logger = logging.getLogger(__name__)


class Settings(fo.DataSet):
    raw_mode = fo.Bool("Raw mode (return unscaled raw values)")
    preload = fo.Bool("Preload whole file into memory", value=True)


class IbaDatFileReader(filereaderplugin.FileReaderPlugin):
    extensions = {"Iba dat files": [".dat"]}
    menu_label = "Iba .dat file"
    plugin_id = "reader.iba_dat"
    context_label = "Iba .dat reader"

    def is_valid_reader_for(self, path: pathlib.Path):
        if not super().is_valid_reader_for(path):
            return False
        num_bytes = min(1024, path.stat().st_size)
        with path.open(mode="rb") as file:
            raw = file.read(num_bytes)
        return raw.startswith(b"PDA")

    def read_file(self, path):
        """
        Read iba dat file
        """
        self.settings = Settings()
        keyword_args = self.settings.to_dict()
        with ibadatfile.IbaDatFile(path, **keyword_args) as ibafile:
            if ibafile.frames() >= 100_000_000:
                logger.info("too many frames or data corrupted. aborting...")
                yield dataset.DataSet(name="Empty")
                return None
            ds = dataset.DataSet(data=ibafile.data(), name=path.name)
        ds.log(
            "reader = ibadatfile.IbaDatFile(|KWARGS|)",
            "reader.open(|ORIGIN|)",
            "|ds| = reader.data()",
            "reader.close()",
            imports=["ibadatfile"],
            operation="import",
            origin=path,
            description="Import from Iba file",
            kwargs=keyword_args,
        )
        yield ds
