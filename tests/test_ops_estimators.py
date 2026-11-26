"""Machine learning / estimator ops (WP4.8 part 1): scaling, PCA, clustering.

Skipped when scikit-learn is not installed (`sklearn` optional extra).
"""

import importlib.util
import subprocess
import sys
from typing import TYPE_CHECKING

import pandas as pd
import pydantic
import pytest


pytest.importorskip("sklearn")

from datacook.engine import Session, default_ops, parser
from datacook.engine.ops import OpError, estimators, record_from_json, sources


if TYPE_CHECKING:
    from datacook.engine.ops import Op


@pytest.fixture
def numeric_frame() -> pd.DataFrame:
    """Clean numeric table with a non-default index and an extra text column."""
    return (
        pd
        .DataFrame({
            "a": [1.0, 2.0, 3.0, 10.0, 11.0, 12.0],
            "b": [2.0, 1.0, 4.0, 20.0, 19.0, 22.0],
            "c": [5.0, 6.0, 7.0, 50.0, 51.0, 52.0],
            "label": ["x", "y", "z", "x", "y", "z"],
        })
        .convert_dtypes(dtype_backend="pyarrow")
        .set_axis([10, 20, 30, 40, 50, 60])
    )


CASES: dict[str, tuple[type[Op], dict]] = {
    "standard_scaler": (
        estimators.FitTransform,
        {"columns": ["a", "b"], "transformer": "StandardScaler"},
    ),
    "minmax_scaler": (
        estimators.FitTransform,
        {
            "columns": ["a", "b"],
            "transformer": "MinMaxScaler",
            "suffix": "_scaled",
            "feature_range_min": -1.0,
            "feature_range_max": 1.0,
        },
    ),
    "robust_scaler": (
        estimators.FitTransform,
        {"columns": ["a", "b"], "transformer": "RobustScaler"},
    ),
    "maxabs_scaler": (
        estimators.FitTransform,
        {"columns": ["a", "b"], "transformer": "MaxAbsScaler"},
    ),
    "normalizer": (
        estimators.FitTransform,
        {"columns": ["a", "b"], "transformer": "Normalizer", "norm": "l1"},
    ),
    "power_transformer": (
        estimators.FitTransform,
        {
            "columns": ["a", "b"],
            "transformer": "PowerTransformer",
            "power_method": "box-cox",
        },
    ),
    "quantile_transformer": (
        estimators.FitTransform,
        {
            "columns": ["a", "b"],
            "transformer": "QuantileTransformer",
            "n_quantiles": 4,
            "output_distribution": "normal",
            "random_state": 7,
        },
    ),
    "pca": (
        estimators.PCA,
        {"columns": ["a", "b", "c"], "n_components": 2},
    ),
    "pca_replace_whiten": (
        estimators.PCA,
        {"columns": ["a", "b", "c"], "n_components": 2, "whiten": True, "replace": True},
    ),
    "cluster_kmeans": (
        estimators.Cluster,
        {"columns": ["a", "b"], "algorithm": "KMeans", "n_clusters": 2, "random_state": 0},
    ),
    "cluster_kmeans_custom_name": (
        estimators.Cluster,
        {
            "columns": ["a", "b"],
            "algorithm": "KMeans",
            "name": "my cluster",
            "n_clusters": 2,
            "random_state": 42,
        },
    ),
    "cluster_dbscan": (
        estimators.Cluster,
        {"columns": ["a", "b"], "algorithm": "DBSCAN", "eps": 5.0, "min_samples": 2},
    ),
    "cluster_dbscan_defaults": (
        estimators.Cluster,
        {"columns": ["a", "b"], "algorithm": "DBSCAN"},
    ),
}

GOLDEN = {
    "standard_scaler": (
        "df = df.assign(\n"
        "    **pd.DataFrame(\n"
        '        StandardScaler().fit_transform(df[["a", "b"]]),\n'
        '        columns=["a", "b"],\n'
        "        index=df.index,\n"
        "    )\n"
        ")"
    ),
    "minmax_scaler": (
        "df = df.assign(\n"
        "    **pd.DataFrame(\n"
        '        MinMaxScaler(feature_range=(-1.0, 1.0)).fit_transform(df[["a", "b"]]),\n'
        '        columns=["a_scaled", "b_scaled"],\n'
        "        index=df.index,\n"
        "    )\n"
        ")"
    ),
    "robust_scaler": (
        "df = df.assign(\n"
        "    **pd.DataFrame(\n"
        '        RobustScaler().fit_transform(df[["a", "b"]]),\n'
        '        columns=["a", "b"],\n'
        "        index=df.index,\n"
        "    )\n"
        ")"
    ),
    "maxabs_scaler": (
        "df = df.assign(\n"
        "    **pd.DataFrame(\n"
        '        MaxAbsScaler().fit_transform(df[["a", "b"]]),\n'
        '        columns=["a", "b"],\n'
        "        index=df.index,\n"
        "    )\n"
        ")"
    ),
    "normalizer": (
        "df = df.assign(\n"
        "    **pd.DataFrame(\n"
        '        Normalizer(norm="l1").fit_transform(df[["a", "b"]]),\n'
        '        columns=["a", "b"],\n'
        "        index=df.index,\n"
        "    )\n"
        ")"
    ),
    "power_transformer": (
        "df = df.assign(\n"
        "    **pd.DataFrame(\n"
        '        PowerTransformer(method="box-cox").fit_transform(df[["a", "b"]]),\n'
        '        columns=["a", "b"],\n'
        "        index=df.index,\n"
        "    )\n"
        ")"
    ),
    "quantile_transformer": (
        "df = df.assign(\n"
        "    **pd.DataFrame(\n"
        '        QuantileTransformer(n_quantiles=4, output_distribution="normal", random_state=7)'
        '.fit_transform(df[["a", "b"]]),\n'
        '        columns=["a", "b"],\n'
        "        index=df.index,\n"
        "    )\n"
        ")"
    ),
    "pca": (
        "df = df.assign(\n"
        "    **pd.DataFrame(\n"
        '        PCA(n_components=2).fit_transform(df[["a", "b", "c"]]),\n'
        '        columns=["pc1", "pc2"],\n'
        "        index=df.index,\n"
        "    )\n"
        ")"
    ),
    "pca_replace_whiten": (
        'df = df.drop(columns=["a", "b", "c"]).assign(\n'
        "    **pd.DataFrame(\n"
        '        PCA(n_components=2, whiten=True).fit_transform(df[["a", "b", "c"]]),\n'
        '        columns=["pc1", "pc2"],\n'
        "        index=df.index,\n"
        "    )\n"
        ")"
    ),
    "cluster_kmeans": (
        'df = df.assign(cluster=KMeans(n_clusters=2, random_state=0).fit_predict(df[["a", "b"]]))'
    ),
    "cluster_kmeans_custom_name": (
        "df = df.assign(\n"
        '    **{"my cluster": KMeans(n_clusters=2, random_state=42).fit_predict(df[["a", "b"]])},\n'
        ")"
    ),
    "cluster_dbscan": (
        'df = df.assign(cluster=DBSCAN(eps=5.0, min_samples=2).fit_predict(df[["a", "b"]]))'
    ),
    "cluster_dbscan_defaults": ('df = df.assign(cluster=DBSCAN().fit_predict(df[["a", "b"]]))'),
}


def test_every_sklearn_op_has_a_case() -> None:
    sklearn_ops = {op.id for op in default_ops() if "sklearn" in op.requires}
    assert sklearn_ops == {"fit_transform", "pca", "cluster"}
    assert {op.id for op, _ in CASES.values()} == sklearn_ops


@pytest.mark.parametrize("case", sorted(CASES))
def test_apply_equals_generated_code(case: str, numeric_frame: pd.DataFrame) -> None:
    op, kwargs = CASES[case]
    params = op.Params(**kwargs)
    text = op.to_code(params, ["df"], "df")
    assert text == GOLDEN[case]

    header = "\n".join(op.imports_for(params))
    namespace: dict = {"df": numeric_frame}
    exec(f"{header}\n{text}", namespace)
    expected = op.apply(params, numeric_frame)
    pd.testing.assert_frame_equal(namespace["df"], expected)
    # copy-on-write: original frame untouched
    assert numeric_frame["a"].tolist() == [1.0, 2.0, 3.0, 10.0, 11.0, 12.0]


@pytest.mark.parametrize("case", sorted(CASES))
def test_parse_and_json_roundtrip(case: str) -> None:
    op, kwargs = CASES[case]
    record = op.record(**kwargs)
    assert record_from_json(record.to_json()) == record
    code = op.to_code(record.params, ["df"], "df")
    parsed = parser.parse(code, default_ops(), inputs=["df"])
    assert parsed.records == [record]
    assert parsed.steps[0].parents == (-1,)


def test_session_script_imports_and_replay(session: Session) -> None:
    src = session.add(
        sources.InlineData.record(
            data={
                "a": [1.0, 2.0, 3.0, 10.0, 11.0, 12.0],
                "b": [2.0, 1.0, 4.0, 20.0, 19.0, 22.0],
                "c": [5.0, 6.0, 7.0, 50.0, 51.0, 52.0],
            }
        )
    ).id
    scaled = session.add(
        estimators.FitTransform.record(columns=["a", "b"], transformer="StandardScaler"), [src]
    ).id
    pca_node = session.add(
        estimators.PCA.record(columns=["a", "b", "c"], n_components=2), [scaled]
    ).id
    clustered = session.add(
        estimators.Cluster.record(columns=["pc1", "pc2"], n_clusters=2, random_state=0), [pca_node]
    ).id

    script = session.code([clustered])
    assert "from sklearn.preprocessing import StandardScaler" in script
    assert "from sklearn.decomposition import PCA" in script
    assert "from sklearn.cluster import KMeans" in script

    namespace: dict = {}
    exec(script, namespace)
    pd.testing.assert_frame_equal(namespace["df"], session.materialize(clustered))

    with Session() as other:
        other.import_script(script)
        assert other.code() == script


def test_fit_transform_results(numeric_frame: pd.DataFrame) -> None:
    scaled = estimators.FitTransform.apply(
        estimators.FitTransform.Params(columns=["a"], transformer="MinMaxScaler", suffix="_01"),
        numeric_frame,
    )
    assert "a_01" in scaled.columns
    assert scaled["a"].tolist() == numeric_frame["a"].tolist()
    assert scaled["a_01"].min() == pytest.approx(0.0)
    assert scaled["a_01"].max() == pytest.approx(1.0)


def test_pca_replace_and_append(numeric_frame: pd.DataFrame) -> None:
    appended = estimators.PCA.apply(
        estimators.PCA.Params(columns=["a", "b", "c"], n_components=2), numeric_frame
    )
    assert appended.columns.tolist() == ["a", "b", "c", "label", "pc1", "pc2"]

    replaced = estimators.PCA.apply(
        estimators.PCA.Params(columns=["a", "b", "c"], n_components=2, replace=True),
        numeric_frame,
    )
    assert replaced.columns.tolist() == ["label", "pc1", "pc2"]


def test_cluster_kmeans_reproducible(numeric_frame: pd.DataFrame) -> None:
    params = estimators.Cluster.Params(columns=["a", "b"], n_clusters=2, random_state=0)
    first = estimators.Cluster.apply(params, numeric_frame)
    second = estimators.Cluster.apply(params, numeric_frame)
    pd.testing.assert_frame_equal(first, second)
    assert set(first["cluster"].tolist()) == {0, 1}
    # rows 0..2 form one cluster, rows 3..5 form the other
    assert len(set(first["cluster"].iloc[:3])) == 1
    assert len(set(first["cluster"].iloc[3:])) == 1
    assert first["cluster"].iloc[0] != first["cluster"].iloc[3]


def test_missing_values_rejected() -> None:
    arrow_na = pd.DataFrame({"a": [1.0, None, 3.0], "b": [4.0, 5.0, 6.0]}).convert_dtypes(
        dtype_backend="pyarrow"
    )
    numpy_nan = pd.DataFrame({"a": [1.0, float("nan"), 3.0], "b": [4.0, 5.0, 6.0]})

    for df in (arrow_na, numpy_nan):
        with pytest.raises(OpError, match="missing values"):
            estimators.FitTransform.apply(estimators.FitTransform.Params(columns=["a", "b"]), df)
        with pytest.raises(OpError, match="missing values"):
            estimators.PCA.apply(estimators.PCA.Params(columns=["a", "b"], n_components=1), df)
        with pytest.raises(OpError, match="missing values"):
            estimators.Cluster.apply(
                estimators.Cluster.Params(columns=["a", "b"], n_clusters=2), df
            )


def test_input_and_params_validation(numeric_frame: pd.DataFrame) -> None:
    # Pydantic params validation
    with pytest.raises(pydantic.ValidationError, match="feature_range_min"):
        estimators.FitTransform.Params(
            columns=["a"],
            transformer="MinMaxScaler",
            feature_range_min=2.0,
            feature_range_max=1.0,
        )
    with pytest.raises(pydantic.ValidationError):
        estimators.FitTransform.Params(columns=[])
    with pytest.raises(pydantic.ValidationError):
        estimators.PCA.Params(columns=["a"], n_components=0)
    with pytest.raises(pydantic.ValidationError):
        estimators.Cluster.Params(columns=["a"], n_clusters=0)
    with pytest.raises(pydantic.ValidationError):
        estimators.Cluster.Params(columns=["a"], algorithm="DBSCAN", eps=0.0)

    # Runtime input validation
    with pytest.raises(OpError, match="unknown columns"):
        estimators.FitTransform.apply(
            estimators.FitTransform.Params(columns=["nope"]), numeric_frame
        )
    with pytest.raises(OpError, match="non-numeric"):
        estimators.FitTransform.apply(
            estimators.FitTransform.Params(columns=["label"]), numeric_frame
        )
    with pytest.raises(OpError, match="empty"):
        estimators.PCA.apply(
            estimators.PCA.Params(columns=["a", "b"], n_components=1), numeric_frame.iloc[:0]
        )
    with pytest.raises(OpError, match="n_components"):
        estimators.PCA.apply(
            estimators.PCA.Params(columns=["a", "b"], n_components=3), numeric_frame
        )
    with pytest.raises(OpError, match="n_clusters"):
        estimators.Cluster.apply(
            estimators.Cluster.Params(columns=["a", "b"], n_clusters=10), numeric_frame
        )


def test_sklearn_imported_lazily() -> None:
    code = (
        "import sys\n"
        "from datacook.engine.ops import estimators\n"
        "loaded = [m for m in sys.modules if m == 'sklearn' or m.startswith('sklearn.')]\n"
        "print(','.join(loaded))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == ""


def test_ops_unavailable_without_sklearn(monkeypatch: pytest.MonkeyPatch) -> None:
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, package: str | None = None):
        if name == "sklearn":
            return None
        return real_find_spec(name, package)

    for op in (estimators.FitTransform, estimators.PCA, estimators.Cluster):
        assert op.available() is True
    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    for op in (estimators.FitTransform, estimators.PCA, estimators.Cluster):
        assert op.available() is False
        assert op.extra == "sklearn"
