from __future__ import annotations

from prettyqt import constants, core, itemmodels


class SeriesModel(itemmodels.ModelMixin, core.AbstractTableModel):
    """
    Class to populate a table view with a pandas dataframe
    """

    def __init__(self, chart=None, parent=None):
        super().__init__(parent=parent)
        self.chart = chart
        self.len = None
        self.set_length()

    def set_length(self):
        self.len = len({s.name() for s in self.chart().series()})

    def rowCount(self, parent=None):
        return self.len

    def data(self, index, role=constants.DISPLAY_ROLE):
        if not index.isValid():
            return None
        match role:
            case constants.DISPLAY_ROLE | constants.EDIT_ROLE | constants.NAME_ROLE:
                return self.chart().series()[index.row()].name()
            case constants.USER_ROLE:
                return self.chart().series()[index.row()]
            case constants.DECORATION_ROLE:
                return self.chart().series()[index.row()].color()
            case constants.CHECKSTATE_ROLE:
                return self.chart().series()[index.row()].isVisible()
        return None

    def setData(self, index, value, role):
        if not index.isValid():
            return False
        match role:
            case constants.EDIT_ROLE:
                series = index.data(constants.USER_ROLE)
                old_name = series.name()
                series.setName(value)
                self.modify_all_with_name(series, old_name)
                self.dataChanged.emit(index, index)
                return True
            case constants.CHECKSTATE_ROLE:
                s = index.data(constants.USER_ROLE)
                self.set_vis_for_series_with_names([s.name()], not s.isVisible())
                self.dataChanged.emit(index, index)
                return True

    def flags(self, index):
        return (
            super().flags(index)
            | constants.NO_CHILDREN
            | constants.IS_EDITABLE
            | constants.IS_CHECKABLE
        )

    def remove_series(self, series):
        with self.remove_rows():
            self.chart().removeSeries(series)
            self.set_length()

    def remove_series_with_names(self, names):
        with self.remove_rows():
            for s in reversed(self.chart().series()):
                if s.name() in names:
                    self.chart().removeSeries(s)
            self.set_length()

    def set_vis_for_series_with_names(self, names, visible):
        with self.change_layout():
            for s in reversed(self.chart().series()):
                if s.name() in names:
                    s.setVisible(visible)

    def modify_all_with_name(self, series, name):
        for i, s in enumerate(self.chart().series()):
            if name == s.name():
                pen = s.pen()
                pen.setColor(series.color())
                pen.setWidthF(series.pen().widthF())
                s.setPen(pen)
                s.setName(series.name())
        self.set_length()
