"""Parse a script back into op records (the code view's edit path).

Statements produced by `codegen` are recognised by the ops' `from_code`. The script is read
in blocks separated by blank lines (codegen writes one step per block). A block whose
statements are all recognised becomes one step per statement; any other block becomes one
`CustomCode` step working on the variable `df`. Plain aliases (`a = b`,
`a = b.copy(deep=False)`) only rebind names. Custom code on a branch variable is generated
as `def custom_step(df): ...` + call and parsed back. Leading imports are skipped.
"""

import ast
from dataclasses import dataclass, field
import textwrap
from typing import TYPE_CHECKING

import pydantic

from datacook.engine.ops import Match, OpRecord, base
from datacook.engine.ops.code import FUNCTION, VAR, CustomCode


if TYPE_CHECKING:
    from collections.abc import Sequence

    from datacook.engine.ops import Op
    from datacook.engine.registry import Registry


class ParseError(ValueError):
    def __init__(self, message: str, lineno: int | None = None) -> None:
        self.message = message
        self.lineno = lineno
        super().__init__(f"line {lineno}: {message}" if lineno else message)


@dataclass(frozen=True, slots=True)
class Step:
    record: OpRecord
    parents: tuple[int, ...]
    """Indexes into `ParsedScript.steps`; negative: `-1 - i` = the i-th pre-bound input."""
    output: str
    name: str | None
    lineno: int
    end_lineno: int


@dataclass(slots=True)
class ParsedScript:
    steps: list[Step] = field(default_factory=list)
    variables: dict[str, int] = field(default_factory=dict)
    """Variable name -> step index at the end of the script."""

    @property
    def records(self) -> list[OpRecord]:
        return [s.record for s in self.steps]


def _alias(stmt: ast.stmt, bound: dict[str, int]) -> tuple[str, str] | None:
    if not (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
    ):
        return None
    value = stmt.value
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "copy"
        and not value.args
        and all(kw.arg == "deep" for kw in value.keywords)
    ):
        value = value.func.value
    if isinstance(value, ast.Name) and value.id in bound:
        return stmt.targets[0].id, value.id
    return None


def parse(
    text: str,
    registry: Registry[type[Op]],
    inputs: Sequence[str] = (),
) -> ParsedScript:
    """Parse `text`; `inputs` are variable names bound before the script starts."""
    try:
        module = ast.parse(text)
    except SyntaxError as e:
        raise ParseError(e.msg, e.lineno) from e
    lines = text.splitlines()
    ops = list(registry)
    result = ParsedScript()
    bound: dict[str, int] = {name: -1 - i for i, name in enumerate(inputs)}

    def comment_above(lineno: int) -> str | None:
        """`label` if line lineno-1 is `# label` and starts a block (blank line before)."""
        idx = lineno - 2
        if idx < 0 or not lines[idx].lstrip().startswith("#"):
            return None
        if idx > 0 and lines[idx - 1].strip():
            return None
        return lines[idx].lstrip()[1:].strip() or None

    def step_name(label: str | None, op: type[Op]) -> str | None:
        if label is None or label in (str(op.title), op.title.msgid):
            return None
        return label

    def custom(block: list[ast.stmt]) -> None:
        output = VAR
        first, last = block[0], block[-1]
        if VAR not in bound:
            msg = f"statement not understood, and there is no {VAR!r} to run it on as custom code"
            raise ParseError(msg, first.lineno)
        end = last.end_lineno or last.lineno
        code = "\n".join(lines[first.lineno - 1 : end])
        record = OpRecord(CustomCode.id, CustomCode.Params(code=code))
        name = step_name(comment_above(first.lineno), CustomCode)
        result.steps.append(Step(record, (bound[VAR],), output, name, first.lineno, end))
        bound[output] = len(result.steps) - 1

    def recognise(stmt: ast.stmt, scope: dict[str, int]) -> tuple[type[Op], Match] | None:
        # an op rejecting the arguments may just be the wrong op for a call that several
        # ops generate (`df.sort_values(...)`): report the error only if no op matches
        error: ParseError | None = None
        for op in ops:
            try:
                found = op.from_code(stmt, scope)
            except (ValueError, TypeError, pydantic.ValidationError) as e:
                if error is None:
                    error = ParseError(f"{op.id}: {e}", stmt.lineno)
                    error.__cause__ = e
                continue
            if found is not None:
                if not op.takes(len(found.inputs)):
                    raise ParseError(f"{op.id} needs {op.inputs_text()} input(s)", stmt.lineno)
                return op, found
        if error is not None:
            raise error
        return None

    def custom_function(block: list[ast.stmt]) -> bool:
        """`def custom_step(df): ... return df` + `out = custom_step(var)` (codegen form)."""
        if len(block) != 2:  # noqa: PLR2004
            return False
        func, call = block
        assign = base.assignment(call)
        if not (
            isinstance(func, ast.FunctionDef)
            and func.name == FUNCTION
            and [a.arg for a in func.args.args] == [VAR]
            and len(func.body) > 1
            and isinstance(ret := func.body[-1], ast.Return)
            and isinstance(ret.value, ast.Name)
            and ret.value.id == VAR
            and assign is not None
            and isinstance(value := assign[1], ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == FUNCTION
            and len(value.args) == 1
            and isinstance(arg := value.args[0], ast.Name)
            and arg.id in bound
        ):
            return False
        first, last = func.body[0], func.body[-2]
        end = last.end_lineno or last.lineno
        code = textwrap.dedent("\n".join(lines[first.lineno - 1 : end]))
        record = OpRecord(CustomCode.id, CustomCode.Params(code=code))
        name = step_name(comment_above(func.lineno), CustomCode)
        lineno, end_lineno = func.lineno, call.end_lineno or call.lineno
        result.steps.append(Step(record, (bound[arg.id],), assign[0], name, lineno, end_lineno))
        bound[assign[0]] = len(result.steps) - 1
        return True

    def process(block: list[ast.stmt]) -> None:
        if custom_function(block):
            return
        # dry run: are all statements aliases or recognised ops?
        scope = dict(bound)
        plan: list[tuple[ast.stmt, tuple[type[Op], Match] | None]] = []
        for stmt in block:
            alias = _alias(stmt, scope)
            if alias is not None:
                scope[alias[0]] = scope[alias[1]]
                plan.append((stmt, None))
                continue
            match = recognise(stmt, scope)
            if match is None:
                custom(block)
                return
            scope[match[1].output] = 0
            plan.append((stmt, match))
        for stmt, match in plan:
            if match is None:
                alias = _alias(stmt, bound)
                assert alias is not None
                bound[alias[0]] = bound[alias[1]]
                continue
            op, found = match
            step = Step(
                OpRecord(op.id, found.params),
                tuple(bound[v] for v in found.inputs),
                found.output,
                step_name(comment_above(stmt.lineno), op),
                stmt.lineno,
                stmt.end_lineno or stmt.lineno,
            )
            result.steps.append(step)
            bound[found.output] = len(result.steps) - 1

    body = list(module.body)
    while body and isinstance(body[0], (ast.Import, ast.ImportFrom)):
        body.pop(0)
    # blocks: separated by blank lines (codegen writes one step per block)
    block: list[ast.stmt] = []
    for stmt in body:
        if block:
            prev_end = block[-1].end_lineno or block[-1].lineno
            first_line = stmt.lineno - 1 if comment_above(stmt.lineno) else stmt.lineno
            gap = lines[prev_end : first_line - 1]
            if any(not line.strip() for line in gap):
                process(block)
                block = []
        block.append(stmt)
    if block:
        process(block)
    result.variables = {k: v for k, v in bound.items() if v >= 0}
    return result
