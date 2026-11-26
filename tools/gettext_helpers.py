"""Gettext catalogs of `src/datacook` (needs GNU gettext: xgettext, msgmerge, msgfmt).

    uv run python tools/gettext_helpers.py scan      # src -> datacook.pot -> merge into each .po
    uv run python tools/gettext_helpers.py compile   # .po -> .mo
    uv run python tools/gettext_helpers.py stats     # translated / fuzzy / untranslated

Keywords: `_()` (LazyText) and `N_()` (msgids, e.g. pydantic field titles). Only `src/datacook`
is scanned (not `legacy/`); msgids that disappear stay in the .po files as obsolete (`#~`)
entries, so msgmerge restores their translation when phase 4 ports the code back.
"""

import pathlib
import subprocess
import sys


PACKAGE = pathlib.Path(__file__).parent.parent / "src" / "datacook"
LOCALES = PACKAGE / "locales"
DOMAIN = "datacook"


def languages() -> list[str]:
    return sorted(p.name for p in LOCALES.iterdir() if (p / "LC_MESSAGES").is_dir())


def po_file(lang: str) -> pathlib.Path:
    return LOCALES / lang / "LC_MESSAGES" / f"{DOMAIN}.po"


def scan() -> None:
    root = PACKAGE.parent
    files = sorted(str(p.relative_to(root)) for p in PACKAGE.rglob("*.py"))
    pot = LOCALES / f"{DOMAIN}.pot"
    subprocess.run(
        [
            "xgettext",
            "--language=Python",
            "--from-code=UTF-8",
            "--keyword=_",
            "--keyword=N_",
            "--add-comments=TRANSLATORS:",
            "--sort-by-file",
            "--package-name=DataCook",
            f"--output={pot}",
            *files,
        ],
        cwd=root,
        check=True,
    )
    for lang in languages():
        po = po_file(lang)
        print(f"merging {po}")
        subprocess.run(
            ["msgmerge", "--quiet", "--update", "--backup=none", str(po), str(pot)], check=True
        )


def compile_catalogs() -> None:
    for lang in languages():
        po = po_file(lang)
        subprocess.run(["msgfmt", "--check", "-o", str(po.with_suffix(".mo")), str(po)], check=True)


def stats() -> None:
    for lang in languages():
        print(lang, end=": ", flush=True)
        cmd = ["msgfmt", "--statistics", "-o", "/dev/null", str(po_file(lang))]
        subprocess.run(cmd, check=True)


def main(argv: list[str]) -> int:
    commands = {"scan": scan, "compile": compile_catalogs, "stats": stats}
    if len(argv) != 1 or argv[0] not in commands:
        print(__doc__)
        return 2
    commands[argv[0]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
