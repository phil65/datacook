from __future__ import annotations

import logging
from typing import Any

from prettyqt import itemmodels

from processanalyzer.core import application, history, serializemixin
from processanalyzer.util import helpers

logger = logging.getLogger(__name__)


class Project(serializemixin.SerializeMixin, itemmodels.NestedItem):
    def __init__(self, name="", description="", **kwargs):
        self.name = name
        self.description = description
        super().__init__(**kwargs)

    def as_json(self) -> dict[str, Any]:
        return dict(name=self.name, children=[c.as_json() for c in self.children])

    @classmethod
    def from_json(cls, dct: dict[str, Any]) -> Project:
        return cls(
            name=dct.get("name"),
            children=[history.History.from_json(c) for c in dct.get("children", [])],
        )

    def save(self, path=None):
        """
        dump all recipes on disk.
        """
        if not path:
            path = application.DS_HISTORY_BACKUP
        helpers.save_yaml(self.as_json(), path=path)


if __name__ == "__main__":
    pr = Project(name="Test")
    print(pr)
