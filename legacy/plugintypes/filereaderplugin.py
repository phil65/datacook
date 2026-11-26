from __future__ import annotations

import pathlib
import logging
import time

from processanalyzer.constants import iconnames
from processanalyzer.plugintypes import baseplugin

logger = logging.getLogger(__name__)


class FileReaderPlugin(baseplugin.BasePlugin):
    plugin_category = "Reader"
    extensions: dict[str, list[str]]
    icon = iconnames.FILE

    def read_file(self, path):
        raise NotImplementedError

    def supported_extensions(self) -> list[str]:
        """returns list of supported file extensions

        List is of form [".ext1", ".ext2", ...]

        Returns:
            List[str]: List of supported extensions
        """
        return [item for sublist in self.extensions.values() for item in sublist]

    def is_valid_reader_for(self, path: pathlib.Path) -> bool:
        return path.is_file() and path.suffix.lower() in self.supported_extensions()

    def read_files(self, paths: list[pathlib.Path]):
        """
        import data for given paths, emit signal for each loaded dataset.
        """
        for path in paths:
            now = time.time()
            logger.info("importing file %s...", path.name)
            yield from self.read_file(path)
            logger.info(f"Finished. Import took {(time.time() - now):.3f} seconds")
