"""Top-level package for DataCook QtCharts Plugin."""

from prettyqt import charts, core


class LineSeries(charts.LineSeries):

    """
    QLineSeries with some custom properties
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._process_name = ""

    @core.Property(object)
    def process_name(self):
        return self._process_name

    @process_name.setter  # type: ignore
    def process_name(self, value):
        self._process_name = value
