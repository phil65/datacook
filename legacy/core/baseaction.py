from __future__ import annotations

import functools
import inspect
from typing import Any

from collections.abc import Generator

from prettyqt import constants, gui

from processanalyzer.core import categories
from processanalyzer.gui import menus
from processanalyzer.methods import methods


class BaseAction(gui.Action):
    shortcut: str | None = None
    icon: str | None = None
    description: str | None = None
    short_desc: str | None = None
    context_category: categories.Category = categories.GeneralCategory
    comment: str | None = None

    add_feat = False
    modelaction = "layoutchange"
    # subclasses: List[Any] = []

    # def __init_subclass__(cls, **kwargs):
    #     super().__init_subclass__(**kwargs)
    #     cls.subclasses.append(cls)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.set_text(self.short_desc)
        self.model = None
        self.indexes = []
        self.set_icon(self.icon)
        self.set_shortcut(self.shortcut)
        self.set_tooltip(self.description)

    def set_context(self, model=None, indexes: list | None = None):
        self.model = model
        self.indexes = indexes or []

    def selected_names(self) -> Generator[Any, None, None]:
        return (i.data(constants.NAME_ROLE) for i in self.indexes)

    def selected_data(self) -> Generator[Any, None, None]:
        return (i.data(constants.USER_ROLE) for i in self.indexes)

    def selected_rows(self) -> Generator[int, None, None]:
        return (i.row() for i in self.indexes)

    def is_visible(self) -> bool:
        return len(self.indexes) > 0

    def return_action(self, parent=None) -> BaseAction:
        return self

    def get_param_class(self):
        return None

    def setup_kwargs(self):
        Dialog = self.get_param_class()
        if Dialog is None:
            return True
        dlg = Dialog(
            title=self.short_desc,
            icon=self.icon,
            comment=self.comment or self.description,
        )
        if not dlg.edit():
            return None
        return dlg

    def setup_kwargs_and_process(self):
        dlg = self.setup_kwargs()
        if dlg is None:
            return None
        keyword_args = {} if dlg is True else dlg.to_dict()
        return self.process(**keyword_args)

    def process(self, **kwargs):
        pass


class MethodAction(BaseAction):
    method: methods.BaseMethod

    def __init__(self, parent=None):
        self.short_desc = self.method.short_desc
        self.icon = self.method.icon
        self.description = self.method.description
        self.comment = self.method.comment
        self.obj = self.method.obj
        super().__init__(parent=parent)


class CallableAction(BaseAction):
    # icon = iconnames.PYTHON
    description = ""
    short_desc = None

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.obj = None

    def setup(self, method, name):
        self.obj = method
        self.short_desc = name
        self.set_text(name)

    def process(self, **kwargs):
        return self.obj()


class ContainerAction(BaseAction):
    icon: str | None = None
    description: str | None = None
    short_desc: str | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.submenu_items = {}

    def _build_submenu(self, parent=None):
        submenu = menus.Menu(self.short_desc, parent=parent)
        for k, v in self.submenu_items.items():
            if isinstance(v, functools.partial) or inspect.ismethod(v):
                act = CallableAction(parent=self)
                act.setup(method=v, name=k)
            elif issubclass(v, BaseAction):
                act = v(parent=self)
            else:
                continue
            act.set_context(self.model, self.indexes)
            submenu.add(act)
        return submenu

    def return_action(self, parent=None):
        action = gui.Action(
            text=self.short_desc,
            parent=parent,
            icon=self.icon,
            shortcut=self.shortcut,
            tooltip=self.description,
        )
        submenu = self._build_submenu(parent=parent)
        action.set_menu(submenu)
        return action
