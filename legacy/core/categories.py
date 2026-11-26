from __future__ import annotations

from dataclasses import dataclass

from datacook.constants import iconnames
from datacook.core.application import _


@dataclass(frozen=True)
class Category:
    slug: str
    name: str
    icon: str


GeneralCategory = Category(slug="general", name=_("General"), icon=iconnames.DATASET)
PlotCategory = Category(slug="plot", name=_("Plotting"), icon=iconnames.PLOT)
StatsCategory = Category(slug="stats", name=_("Statistics"), icon=iconnames.STATS)
NanCategory = Category(slug="nan", name=_("NaN operations"), icon=iconnames.NAN)
DateTimeCategory = Category(slug="datetime", name=_("Date / Time operations"), icon=iconnames.TIME)
StringCategory = Category(slug="string", name=_("String operations"), icon=iconnames.STRING)
FilterCategory = Category(slug="filter", name=_("Filter operations"), icon=iconnames.FILTER)
SklearnCategory = Category(slug="sklearn", name=_("Scikit-Learn operations"), icon=iconnames.ML)
ConversionCategory = Category(slug="conversion", name=_("Conversion"), icon=iconnames.TRANSFORMER)
ReshapeCategory = Category(slug="reshape", name=_("Reshape"), icon=iconnames.RESHAPE)
PluginCategory = Category(slug="plugin", name=_("Plugin"), icon=iconnames.PLUGIN)
