from __future__ import annotations

import logging
import logging.config
import pathlib
import re
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import yaml


if TYPE_CHECKING:
    from collections.abc import Iterable


logger = logging.getLogger(__name__)

FUNCTIONS = {
    len: "len",
    np.mean: "numpy.mean",
    np.median: "numpy.median",
    np.std: "numpy.std",
    np.sum: "numpy.sum",
    np.min: "numpy.min",
    np.max: "numpy.max",
}


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub("[^0-9a-zA-Z_#]", "_", text)
    return re.sub("^[^a-zA-Z_#]+", "", text)


def move_in_list(ls: list, indexes: list, target_row: int) -> list:
    new = [ls[i] for i in indexes]
    in_range = target_row < len(ls) and target_row != -1
    pos = ls.index(ls[target_row]) if in_range else len(ls)
    rem = 0
    for i in sorted(indexes, reverse=True):
        ls.pop(i)
        if i <= pos:
            rem += 1
    for item in reversed(new):
        ls.insert(pos - rem, item)
    return ls


def format_kwargs(kwargs: dict[str, Any], prepend_comma: bool = False) -> str:
    kwarg_list = []
    if not kwargs:
        return ""
    for k, v in kwargs.items():
        if not isinstance(v, (list, dict)) and v in FUNCTIONS:
            v = FUNCTIONS[v]
        # TODO: could also use float("NaN") and math.isnan ?
        elif is_nan(v):
            v = "numpy.nan"
        elif isinstance(v, pathlib.Path):
            v = repr(str(v))
        else:
            v = repr(v)
        kwarg_list.append(f"{k}={v}")
    text = ", ".join(kwarg_list)
    return f", {text}" if prepend_comma and text else text


def replace_kwargs_template(self, text: str, kwargs: dict[str, Any]):
    text = text.replace("|KWARGS|", format_kwargs(self.kwargs))
    return text.replace("|OPTKWARGS|", format_kwargs(self.kwargs, prepend_comma=True))


def infer_type(text: str):
    try:
        if float(text).is_integer():
            return int(text)
        return float(text)
    except TypeError, ValueError:
        return text


def format_name(name) -> str:
    if isinstance(name, (tuple, list)):
        return " | ".join(str(i) for i in name)
    return str(name)


def is_nan(obj) -> bool:
    try:
        return np.isnan(obj) if isinstance(obj, float) else False
    except TypeError:
        return False


def save_yaml(data, path: pathlib.Path):
    """Serialize a list of history objects to YAML and save it at the given path."""
    json_str = yaml.dump(data, sort_keys=False, allow_unicode=True)
    path.write_text(json_str)
    logger.debug("saved to %s", path)


def load_yaml(path: pathlib.Path) -> dict | list | None:
    """Read the history objects stored (as a YAML list) in the given file."""
    if not path.exists():
        logger.warning("File %s does not exist.", path)
        return None
    try:
        return yaml.full_load(path.read_text())
    except EOFError, TypeError:
        logger.exception("Error when loading from %s", path)
        return None


def index_description(index: pd.Index) -> str:
    if isinstance(index, pd.MultiIndex):
        return f"MultiIndex ({len(index.levels)})"
    return str(index.name)


def list_imports(import_lines: list[str]) -> str:
    items = [
        imp.strip()
        for line in import_lines
        if line.strip().startswith("import ")
        for imp in line.strip()[7:].split(",")
    ]
    items2 = [
        line.strip()[5:].split(" ")[0] for line in import_lines if line.strip().startswith("from ")
    ]
    reqs = set(items + items2)

    return "Required imports:\n" + "\n".join(reqs) if reqs else ""


def extract_imports(lines: Iterable[Any]) -> set:
    imports = set()
    for ln in lines:
        ln = repr(ln)
        if "Timestamp(" in ln:
            imports.add("from pandas import Timestamp")
        if "Timedelta(" in ln:
            imports.add("from pandas import Timedelta")
        if "Interval(" in ln:
            imports.add("from pandas import Interval")
        if "datetime." in ln:
            imports.add("import datetime")
        if ln == "nan":
            imports.add("import numpy")
    return imports


def format_num(num: int) -> str:
    return format(num, ",")


def get_subpaths(paths) -> list:
    if not paths:
        return []
    if paths[0] == "":
        paths = [
            folder / filename
            for folder in paths
            for filename in folder.iterdir()
            if (folder / filename).is_file()
        ]
    return paths


def get_subclasses(klass):
    for i in klass.__subclasses__():
        yield from get_subclasses(i)
        yield i
