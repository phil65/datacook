from __future__ import annotations

import logging

from prettyqt import core, widgets, constants

from processanalyzer.core import threads
from processanalyzer.gui import baseitemview

from .seriesdialog import SeriesDialog
from .seriesmodel import SeriesModel

logger = logging.getLogger(__name__)


class SeriesWidget(baseitemview.BaseItemViewMixin, widgets.TableView):
    def __init__(self, *args, **kwargs):
        """
        Custom TreeView for managing the indexes
        """
        super().__init__(*args, **kwargs)
        self.set_selection_mode("extended")
        self.setup_list_style()

    def keyPressEvent(self, event):
        """
        keypress event override
        allow deleting items with del
        """
        key = event.key()
        if key == constants.KEY_DELETE:
            self.remove_selected_series()
        else:
            return super().keyPressEvent(event)
        event.accept()

    def update_model(self):
        self.model().layoutAboutToBeChanged.emit()
        self.model().layoutChanged.emit()

    def contextMenuEvent(self, event):
        """
        context menu override
        """
        position = event.pos()
        indexes = list(self.selected_indexes())
        if not indexes:
            return None
        menu = widgets.Menu()
        any_visible = any(idx.data(constants.CHECKSTATE_ROLE) for idx in indexes)
        any_invisible = any(
            idx.data(constants.CHECKSTATE_ROLE) is False for idx in indexes
        )
        action_remove_series = menu.addAction("Remove series")
        action_show_series = menu.addAction("Show series") if any_invisible else None
        action_hide_series = menu.addAction("Hide series") if any_visible else None
        action_properties = menu.addAction("Properties") if len(indexes) == 1 else None

        if selected := menu.exec_(self.mapToGlobal(position)) is not None:
            if selected == action_remove_series:
                self.remove_selected_series()
            elif selected == action_hide_series:
                labels = list(self.selected_names())
                self.model().set_vis_for_series_with_names(labels, False)
            elif selected == action_show_series:
                labels = list(self.selected_names())
                self.model().set_vis_for_series_with_names(labels, True)
            elif selected == action_properties:
                series = next(self.selected_data())
                dlg = SeriesDialog(parent=self, series=series)
                dlg.accepted.connect(self.model().modify_all_with_name)
                dlg.open_dialog()

    def _load(self, series):
        model = SeriesModel(series)
        self.set_model(model)

    def remove_selected_series(self):
        labels = list(self.selected_names())
        self.model().remove_series_with_names(labels)
        self.model().chart().zoom(1.001)
        self.model().chart().zoom(1 / 1.001)

    @core.Slot()
    def select_series_by_sender(self):
        clicked = self.sender()
        worker = threads.Worker(self.select_series, clicked)
        threads.pool.start(worker)

    def select_series(self, clicked):
        clicked_name = clicked.name()
        logger.info(f"clicked {clicked.process_name}")
        for i, s in enumerate(self.model().chart().series()):
            if clicked_name == s.name():
                idx = self.model().createIndex(i, 0)
                self.setCurrentIndex(idx)
                return None
