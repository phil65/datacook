"""Translations (gettext, German + English catalogs in `datacook/locales`).

`_()` returns a `LazyText`: the message is looked up each time it is turned into a string,
so class-level metadata (op titles, category names) follows `set_language()` even when it
runs after import. Pydantic field titles must be plain strings: mark them with `N_()` (a
no-op marker the gettext scan picks up) and translate them in the UI with `translate()`.
"""

import gettext
import pathlib
import threading


LANG_DIR = pathlib.Path(__file__).parent / "locales"
DOMAIN = "datacook"

_lock = threading.Lock()
_translation: gettext.NullTranslations = gettext.NullTranslations()


def set_language(language: str | None) -> None:
    """Switch the active language (`None` or "en" -> source strings)."""
    global _translation
    if language in (None, "en"):
        new: gettext.NullTranslations = gettext.NullTranslations()
    else:
        new = gettext.translation(DOMAIN, localedir=str(LANG_DIR), languages=[language])
    with _lock:
        _translation = new


def translate(text: str) -> str:
    """Translate a message id with the active language ("" stays "", not the PO header)."""
    return _translation.gettext(text) if text else text


class LazyText:
    """A message id that is translated whenever it is used as a string."""

    __slots__ = ("msgid",)

    def __init__(self, msgid: str) -> None:
        self.msgid = msgid

    def __str__(self) -> str:
        return translate(self.msgid)

    def __repr__(self) -> str:
        return f"_({self.msgid!r})"

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LazyText):
            return self.msgid == other.msgid
        if isinstance(other, str):
            return str(self) == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.msgid)

    def __add__(self, other: str) -> str:
        return str(self) + other

    def __radd__(self, other: str) -> str:
        return other + str(self)


def _(text: str) -> LazyText:
    """Mark a message for translation; translated lazily when used as a string."""
    return LazyText(text)


def N_(text: str) -> str:  # noqa: N802
    """Mark a message for extraction only (e.g. pydantic field titles)."""
    return text
