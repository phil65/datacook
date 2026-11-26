"""The app icon ships with the package and loads in every size."""

from datacook.app.application import ICON_DIR, app_icon


def test_icon_files_ship_with_the_package():
    sizes = sorted(int(p.stem.split("x")[0]) for p in ICON_DIR.glob("*.png"))
    assert sizes == [16, 24, 32, 48, 64, 128, 256]
    assert (ICON_DIR.parent / "icon.svg").is_file()
    assert (ICON_DIR.parent / "icon.ico").is_file()


def test_app_icon_has_all_sizes(qapp):
    icon = app_icon()
    assert not icon.isNull()
    assert {s.width() for s in icon.availableSizes()} >= {16, 32, 48, 256}
