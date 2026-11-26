from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from datacook.core import (
    codeblock,
    config,
    history,
    itemclasses,
    serializemixin,
)
from datacook.util import helpers


if TYPE_CHECKING:
    from collections.abc import Callable


logger = logging.getLogger(__name__)


class HistoryItemMixin(serializemixin.SerializeMixin):
    instance: Any
    get_metadata: Callable
    item_name: str
    obj: type

    def __init__(
        self,
        name: str | None = None,
        history: history.History | None = None,
        comment: str = "",
        inherit_from: HistoryItemMixin | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.set_history(history)
        self.set_name(None)
        self.set_comment(comment)
        if isinstance(inherit_from, HistoryItemMixin):
            self.set_comment(inherit_from.comment)
            self.set_history(inherit_from.history)
            self.set_name(inherit_from.title)
        if name is not None:
            self.set_name(name)

    def copy(self):
        item_cls = type(self)
        return item_cls(
            data=self.instance,
            name=self.title,
            history=self.history.deepcopy() if self.history is not None else None,
            comment=self.comment,
        )

    def set_name(self, title):
        self.title = helpers.format_name(title)
        return self

    def set_comment(self, comment: str):
        self.comment = comment

    def set_history(self, hist: history.History | None):
        self.history = hist

    def as_json(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "comment": self.comment,
            "history": self.history.as_json() if self.history else None,
        }

    @classmethod
    def from_json(cls, dct: Any) -> Any:
        """Instanciate a dataset object based on a python dictionary."""
        hist = history.History.from_json(dct.get("history"))
        item = hist.evaluate()
        item.set_name(dct.get("title"))
        item.set_comment(dct.get("comment"))
        return item

    @classmethod
    def from_script(
        cls,
        code: codeblock.Code,
        description: str = "Recipe",
        fn_name: str | None = None,
        title: str = "From code",
    ):
        compiled = code.evaluate({"__builtins__": __builtins__}, return_val=cls.item_name)
        if not isinstance(compiled, cls.obj):
            raise TypeError(f"Function needs to return {cls.obj.__name__}")
        item_cls = itemclasses.get_class_for_instance(compiled)
        cmds = code.get_process_code()
        if fn_name is None:
            fn_name = f"build_{cls.item_name}"
        method_text, fn_name = cmds.wrap_in_method(method_name=fn_name, obj_name=cls.item_name)
        result = item_cls(data=compiled, name=title)
        result.log(
            str(method_text),
            description=description,
            imports=list(code.get_import_lines()),
            operation="import",
        )
        return result

    def apply_script(
        self,
        code: codeblock.Code | str,
        description: str = "Custom expression",
        fn_name: str | None = None,
        log: bool = True,
    ):
        """Apply a script to the dataset. script is wrapped as a function."""
        if fn_name is None:
            fn_name = f"modify_{self.item_name}"
        if isinstance(code, str):
            code = codeblock.Code(code)
        compiled = code.evaluate(
            {self.item_name: self.instance, "__builtins__": __builtins__},
            return_val=self.item_name,
        )
        if not isinstance(compiled, self.obj):
            raise TypeError(f"Function needs to return {self.obj.__name__}")
        item_cls = itemclasses.get_class_for_instance(compiled)
        result = item_cls(data=compiled, inherit_from=self)
        cmds = code.get_process_code()
        method_text, fn_name = cmds.wrap_in_method(
            method_name=fn_name, input_param=True, obj_name=self.item_name
        )
        if log:
            result.log(
                str(method_text),
                imports=list(code.get_import_lines()),
                description=f"Recipe: {description}",
            )
        return result

    def log(
        self,
        *args: str,
        imports: list[str] | None = None,
        operation: str = "modification",
        description: str = "",
        name=None,
        origin: str | None = None,
        children: list[history.History] | None = None,
        kwargs: dict[str, Any] | None = None,
    ):
        # alternative: use operation kwarg to infer children
        if children:  # merge
            children = [h.deepcopy() for h in children]
        elif not self.history:  # import
            children = []
        else:
            children = [self.history.deepcopy()]
        hist = history.History(
            name=name or self.title,
            description=description,
            metadata=self.get_metadata(),
            origin=origin,
            operation=operation,
            cmds=args,
            item_name=self.item_name,
            requirements=imports,
            children=children,
            kwargs=kwargs,
        )
        if config.settings.collapse_history and len(children) == 1:
            hist.collapse_operations(max_ops=1)
            hist.description = "Collapsed operations"
        self.set_history(hist)

        return self
