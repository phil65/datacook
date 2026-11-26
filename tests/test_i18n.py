from datacook import i18n
from datacook.engine import categories
from datacook.engine.ops.rows import FilterRows


def test_translation_is_lazy() -> None:
    assert str(categories.FILTER.title) == "Filter operations"
    try:
        i18n.set_language("de")  # after the ops were imported
        assert str(categories.FILTER.title) == "Filter-Operationen"
        assert f"{categories.GENERAL.title}" == "Allgemein"
        assert FilterRows.category.title == "Filter-Operationen"
    finally:
        i18n.set_language(None)
    assert str(categories.FILTER.title) == "Filter operations"
    assert i18n.N_("x") == "x"


def test_empty_text_is_not_the_catalog_header() -> None:
    try:
        i18n.set_language("de")
        assert i18n.translate("") == ""
        assert str(i18n._("")) == ""
    finally:
        i18n.set_language(None)


def _msgids() -> set[str]:
    """Every string literal passed to `_()` / `N_()` in the package (what xgettext scans)."""
    import ast
    import pathlib

    root = pathlib.Path(i18n.__file__).parent
    ids: set[str] = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"_", "N_"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                ids.add(node.args[0].value)
    return ids


def test_german_catalog_is_complete() -> None:
    """Every msgid of the package has a German translation (run `uv run duty lang`)."""
    import gettext

    catalog = gettext.translation(i18n.DOMAIN, localedir=str(i18n.LANG_DIR), languages=["de"])
    translated = catalog._catalog  # ty: ignore[unresolved-attribute]
    ids = _msgids()
    assert len(ids) > 200
    missing = sorted(msgid for msgid in ids if not translated.get(msgid))
    assert missing == []
