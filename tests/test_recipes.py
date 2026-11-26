"""Engine: delete a middle step keeping its children (O6); recipes and the library (O1)."""

import json
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from datacook.engine import EventKind, Session, recipes
from datacook.engine.ops import columns, combine, rows, sources
from datacook.engine.ops.base import column_refs
from datacook.engine.recipes import INPUT, RecipeError, RecipeLibrary
from datacook.engine.restructure import StepError


if TYPE_CHECKING:
    import pathlib


def _src(session: Session, data: dict | None = None, name: str | None = None) -> str:
    data = data or {"a": [3, 1, 2], "b": [1.0, 2.0, 3.0], "c": ["x", "y", "z"]}
    return session.add(sources.InlineData.record(data=data), name=name).id


# --- column references -------------------------------------------------------------------


def test_column_refs_nested_and_per_input() -> None:
    agg = combine.GroupByAggregate.record(
        by=["a"], aggregations=[combine.Aggregation(column="b", func="sum")]
    )
    assert column_refs(agg.params) == {0: ["a", "b"]}
    merge = combine.Merge.record(left_on=["a"], right_on=["k"])
    assert column_refs(merge.params) == {0: ["a"], 1: ["k"]}
    assert column_refs(columns.RenameColumns.record(columns={"a": "z"}).params) == {0: ["a"]}
    assert column_refs(rows.Head.record(n=1).params) == {}


# --- O6: delete a middle step ------------------------------------------------------------


def test_remove_step_reparents_children(session: Session) -> None:
    src = _src(session)
    mid = session.add(rows.SortRows.record(by=["a"]), [src]).id
    c1 = session.add(rows.Head.record(n=2), [mid]).id
    c2 = session.add(columns.SelectColumns.record(columns=["a"]), [mid]).id
    gc = session.add(rows.Head.record(n=1), [c2]).id
    session.materialize(gc)
    events: list = []
    session.subscribe(events.append)
    gens = session.generations([c1, c2, gc])
    removed = session.remove_step(mid)
    assert removed.id == mid
    assert mid not in session
    assert session[c1].parents == (src,)
    assert session[c2].parents == (src,)
    assert [c.id for c in session.children(src)] == [c1, c2]
    # children and their descendants are invalidated (new generations, cache dropped)
    new = session.generations([c1, c2, gc])
    assert all(new[n] != gens[n] for n in gens)
    assert not session.is_cached(gc)
    kinds = [e.kind for e in events]
    assert kinds.count(EventKind.MOVED) == 2
    assert kinds[-1] == EventKind.REMOVED
    assert events[-1].node_ids == (mid,)
    # unsorted now: the children read the source directly
    assert session.materialize(c1)["a"].tolist() == [3, 1]
    assert "sort_values" not in session.code()


def test_remove_step_refuses_sources_and_merges(session: Session) -> None:
    left = _src(session)
    right = _src(session, {"a": [1], "d": [9]})
    merged = session.add(combine.Merge.record(on=["a"]), [left, right]).id
    session.add(rows.Head.record(n=1), [merged])
    with pytest.raises(StepError, match="first step"):
        session.remove_step(left)
    with pytest.raises(StepError, match="several inputs"):
        session.remove_step(merged)
    assert merged in session


def test_remove_step_checks_columns_of_children(session: Session) -> None:
    src = _src(session)
    renamed = session.add(columns.RenameColumns.record(columns={"a": "z"}), [src]).id
    session.add(rows.SortRows.record(by=["z"]), [renamed])
    # parent schema unknown: allowed (best effort); known: refused with the columns
    session.materialize(src)
    with pytest.raises(StepError, match="z"):
        session.remove_step(renamed)
    assert renamed in session


def test_reparent_keeps_parents_before_children(session: Session) -> None:
    src = _src(session)
    a = session.add(rows.Head.record(n=2), [src]).id
    b = session.add(rows.Head.record(n=1), [a]).id
    session.remove_step(a)
    # restore like undo does: re-add (at the end) and move the child back under it
    session.add(rows.Head.record(n=2), [src], node_id=a)
    session.reparent(b, [a])
    order = [n.id for n in session.nodes()]
    assert order.index(a) < order.index(b)
    assert session.materialize(b).shape == (1, 3)
    with pytest.raises(ValueError, match="cycle"):
        session.reparent(a, [b])


# --- O1: recipes -------------------------------------------------------------------------


def _chain(session: Session) -> tuple[str, str, str]:
    src = _src(session, name="data")
    sel = session.add(columns.SelectColumns.record(columns=["a", "b"]), [src], name="pick").id
    srt = session.add(rows.SortRows.record(by=["a"]), [sel]).id
    return src, sel, srt


def test_recipe_from_subtree_round_trip(session: Session, tmp_path: pathlib.Path) -> None:
    src, sel, _srt = _chain(session)
    session.materialize(src)
    recipe = recipes.from_subtree(session, sel, name="Clean", description="pick + sort")
    assert not recipe.is_import
    assert [s.inputs for s in recipe.steps] == [(INPUT,), (0,)]
    assert recipe.required_columns == ("a", "b")
    assert recipe.steps[0].name == "pick"
    path = tmp_path / f"clean{recipes.SUFFIX}"
    recipe.save(path)
    data = json.loads(path.read_text())
    assert data["format"] == "datacook-recipe"
    assert data["version"] == recipes.VERSION
    assert recipes.load(path) == recipe


def test_apply_to_other_frame_with_same_columns(session: Session) -> None:
    _src_id, sel, _srt = _chain(session)
    recipe = recipes.from_subtree(session, sel, name="Clean")
    other = _src(session, {"a": [9, 7, 8], "b": [0.1, 0.2, 0.3], "c": ["p", "q", "r"]})
    added = recipes.apply(session, recipe, other)
    assert len(added) == 2
    assert added[0].parents == (other,)
    result = session.materialize(added[-1].id)
    assert list(result.columns) == ["a", "b"]
    assert result["a"].tolist() == [7, 8, 9]
    # the generated code is just normal steps
    code = session.code([added[-1].id])
    assert 'sort_values(by=["a"])' in code
    assert "recipe" not in code.lower()


def test_apply_missing_column_error(session: Session) -> None:
    _src_id, sel, _srt = _chain(session)
    recipe = recipes.from_subtree(session, sel, name="Clean")
    wrong = _src(session, {"a": [1], "x": [2]})
    n = len(session)
    with pytest.raises(RecipeError, match=r"Clean.*b"):
        recipes.apply(session, recipe, wrong)
    assert len(session) == n  # nothing added
    with pytest.raises(RecipeError, match="b"):
        recipes.apply_many(session, recipe, [sel, wrong])
    assert len(session) == n  # checked before anything is added


def test_apply_many_adds_one_branch_each(session: Session) -> None:
    _src_id, sel, _srt = _chain(session)
    recipe = recipes.from_subtree(session, sel, name="Clean")
    t1 = _src(session)
    t2 = _src(session)
    branches = recipes.apply_many(session, recipe, [t1, t2])
    assert [b[0].parents for b in branches] == [(t1,), (t2,)]


def test_required_columns_without_schema_uses_first_steps(session: Session) -> None:
    src = _src(session)
    ren = session.add(columns.RenameColumns.record(columns={"a": "z"}), [src]).id
    session.add(rows.SortRows.record(by=["z"]), [ren])
    recipe = recipes.from_subtree(session, ren, name="r")
    assert recipe.required_columns == ("a",)  # "z" is made by the recipe


def test_recipe_with_branches_and_internal_merge(session: Session) -> None:
    src = _src(session)
    a = session.add(columns.SelectColumns.record(columns=["a", "b"]), [src]).id
    b = session.add(columns.SelectColumns.record(columns=["a", "c"]), [src]).id
    session.add(combine.Merge.record(on=["a"]), [a, b])
    with pytest.raises(RecipeError, match="one input"):
        recipes.from_subtree(session, a, name="x")  # the merge's second input is outside
    recipe = recipes.from_path(session, session.nodes()[-1].id, start=src, name="m")
    assert [s.inputs for s in recipe.steps] == [(INPUT,), (INPUT,), (0, 1)]
    other = _src(session)
    added = recipes.apply(session, recipe, other)
    assert session.materialize(added[-1].id).shape == (3, 3)


def test_import_recipe_batch_of_csv_files(session: Session, tmp_path: pathlib.Path) -> None:
    paths = []
    for i in range(3):
        path = tmp_path / f"part{i}.csv"
        pd.DataFrame({"a": [3 + i, 1, 2], "b": [1, 2, 3]}).to_csv(path, index=False)
        paths.append(path)
    root = session.add(sources.ReadCsv.record(path=str(paths[0]), sep=",")).id
    srt = session.add(rows.SortRows.record(by=["a"]), [root]).id
    recipe = recipes.from_path(session, srt, name="Import sorted")
    assert recipe.is_import
    with pytest.raises(RecipeError, match="import recipe"):
        recipes.plan(recipe, srt)
    branches = recipes.import_files(session, recipe, paths)
    assert len(branches) == 3
    for i, (reader, sort) in enumerate(branches):
        assert reader.parents == ()
        assert reader.name == f"part{i}.csv"
        assert reader.record.params.path == str(paths[i])  # ty: ignore[unresolved-attribute]
        assert session.materialize(sort.id)["a"].tolist() == [1, 2, 3 + i]


def test_load_rejects_bad_files(tmp_path: pathlib.Path) -> None:
    with pytest.raises(RecipeError, match="Not a DataCook recipe"):
        recipes.loads("{}")
    with pytest.raises(RecipeError, match="version"):
        recipes.loads(json.dumps({"format": "datacook-recipe", "version": 99, "steps": []}))
    bad = {"format": "datacook-recipe", "version": 1, "name": "x"}
    with pytest.raises(RecipeError, match="Step 1"):
        recipes.from_dict({**bad, "steps": [{"op": "nope", "params": {}}]})
    with pytest.raises(RecipeError, match="invalid input"):
        recipes.from_dict({**bad, "steps": [{"op": "head", "params": {}, "inputs": [0]}]})
    with pytest.raises(RecipeError, match="at least one step"):
        recipes.from_dict({**bad, "steps": []})


def test_merge_recipes(session: Session) -> None:
    src = _src(session)
    sel = session.add(columns.SelectColumns.record(columns=["a", "b"]), [src]).id
    ren = session.add(columns.RenameColumns.record(columns={"a": "z"}), [sel]).id
    srt = session.add(rows.SortRows.record(by=["z"]), [ren]).id
    session.materialize(src)
    first = recipes.from_path(session, ren, start=src, name="first")
    session.materialize(ren)
    second = recipes.from_subtree(session, srt, name="second")
    assert second.required_columns == ("z",)
    merged = recipes.merge(first, second)
    assert merged.name == "first + second"
    assert [s.inputs for s in merged.steps] == [(INPUT,), (0,), (1,)]
    assert merged.required_columns == ("a", "b")  # "z" is made by the first recipe
    out = recipes.apply(session, merged, _src(session))
    assert session.materialize(out[-1].id).columns.tolist() == ["z", "b"]


def test_library(tmp_path: pathlib.Path, session: Session) -> None:
    _src_id, sel, srt = _chain(session)
    lib = RecipeLibrary(tmp_path / "recipes")
    assert lib.entries() == []
    p1 = lib.save(recipes.from_subtree(session, sel, name="Clean"))
    p2 = lib.save(recipes.from_subtree(session, srt, name="Clean"))
    assert p1 != p2  # free file names
    assert [e.name for e in lib.entries()] == ["Clean", "Clean"]
    renamed = lib.update(p2, name="Sort only", description="just sort")
    assert not p2.exists()
    assert recipes.load(renamed).description == "just sort"
    merged = lib.merge([p1, renamed], name="Both")
    assert len(recipes.load(merged).steps) == 3
    (lib.folder / f"broken{recipes.SUFFIX}").write_text("nope")
    entries = {e.path.stem: e for e in lib.entries()}
    assert entries["broken"].recipe is None
    assert entries["broken"].error
    lib.delete(merged)
    assert merged not in [e.path for e in lib.entries()]
    imported = lib.import_file(renamed)
    assert recipes.load(imported).name == "Sort only"
