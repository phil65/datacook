from __future__ import annotations

import ast
import hashlib
import logging
import textwrap
import time
from typing import TYPE_CHECKING, Any

from datacook.util import helpers


if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


logger = logging.getLogger(__name__)


class Code:
    def __init__(self, code=""):
        self.data = str(code)

    def __add__(self, other):
        """Needed for "+"."""
        match other:
            case Code():
                self.data += f"\n{other.data}"
            case str():
                self.data += f"\n{other}"
            case list():
                self.extend(other)
            case _:
                raise TypeError(f"Addition with {type(other)} not supported")
        return Code(code=self.data)

    def __eq__(self, other):
        return self.data == other.data if isinstance(other, Code) else False

    def __bool__(self):
        return bool(self.data)

    def __radd__(self, other):
        """Needed for sum()."""
        return self if other == 0 else self.__add__(other)

    def __iter__(self) -> Iterator[str]:
        return iter(self.lines())

    def __str__(self):
        return self.data

    def __len__(self):
        return self.data.count("\n") + 1 if self.data else 0

    def __repr__(self):
        return f"CodeBlock:\n{self.data}"

    def lines(self) -> list[str]:
        return self.data.split("\n")

    def hash_code(self) -> str:
        hashed = hashlib.sha1(self.data.encode("UTF-8")).hexdigest()
        return hashed[:10]

    def append(self, line):
        if line:
            self.data += line

    def extend(self, lines: Iterable[str]):
        self.data += "\n".join([str(ln) for ln in lines if ln])

    def replace(self, before: str, after: str) -> str:
        return self.data.replace(before, after)

    def wrap_in_method(
        self,
        method_name: str,
        input_param: bool = False,
        obj_name: str = "",
        apply: bool = True,
    ) -> tuple[Code, str]:
        method_name = helpers.slugify(method_name)
        param = obj_name if input_param else ""
        body = textwrap.indent(f"{self.data}\nreturn {obj_name}\n", "    ")
        method_text = f"def {method_name}({param}):\n{body}"
        if apply:
            arg = f"|{obj_name}|" if input_param else ""
            method_text += f"\n|{obj_name}| = {method_name}({arg})"
        return Code(code=method_text), method_name

    def get_import_lines(self) -> set:
        """Filter out lines with imports."""
        items = [
            line.strip() for line in self.lines() if line.strip().startswith(("import ", "from "))
        ]
        return set(items)

    def get_process_code(self, indent: int = 0) -> Code:
        """Filter out lines with processing code."""
        items = [
            line
            for line in self.lines()
            if line != "" and not line.strip().startswith(("import ", "from "))
        ]

        return Code(code=textwrap.indent("\n".join(items), " " * indent))

    def code_to_lines(self, var_name: str, fn_name: str) -> tuple[Code, str]:
        if self.data.startswith("return "):
            fn_name = self.data.replace("return ", f"lambda {var_name}: ")
            lines = ""
        else:
            lines = f"def {fn_name}({var_name}):\n{textwrap.indent(self.data, '    ')}\n"
        return Code(code=lines), fn_name

    def evaluate(self, context: dict[str, Any] | None = None, return_val: str | None = None):
        """Evaluate several lines of input, returning the result of the last line."""
        now = time.time()
        if context is None:
            context = locals()
        code = str(self.data) if return_val is None else f"{self.data}\n{return_val}"
        logger.debug("Evaluating code:\n%s", self.data)
        tree = ast.parse(code)
        last = tree.body[-1]
        if not isinstance(last, ast.Expr):
            msg = "The last line of the code must be an expression"
            raise TypeError(msg)
        eval_expr = ast.Expression(last.value)
        exec_expr = ast.parse("")
        exec_expr.body = tree.body[:-1]
        compiled = compile(exec_expr, "file", "exec")
        exec(compiled, context)
        val = eval(compile(eval_expr, "file", "eval"), context)
        logger.debug("Code evaluation took %s seconds.", time.time() - now)
        return val
