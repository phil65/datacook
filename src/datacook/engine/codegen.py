"""Generate a Python (pandas) script from op records.

Every step is a block `# <label>` + the op's code; the label is the node name, or the op
title. A linear chain reuses one variable (`df = df.sort_values(...)`); a node gets its
own variable when its parent feeds more than one step (branches), when it is not the
parent's first input (merge) or when the parent is named (named nodes keep their variable,
`df_<name>`), so the script is correct in plain top-to-bottom order.
"""

from collections import Counter
from dataclasses import dataclass
import re
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from datacook.engine.node import Node
    from datacook.engine.ops import Op
    from datacook.engine.registry import Registry

MAIN_VAR = "df"


def _closure(nodes: Mapping[str, Node], targets: Iterable[str]) -> set[str]:
    keep: set[str] = set()
    stack = list(targets)
    while stack:
        nid = stack.pop()
        if nid not in keep:
            keep.add(nid)
            stack.extend(nodes[nid].parents)
    return keep


def _slug(name: str) -> str:
    slug = re.sub(r"\W+", "_", name.strip().lower()).strip("_")
    if not slug or not slug.isidentifier() or slug[0].isdigit():
        return ""
    return slug if slug.startswith("df") else f"df_{slug}"


def label(node: Node, op: type[Op]) -> str:
    return (node.name or str(op.title)).replace("\n", " ")


@dataclass(frozen=True, slots=True)
class Script:
    """A generated script plus where each node's block is in it."""

    text: str
    spans: dict[str, tuple[int, int]]
    """`{node_id: (first, last)}`: 1-based, inclusive line numbers of the node's block
    (its `# label` comment line through its last code line)."""


def render(
    nodes: Mapping[str, Node],
    registry: Registry[type[Op]],
    targets: Iterable[str] | None = None,
) -> Script:
    """Script computing `targets` (default: every node), with per-node line spans.

    `nodes` must be in topological order (parents first), as `Session.nodes()` is.
    """
    keep = set(nodes) if targets is None else _closure(nodes, targets)
    ordered = [n for n in nodes.values() if n.id in keep]
    consumers: Counter[str] = Counter(p for n in ordered for p in n.parents)
    variables: dict[str, str] = {}
    used: set[str] = set()

    def fresh(node: Node) -> str:
        for candidate in (_slug(node.name or ""), MAIN_VAR):
            if candidate and candidate not in used:
                return candidate
        i = 2
        while f"{MAIN_VAR}{i}" in used:
            i += 1
        return f"{MAIN_VAR}{i}"

    imports: dict[str, None] = {}
    blocks: list[tuple[str, str]] = []
    for node in ordered:
        op = registry[node.record.op_id]
        imports.update(dict.fromkeys(op.imports_for(node.record.params)))
        first = nodes[node.parents[0]] if node.parents else None
        if first is not None and consumers[first.id] == 1 and not first.name:
            var = variables[node.parents[0]]
        else:
            var = fresh(node)
        variables[node.id] = var
        used.add(var)
        inputs = [variables[p] for p in node.parents]
        code = op.to_code(node.record.params, inputs, var)
        blocks.append((node.id, f"# {label(node, op)}\n{code}"))
    header = sorted(imports, key=lambda line: (line.startswith("from "), line))
    parts = ["\n".join(header)] if header else []
    spans: dict[str, tuple[int, int]] = {}
    line = len(header) + 2 if header else 1  # first line of the next part
    for node_id, block in blocks:
        n_lines = block.count("\n") + 1
        spans[node_id] = (line, line + n_lines - 1)
        line += n_lines + 1  # blank line between parts
        parts.append(block)
    return Script("\n\n".join(parts) + "\n", spans)


def script(
    nodes: Mapping[str, Node],
    registry: Registry[type[Op]],
    targets: Iterable[str] | None = None,
) -> str:
    """Script computing `targets` (default: every node); see `render`."""
    return render(nodes, registry, targets).text


def script_spans(
    nodes: Mapping[str, Node],
    registry: Registry[type[Op]],
    targets: Iterable[str] | None = None,
) -> dict[str, tuple[int, int]]:
    """`{node_id: (first, last line)}` of each node's block in `script(...)` (1-based)."""
    return render(nodes, registry, targets).spans
