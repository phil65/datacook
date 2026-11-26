"""Op categories (menu / palette groups)."""

from dataclasses import dataclass

from datacook.i18n import LazyText, _


@dataclass(frozen=True, slots=True)
class Category:
    id: str
    title: LazyText
    icon: str


SOURCE = Category("source", _("Import"), "mdi.database-import")
GENERAL = Category("general", _("General"), "mdi.database")
COLUMNS = Category("columns", _("Columns"), "mdi.table-column")
ROWS = Category("rows", _("Rows"), "mdi.table-row")
FILTER = Category("filter", _("Filter operations"), "mdi.filter-outline")
NAN = Category("nan", _("NaN operations"), "mdi.help-circle-outline")
CATEGORICAL = Category("categorical", _("Categories"), "mdi.shape-outline")
CONVERSION = Category("conversion", _("Conversion"), "mdi.swap-horizontal")
RESHAPE = Category("reshape", _("Reshape"), "mdi.table-pivot")
COMBINE = Category("combine", _("Combine"), "mdi.set-merge")
STATS = Category("stats", _("Statistics"), "mdi.chart-box-outline")
TEXT = Category("text", _("Text"), "mdi.format-text")
DATETIME = Category("datetime", _("Date and time"), "mdi.calendar-clock")
TIMESERIES = Category("timeseries", _("Time series"), "mdi.chart-timeline-variant")
CODE = Category("code", _("Code"), "mdi.language-python")
