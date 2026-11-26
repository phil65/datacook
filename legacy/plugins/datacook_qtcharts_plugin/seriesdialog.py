from __future__ import annotations

import prettyqt.custom_widgets.dataset as fo
from prettyqt import core, gui
from processanalyzer.constants import iconnames


class SeriesDialog(core.Object):
    """
    TODO
    """

    accepted = core.Signal(object, str)

    def __init__(self, series, *args, **kwargs):
        super().__init__(*args, **kwargs)

        width = series.pen().widthF()

        class Dialog(fo.DataSet):
            name = fo.String("Name", series.name())
            proc_name = fo.String("Process name", series.process_name)
            color = fo.Color("Color", series.color())
            size = fo.Float("Size", value=width, min_val=0.1, max_val=20, slider=True)

        self.dlg = Dialog(title="Series options", icon=iconnames.PLOT)
        self.series = series
        self.initial_name = series.name()

    def open_dialog(self):
        if not self.dlg.edit():
            return None
        dct = self.dlg.to_dict()
        pen = self.series.pen()
        pen.setColor(gui.Color(dct["color"]))
        pen.setWidthF(dct["size"])
        # style = list(STYLES.keys())[self.cb_style.currentIndex()]
        # pen.setStyle(style)
        self.series.setPen(pen)
        self.series.process_name = dct["proc_name"]
        self.series.setName(dct["name"])
        self.accepted.emit(self.series, self.initial_name)


if __name__ == "__main__":
    from prettyqt import widgets, charts

    app = widgets.app()
    series = charts.LineSeries()
    dlg = SeriesDialog(series)
    dlg.open_dialog()
