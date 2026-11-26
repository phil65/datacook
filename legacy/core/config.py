from __future__ import annotations

import atexit
import logging
import os
import shutil

from dynaconf import Dynaconf, loaders
from dynaconf.utils.boxing import DynaBox
from packaging import version
import pandas as pd

import datacook
from datacook.core import application


pd.options.mode.copy_on_write = True

logger = logging.getLogger(__file__)
os.environ["APP_DATA"] = str(application.DATA_DIR)

DEFAULT_SETTINGS_FILE = str(application.DEFAULT_SETTINGS_PATH)
USER_SETTINGS_FILE = str(application.USER_SETTINGS_PATH)


class Settings(Dynaconf):
    def save_settings_file(self):
        # generates a dict with all the keys for `development` env
        data = self.as_dict()
        # writes to a file, the format is inferred by extension
        # can be .yaml, .toml, .ini, .json, .py
        logger.debug("saving settings to %s", USER_SETTINGS_FILE)
        loaders.write(USER_SETTINGS_FILE, DynaBox(data).to_dict())

    def reset(self):
        self.load_file(DEFAULT_SETTINGS_FILE)


settings = Settings(settings_files=[DEFAULT_SETTINGS_FILE, USER_SETTINGS_FILE])
atexit.register(settings.save_settings_file)


def migrate():
    current_version_str = datacook.__version__
    prev_version = version.parse(settings.current_version)
    if prev_version <= version.parse("2.8.0"):
        logger.info("Migrating to %s", current_version_str)
        shutil.rmtree(application.CACHE_DIR)
        application.CACHE_DIR.mkdir(parents=True)
    if prev_version < version.parse("2.12.0"):
        settings.app_theme = "default"
    settings.current_version = current_version_str


def reset():
    for p in [application.CACHE_DIR, application.DATA_DIR, application.LOG_DIR]:
        shutil.rmtree(p, ignore_errors=True)
        p.mkdir(parents=True)
    settings.reset()
