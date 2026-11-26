"""DataCook desktop app (Qt) on top of the Qt-free engine.

Importing this package does not import Qt: `protocols`, `settings`, `pins`, `eventqueue`,
`jobs` and `testing` are Qt-free (they also run on free-threaded Python); everything else
(`state`, `bridge`, `slots`, `commands`, `controllers`, `mainwindow`, docks) needs Qt.
Start with `README.md` in this folder.
"""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """GUI entry point: set up the allocators before pyarrow is imported, then start."""
    from datacook import allocator

    allocator.configure()
    from datacook.app.application import main as run

    return run(argv)
