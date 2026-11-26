"""The package imports; the engine does not pull in Qt or the legacy core."""

import subprocess
import sys

import datacook


def test_package_imports() -> None:
    assert isinstance(datacook.__version__, str)


def test_engine_is_qt_free() -> None:
    code = (
        "import sys\n"
        "import datacook.engine, datacook.engine.formats, datacook.engine.project\n"
        "from datacook.engine import default_ops\n"
        "list(default_ops())\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in "
        "('PySide6', 'PyQt6', 'shiboken6', 'prettyqt', 'qtpy', 'cutepandas', 'processanalyzer')"
        " or m.startswith(('datacook.core', 'datacook.methods'))]\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == ""
