"""Custom code op: arbitrary Python working on the variable `df`."""

import textwrap
from typing import TYPE_CHECKING, Any

from pydantic import Field

from datacook.engine import categories
from datacook.engine.ops import base
from datacook.i18n import N_, _


if TYPE_CHECKING:
    import ast
    from collections.abc import Mapping, Sequence

    from datacook.engine.frames import Frame

VAR = "df"
FUNCTION = "custom_step"


class CustomCode(base.Op):
    """Python statements that read and rebind `df` (pandas is available as `pd`).

    The code parser turns statements it does not recognise into this op, so any script
    stays editable as one opaque step.
    """

    id = "custom_code"
    title = _("Custom code")
    description = _("Run Python code on the table (variable 'df', pandas as 'pd').")
    category = categories.CODE
    icon = "mdi.language-python"
    imports = ("import numpy as np", "import pandas as pd")

    class Params(base.Params):
        code: str = Field(title=N_("Code"), min_length=1, json_schema_extra={"widget": "code"})

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import numpy as np
        import pandas as pd

        try:
            code = compile(params.code, "<custom code>", "exec")
        except SyntaxError as e:
            raise base.OpError(f"line {e.lineno}: {e.msg}") from e
        # a new frame object (sharing data, copy-on-write) so in-place edits like
        # `df["c"] = 1` cannot modify the parent's cached frame
        namespace: dict[str, Any] = {"pd": pd, "np": np, VAR: inputs[0].copy(deep=False)}
        exec(code, namespace)
        result = namespace.get(VAR)
        if not isinstance(result, pd.DataFrame):
            msg = f"custom code must leave a DataFrame in {VAR!r}, got {type(result).__name__}"
            raise base.OpError(msg)
        return result

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        code = params.code.strip("\n")
        if inputs[0] == VAR == output:
            return code
        # other variables (branches): a function, so `df` of other steps stays untouched
        body = textwrap.indent(code, "    ")
        return (
            f"def {FUNCTION}({VAR}):\n{body}\n    return {VAR}\n{output} = {FUNCTION}({inputs[0]})"
        )

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        # the parser builds custom code from runs of unrecognised statements itself
        return None
