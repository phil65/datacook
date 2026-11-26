"""Categorical column ops (`.cat` accessor): add, remove, rename, reorder, set categories.

Categorical columns use the pandas `category` dtype (from "Change data type" with
`"category"`); its categories keep their arrow-backed dtype. Arrow `dictionary` columns have
no `.cat` accessor: convert them to `category` first. Every op works on one column and
replaces it in place: `df = df.assign(c=df["c"].cat.add_categories(["x"]))`.
"""

from typing import Any

from pydantic import Field

from datacook.engine import categories
from datacook.engine.ops import base
from datacook.i18n import N_, _


type Scalar = bool | int | float | str


def _column() -> Any:
    return Field(title=N_("Column"), json_schema_extra={"widget": "column"})


class _CategoryOp(base.ColumnCallOp):
    category = categories.CATEGORICAL
    accessor = "cat"

    class Params(base.Params):
        column: str = _column()


class AddCategories(_CategoryOp):
    id = "cat_add_categories"
    title = _("Add categories")
    description = _("Add new (unused) categories to a categorical column.")
    icon = "mdi.plus-box-outline"
    method = "add_categories"
    positional = ("new_categories",)

    class Params(base.Params):
        column: str = _column()
        new_categories: list[Scalar] = Field(title=N_("New categories"), min_length=1)


class RemoveCategories(_CategoryOp):
    id = "cat_remove_categories"
    title = _("Remove categories")
    description = _("Remove categories; values of a removed category become missing.")
    icon = "mdi.minus-box-outline"
    method = "remove_categories"
    positional = ("removals",)

    class Params(base.Params):
        column: str = _column()
        removals: list[Scalar] = Field(title=N_("Categories to remove"), min_length=1)


class RenameCategories(_CategoryOp):
    id = "cat_rename_categories"
    title = _("Rename categories")
    description = _("Rename categories (old name -> new name); the values follow.")
    icon = "mdi.rename-box"
    method = "rename_categories"
    positional = ("new_categories",)

    class Params(base.Params):
        column: str = _column()
        new_categories: dict[str, Scalar] = Field(title=N_("New names"), min_length=1)


class ReorderCategories(_CategoryOp):
    id = "cat_reorder_categories"
    title = _("Reorder categories")
    description = _("Put the categories in a new order (all categories, each once).")
    icon = "mdi.sort"
    method = "reorder_categories"
    positional = ("new_categories",)

    class Params(base.Params):
        column: str = _column()
        new_categories: list[Scalar] = Field(title=N_("Categories in new order"), min_length=1)
        ordered: bool | None = Field(None, title=N_("Ordered"))


class SetCategories(_CategoryOp):
    id = "cat_set_categories"
    title = _("Set categories")
    description = _(
        "Replace the categories: values not in the new categories become missing,"
        " new categories are added."
    )
    icon = "mdi.format-list-bulleted-type"
    method = "set_categories"
    positional = ("new_categories",)

    class Params(base.Params):
        column: str = _column()
        new_categories: list[Scalar] = Field(title=N_("Categories"))
        ordered: bool | None = Field(None, title=N_("Ordered"))
        rename: bool = Field(False, title=N_("Rename (match by position)"))


class AsOrdered(_CategoryOp):
    id = "cat_as_ordered"
    title = _("Set categories as ordered")
    description = _("Mark the categories as ordered (enables min / max and comparisons).")
    icon = "mdi.order-numeric-ascending"
    method = "as_ordered"


class AsUnordered(_CategoryOp):
    id = "cat_as_unordered"
    title = _("Set categories as unordered")
    description = _("Mark the categories as unordered.")
    icon = "mdi.order-bool-ascending"
    method = "as_unordered"


class RemoveUnusedCategories(_CategoryOp):
    id = "cat_remove_unused"
    title = _("Remove unused categories")
    description = _("Remove categories that no value uses.")
    icon = "mdi.broom"
    method = "remove_unused_categories"
