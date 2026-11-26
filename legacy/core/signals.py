from __future__ import annotations


from prettyqt import core, widgets


class Signals(core.Object):
    # apparently with Python3.6 + PyQt5, NoneType is not allowed for fixed-type signals.
    # So we have to use "object" as signal type for now

    add_dataset_and_open = core.Signal(object)
    add_dataset_and_focus = core.Signal(object)
    add_dataset = core.Signal(object)
    add_datasets = core.Signal(object)
    add_estimator = core.Signal(object)
    popup_info = core.Signal(str)
    update_history = core.Signal(object)  # dataset or None
    update_esthistory = core.Signal(object)  # dataset or None
    add_table = core.Signal(object)
    add_widget = core.Signal(widgets.Widget, str)
    update_featuretree = core.Signal(object)  # dataset or None
    update_indextree = core.Signal(object)  # dataset or None
    update_table = core.Signal(object)  # dataset or None
    settings_updated = core.Signal()
    update_datasetmanager = core.Signal(object)
    update_categorytree = core.Signal(object, object)
    update_categorytree_ds = core.Signal(object)


signals = Signals()
