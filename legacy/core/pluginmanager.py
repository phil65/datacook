from __future__ import annotations

import os
import types
import dataclasses
import importlib
import logging
import pathlib
import pkgutil

import yaml

from processanalyzer.core import application, config

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=False, eq=False)
class PluginInfo:
    module_name: str
    name: str
    author: str
    version: str
    website: str
    description: str
    requirements: list | None = None
    platforms: list | None = None
    package_path: str | None = None
    module: types.ModuleType | None = None
    category: str | None = None

    def import_module(self):
        name = f".{self.module_name}" if self.package_path else self.module_name
        if self.is_active():
            try:
                self.module = importlib.import_module(
                    name=name, package=self.package_path
                )
                logger.info("imported %s", self.name)
            except Exception as e:
                logger.exception(e)

    def has_settings(self) -> bool:
        return hasattr(self.module, "Settings")

    def edit_settings(self):
        # self.load_settings()
        if not self.has_settings():
            raise ValueError("Module does not have any settings defined.")
        dlg = self.module.Settings()
        settings = config.settings.get(self.module_name, {})
        logger.info("loaded settings for %s", self.module_name)
        if not dlg.edit(preset=settings):
            return None
        dct = dlg.to_dict()
        config.settings[self.module_name] = dct
        logger.info(f"written settings for {self.module_name}: {dct}")

    def is_active(self) -> bool:
        return config.settings.setdefault("active_plugins", {}).setdefault(
            self.module_name, True
        )

    def toggle_active(self):
        val = not self.is_active()
        config.settings["active_plugins"][self.module_name] = val


class PluginManager:
    def __init__(self):
        """
        initialize our app manager
        """
        self.plugins = {}
        self.package_path = f"{application.MODULE_NAME}.plugins"
        self.plugins_dir = str(application.PLUGINS_DIR)

    def collect_plugin_candidates(self):
        logging.info("scanning for packages with datacook_ prefix...")
        for finder, name, __ in pkgutil.iter_modules():
            if name.startswith("datacook_"):
                self.load_plugin_info(finder, name)
        logger.info("scanning %s for plugins...", self.plugins_dir)
        for finder, name, __ in pkgutil.iter_modules([self.plugins_dir]):
            self.load_plugin_info(finder.path, name, package_path=self.package_path)

    def load_plugin_info(
        self,
        path: os.PathLike,
        name: str,
        package_path: str | None = None,
    ):
        if package_path is not None:
            manifest_path = pathlib.Path(path) / name / "manifest.yaml"
        else:
            manifest_path = pathlib.Path(path) / "manifest.yaml"
        if not manifest_path.exists():
            logger.error("No manifest file found for %s", name)
            return None
        logger.info("loading manifest info for %s", name)
        file_content = manifest_path.read_text()
        info = yaml.full_load(file_content)
        self.plugins[name] = PluginInfo(name, package_path=package_path, **info)
        logger.info("loaded manifest info for %s", name)

    def import_plugin_modules(self):
        for info in self.plugins.values():
            info.import_module()


instance = PluginManager()

if __name__ == "__main__":
    instance.collect_plugin_candidates()
    instance.import_plugin_modules()
