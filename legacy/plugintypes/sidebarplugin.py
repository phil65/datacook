from __future__ import annotations

from prettyqt import widgets


class SidebarPlugin(widgets.Widget):
    plugin_category = "Dock"
    DEFAULT_POSITION = "right"
    MIN_SIZE = (200, 50)

    def unregister(self):
        pass
