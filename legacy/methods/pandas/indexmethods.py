from __future__ import annotations

from collections.abc import Hashable
import logging

import pandas as pd
import pandastools  # noqa: F401
from pydantic import Field

from datacook.constants import iconnames
from datacook.core.application import _
from datacook.methods import base, methods


logger = logging.getLogger(__name__)

SIDE_OPTS = [(None, _("Default")), ("left", _("Left")), ("right", _("Right"))]


class AsTypeMethod(methods.IndexMethod):
    """Action to show groupedmodel for dataset."""

    icon = iconnames.DATASET
    description = _("Convert data type.")
    short_desc = _("Convert data type")
    obj = pd.Index.astype

    class Params(base.BaseModel):
        dtype: str = Field(title=_("New data type"))


class RenameMethod(methods.IndexMethod):
    icon = iconnames.RENAME
    description = _("Alter index or MultiIndex name.")
    short_desc = _("Rename")
    obj = pd.Index.rename

    class Params(base.BaseModel):
        name: Hashable = Field(title=_("Names"))


class SetNamesMethod(methods.IndexMethod):
    icon = iconnames.RENAME
    description = _("Set index or MultiIndex name.")
    short_desc = _("Rename")
    obj = pd.Index.set_names

    class Params(base.BaseModel):
        names: Hashable | list[Hashable] = Field(title=_("Names"))
        level: Hashable | list[Hashable] = Field(title=_("Level"))


if __name__ == "__main__":
    from prettyqt import widgets

    app = widgets.app()
