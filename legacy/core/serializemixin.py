from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import yaml

from datacook.util import helpers


if TYPE_CHECKING:
    from collections.abc import Callable
    import pathlib


logger = logging.getLogger(__name__)


class SerializeMixin:
    from_json: Callable
    as_json: Callable

    def to_yaml(self) -> str:
        """Serialize object to a yaml representation."""
        return yaml.dump(self.as_json(), sort_keys=False, allow_unicode=True)

    @classmethod
    def build_from_string(cls, text: str):
        """Instanciate a history object based on a history yaml text representaion."""
        return cls.from_json(yaml.full_load(text))

    @classmethod
    def load_from_file(cls, path: pathlib.Path) -> list | dict | None:
        """Read the history objects stored (as a YAML list) in the given file."""
        json_obj = helpers.load_yaml(path)
        if json_obj is None:
            return None
        return cls.from_json(json_obj)

    def save_to_file(self, path: pathlib.Path):
        """Dump json as yaml to given path."""
        helpers.save_yaml(self.as_json(), path=path)
