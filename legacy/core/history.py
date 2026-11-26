from __future__ import annotations

import copy
import itertools
import logging
from typing import TYPE_CHECKING, Any

from datacook.core import codeblock, itemclasses, nesteditem, serializemixin
from datacook.util import helpers


if TYPE_CHECKING:
    from collections.abc import Iterable


logger = logging.getLogger(__name__)


class History(serializemixin.SerializeMixin, nesteditem.NestedItem):
    # item_name = "Undefined"

    def __init__(
        self,
        item_name: str,
        name: str = "",
        description: str = "",
        operation: str = "modification",
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
        cmds: Iterable[str] | None = None,
        requirements: Iterable[str] | None = None,
        kwargs: dict[str, Any] | None = None,
        **kwargs_,
    ):
        super().__init__(**kwargs_)
        self.name = name
        self.item_name = item_name
        self.description = description
        self.operation = operation
        self.origin = str(origin) if origin else None
        self.metadata = metadata
        self.requirements: set[str] = set()
        self.kwargs = kwargs if kwargs is not None else {}
        self.set_kwargs(self.kwargs)
        self.cmds = codeblock.Code()
        if cmds is not None:
            self.cmds.extend(cmds)
            self.requirements |= helpers.extract_imports(cmds)
        if requirements is not None:
            self.add_imports(requirements)

    def __add__(self, other: History) -> History:
        """Needed for "+"."""
        if not isinstance(other, History):
            raise TypeError("Can only add other Histories")
        if self.is_import_op() and other.is_import_op():
            raise TypeError("Cannot merge imports")
        self.requirements |= other.requirements
        if other.is_import_op():
            self.operation = "import"
            self.origin = other.origin
            self.description = other.description
            self.cmds = other.cmds + self.cmds
        else:
            self.cmds += other.cmds

        return self

    def __eq__(self, other):
        return self.__dict__ == other.__dict__ if isinstance(other, History) else False

    def __radd__(self, other):
        """Needed for sum()."""
        return self if other == 0 else self.__add__(other)

    def __hash__(self):
        """Hash based on the YAML representation (needed for sets / dict keys).

        TODO: should not be implemented for mutable objects?
        """
        return hash(self.to_yaml())

    def __repr__(self):
        return self.to_yaml()

    def as_json(self) -> dict[str, Any]:
        """Recursively build a dictionary of the complete history, including children.

        Items with value None are left out to keep the result compact.
        """
        dct = dict(
            name=self.name,
            id=self.count,
            dynamic_name=self.dynamic_name,
            item_name=self.item_name,
            operation=self.operation,
            description=self.description,
            kwargs=self.kwargs,
            shape=self.metadata,
            source=self.origin,
            requirements=list(self.requirements),
            commands=str(self.cmds),
            children=[c.as_json() for c in self.children],
        )
        return {k: v for k, v in dct.items() if v is not None}

    @classmethod
    def from_json(cls, node_dict: Any) -> Any:
        """Instanciate a history object based on a python dictionary."""
        return cls(
            name=node_dict.get("name", ""),
            count=node_dict.get("id"),
            dynamic_name=node_dict.get("dynamic_name"),
            item_name=node_dict.get("item_name", ""),
            origin=node_dict.get("source"),
            operation=node_dict.get("operation", ""),
            kwargs=node_dict.get("kwargs"),
            requirements=set(node_dict.get("requirements")),
            metadata=node_dict.get("shape"),
            description=node_dict.get("description"),
            cmds=codeblock.Code(code=node_dict.get("commands")),
            children=[cls.from_json(c) for c in node_dict.get("children")],
        )

    def add_imports(self, imports: Iterable[str]):
        lines = [
            f"import {imp}" if not imp.startswith(("import ", "from ")) else imp for imp in imports
        ]
        self.requirements.update(lines)

    def lines_of_code(self) -> int:
        """Return the line count of this item including children (no imports / comments)."""
        cmds = [len(hist.cmds) for hist in self.iter_tree(assign_names=False)]
        return sum(cmds)

    def set_kwargs(self, kwargs: dict[str, Any]):
        if kwargs:
            self.requirements |= helpers.extract_imports(kwargs.values())
        self.kwargs = kwargs

    def prepared_code_block(self, comments: bool = True, garbage_collect: bool = False) -> str:
        code = str(self.cmds).replace(f"|{self.item_name}|", self.dynamic_name)
        comment = f"# {self.description}\n" if comments and self.description else ""
        code_block = f"{comment}{code}\n\n"
        code_block = code_block.replace("|ORIGIN|", repr(self.origin))
        code_block = code_block.replace("|KWARGS|", helpers.format_kwargs(self.kwargs))
        to_replace = helpers.format_kwargs(self.kwargs, prepend_comma=True)
        code_block = code_block.replace("|OPTKWARGS|", to_replace)
        # if merge child, append merge code
        if len(self.children) > 1:
            child_names = [c.dynamic_name for c in self.children]
            if "|CHILD_NAMES|" in code_block:
                ds_names = str(child_names).replace("'", "")
                code_block = code_block.replace("|CHILD_NAMES|", ds_names)
            if "|CHILD_NAME_" in code_block:
                for i, name in enumerate(child_names, start=1):
                    code_block = code_block.replace(f"|CHILD_NAME_{i}|", name)
            if garbage_collect:
                code_block += f"del {', '.join(child_names)}\ngc.collect()\n"
        return code_block

    def get_requirements(self, recursive: bool = True) -> set[str]:
        """Returns set of lines containing import statements.

        Args:
            recursive: Check recursively (default: {True})

        Returns:
            set containining all required import strings
            example: ["import pandas as pd", "from pan import das"]
        """
        reqs = [
            history.requirements
            for history in self.iter_tree(recursive=recursive, assign_names=False)
        ]
        return set(itertools.chain.from_iterable(reqs))

    def get_origins(self, recursive: bool = True) -> list[str]:
        return [
            history.origin
            for history in self.iter_tree(recursive=recursive, assign_names=False)
            if history.origin
        ]

    def import_block(self, recursive: bool = True, garbage_collect: bool = False) -> str:
        """Return the import block as text (includes the gc module if needed)."""
        reqs = self.get_requirements() if recursive else self.requirements
        code = "\n".join(sorted(reqs))
        if garbage_collect and self.contains_merges():
            code += "\nimport gc"
        return code

    def contains_merges(self) -> bool:
        """Returns true if any of children is a merge operation."""
        return any(len(h.children) > 1 for h in self.iter_tree(recursive=True, assign_names=False))

    def is_import_op(self) -> bool:
        return self.operation == "import"

    def delete(self):
        """Delete node and connect parent with children."""
        if self.is_import_op() or len(self.children) != 1 or self.parent is None:
            logger.error("cannot delete node")
            return
        self.children[0].parent = self.parent
        self.parent.children = self.children
        del self

    def code_block(
        self, recursive: bool = True, comments: bool = True, garbage_collect: bool = False
    ) -> codeblock.Code:
        cmd = ""
        if recursive:
            for h in self.iter_tree(recursive=recursive):
                cmd += h.prepared_code_block(comments=comments, garbage_collect=garbage_collect)
        else:
            cmd = self.prepared_code_block(comments=comments, garbage_collect=garbage_collect)
        return codeblock.Code(code=cmd.strip())

    def as_code(
        self, recursive: bool = True, comments: bool = True, garbage_collect: bool = False
    ) -> codeblock.Code:
        """Returns complete prepared code including imports."""
        import_str = self.import_block(recursive=recursive, garbage_collect=garbage_collect)
        process_code = self.code_block(
            recursive=recursive, comments=comments, garbage_collect=garbage_collect
        )
        src = f"{import_str}\n\n{process_code}" if import_str else process_code
        return codeblock.Code(code=src)

    def collapse_children(self):
        """Merge all children into this node, becomes an import cmd then."""
        if not self.children:
            logger.error("Node does not contain children")
            return
        self.requirements.update(self.get_requirements())
        if self.contains_merges():
            logger.debug("%s contains merges. Code gets wrapped in method", self.description)
            code = self.deepcopy().code_block()
            method_name = f"return_{self.item_name}"
            method_text, method_name = code.wrap_in_method(
                method_name=method_name, obj_name=self.dynamic_name
            )
            self.description = "Merged actions"
            self.cmds = codeblock.Code()
            self.cmds.extend(method_text)
            self.requirements |= helpers.extract_imports(method_text)
        else:
            node = self
            count = 1
            while node.children:
                count += 1
                node = node.children[0]
                self.cmds = (
                    node._code_lines_with_kwargs_resolved()
                    + self._code_lines_with_kwargs_resolved()
                )
            node.parent = self
            self.origin = node.origin
            self.description = f"{count} merged actions"
        self.children = []
        self.operation = "import"

    def _code_lines_with_kwargs_resolved(self) -> codeblock.Code:
        text = self.cmds.replace("|KWARGS|", helpers.format_kwargs(self.kwargs))
        text = self.cmds.replace(
            "|OPTKWARGS|", helpers.format_kwargs(self.kwargs, prepend_comma=True)
        )
        return codeblock.Code(text)

    def collapse_operations(self, max_ops: int | None = None):
        """Merge iteratively with child until import or merge is hit."""
        node = self
        count = 0
        logger.debug("Merging %s with %s children", self.description, max_ops)
        while len(node.children) == 1:
            node = node.children[0]
            count += 1
            if node.is_import_op():
                continue
            logger.debug("Merging with %s", node.description)
            self.requirements.update(node.requirements)
            self.cmds = (
                node._code_lines_with_kwargs_resolved() + self._code_lines_with_kwargs_resolved()
            )
            if max_ops and count == max_ops:
                break
        if count > 0:
            logger.debug(
                "Re-connecting child/parent relations for %s and %s",
                self.description,
                node.description,
            )
            for item in node.children:
                item.parent = self
            self.children = node.children
            self.description = f"{count + 1} merged actions"

    def evaluate(self, context: dict[str, Any] | None = None):
        """Construct a dataset from the contained code and attach this history to it."""
        code = self.as_code(garbage_collect=True)
        compiled = code.evaluate(context, return_val=self.item_name)
        # TODO: not 100% if I need deepcopy here.
        if compiled is None:
            logger.info("Script execution failed.")
            raise TypeError("Script returned None")
        item_cls = itemclasses.get_class_for_instance(compiled)
        return item_cls(
            compiled,
            name=self.name,
            # comment=self.comment,
            history=self.deepcopy(),
        )

    def deepcopy(self) -> History:
        """Make a deepcopy of self."""
        return copy.deepcopy(self)
