"""App paths (platformdirs). Translation helpers live in `datacook.i18n`."""

import logging
import pathlib

import platformdirs

import datacook
from datacook.i18n import LANG_DIR, N_, LazyText, _, set_language, translate


logger = logging.getLogger(__name__)

MODULE_NAME = datacook.__name__

dirs = platformdirs.AppDirs(datacook.__title__, appauthor=False, roaming=True, ensure_exists=True)

CACHE_DIR = pathlib.Path(dirs.user_cache_dir)
DATA_DIR = pathlib.Path(dirs.user_data_dir)
LOG_DIR = pathlib.Path(dirs.user_log_dir)
MODULE_PATH = pathlib.Path(__file__).parent.parent
RESOURCES_DIR = MODULE_PATH / "resources"
FONTS_DIR = RESOURCES_DIR / "fonts"

LOG_PATH = LOG_DIR / "log.txt"


__all__ = [
    "CACHE_DIR",
    "DATA_DIR",
    "FONTS_DIR",
    "LANG_DIR",
    "LOG_DIR",
    "LOG_PATH",
    "MODULE_PATH",
    "N_",
    "RESOURCES_DIR",
    "LazyText",
    "_",
    "set_language",
    "translate",
]
