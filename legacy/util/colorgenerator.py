from __future__ import annotations

import itertools

from collections.abc import Generator, Iterator


class ColorGenerator:
    colors = [
        (240, 163, 255),
        (0, 117, 220),
        (153, 63, 0),
        (76, 0, 92),
        (25, 25, 25),
        (0, 92, 49),
        (43, 206, 72),
        (255, 204, 153),
        (128, 128, 128),
        (148, 255, 181),
        (143, 124, 0),
        (157, 204, 0),
        (194, 0, 136),
        (0, 51, 128),
        (255, 164, 5),
        (255, 168, 187),
        (66, 102, 0),
        (255, 0, 16),
        (94, 241, 242),
        (0, 153, 143),
        (224, 255, 102),
        (116, 10, 255),
        (153, 0, 0),
        (255, 255, 128),
        (255, 255, 0),
        (255, 80, 5),
    ]
    total_colors = len(colors)

    def __init__(self, max_colors: int = 26):
        self.set_max_colors(max_colors)
        self.names: dict[str, tuple[int, int, int]] = {}

    def __iter__(self) -> Iterator[tuple[int, int, int]]:
        if self.current_colors is None:
            raise TypeError("neet do call set_max_colors first")
        return iter(self.current_colors)

    def __getitem__(self, key: str) -> tuple[int, int, int]:
        return self.color_by_name(key)

    def set_max_colors(self, max_colors: int):
        colors = self.colors[: min(max_colors, self.total_colors)]
        self.current_colors = itertools.cycle(colors)

    def new(self) -> Generator[tuple[int, int, int], None, None]:
        if self.current_colors is None:
            raise TypeError("neet do call set_max_colors first")
        yield from self.current_colors

    def color_by_name(self, name: str) -> tuple[int, int, int]:
        if name in self.names:
            return self.names[name]
        if self.current_colors is None:
            raise TypeError("neet do call set_max_colors first")
        color = next(self.current_colors)
        self.names[name] = color
        return color

    def color_by_name_hex(self, name: str) -> str:
        c = self.color_by_name(name)
        return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"

    def num_colors(self) -> int:
        return len(self.names.keys())


if __name__ == "__main__":
    cg = ColorGenerator()
    cg.color_by_name("test")
    print(cg["test"])
