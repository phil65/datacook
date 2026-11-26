"""Machine learning ops (scikit-learn): scaling / transforming, PCA, clustering.

Single-step ops that fit and apply on the same table (`fit_transform` / `fit_predict`).
Optional dependency: requires the `sklearn` extra (`scikit-learn>=1.9`); scikit-learn is
imported lazily inside `apply` so `import datacook` stays light.

Missing-value policy: rows with missing values (`pd.NA` / `NaN`) in the selected columns
are rejected with an `OpError` asking the user to fill or drop missing values first.
"""

import ast
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import Field, model_validator

from datacook.engine import categories
from datacook.engine.ops import base, series
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from datacook.engine.frames import Frame


type TransformerName = Literal[
    "StandardScaler",
    "MinMaxScaler",
    "RobustScaler",
    "MaxAbsScaler",
    "Normalizer",
    "PowerTransformer",
    "QuantileTransformer",
]
type NormType = Literal["l1", "l2", "max"]
type PowerMethod = Literal["yeo-johnson", "box-cox"]
type QuantileDistribution = Literal["uniform", "normal"]
type ClusterAlgorithm = Literal["KMeans", "DBSCAN"]

TRANSFORMERS: tuple[str, ...] = (
    "StandardScaler",
    "MinMaxScaler",
    "RobustScaler",
    "MaxAbsScaler",
    "Normalizer",
    "PowerTransformer",
    "QuantileTransformer",
)
CLUSTER_ALGORITHMS: tuple[str, ...] = ("KMeans", "DBSCAN")


def _columns_field() -> Any:
    return Field(
        title=N_("Columns"),
        min_length=1,
        json_schema_extra={"widget": "columns"},
    )


def _validate_numeric_input(frame: Frame, columns: Sequence[str]) -> None:
    """Validate that selected columns exist, are numeric, non-empty, and have no missing values."""
    import pandas as pd

    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise base.OpError(f"unknown columns: {missing}")
    if len(frame) == 0:
        raise base.OpError("cannot fit on an empty table")
    non_numeric = [
        c
        for c in columns
        if not pd.api.types.is_numeric_dtype(frame[c]) or pd.api.types.is_bool_dtype(frame[c])
    ]
    if non_numeric:
        raise base.OpError(f"non-numeric columns: {non_numeric}")
    with_na = [c for c in columns if frame[c].isna().any()]
    if with_na:
        raise base.OpError(
            f"missing values in columns {with_na}: fill or drop missing values first"
        )


def _parse_assign_dataframe(  # noqa: PLR0911
    stmt: ast.stmt,
    bound: Mapping[str, Any],
    *,
    allow_drop: bool = False,
) -> tuple[str, str, list[str] | None, str, dict[str, Any], list[str], list[str]] | None:
    """Parse `out = var[.drop(...)].assign(**pd.DataFrame(Est(...).fit_transform(...)))`.

    Returns `(output, var, dropped_cols, est_name, est_kwargs, input_cols, target_cols)` or None.
    """
    assign = base.assignment(stmt)
    if assign is None:
        return None
    output, value = assign
    if not (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "assign"
        and not value.args
        and len(value.keywords) == 1
        and value.keywords[0].arg is None
    ):
        return None

    receiver = value.func.value
    dropped_cols: list[str] | None = None
    if allow_drop and isinstance(receiver, ast.Call):
        if not (
            isinstance(receiver.func, ast.Attribute)
            and receiver.func.attr == "drop"
            and isinstance(receiver.func.value, ast.Name)
            and receiver.func.value.id in bound
            and not receiver.args
            and len(receiver.keywords) == 1
            and receiver.keywords[0].arg == "columns"
        ):
            return None
        try:
            dropped = base.literal_value(receiver.keywords[0].value)
        except ValueError:
            return None
        if not isinstance(dropped, list) or not all(isinstance(c, str) for c in dropped):
            return None
        dropped_cols = dropped
        var = receiver.func.value.id
    elif isinstance(receiver, ast.Name) and receiver.id in bound:
        var = receiver.id
    else:
        return None

    df_call = value.keywords[0].value
    if not (
        isinstance(df_call, ast.Call)
        and base.dotted_name(df_call.func) == "pd.DataFrame"
        and len(df_call.args) == 1
    ):
        return None

    df_kws = {kw.arg: kw.value for kw in df_call.keywords if kw.arg is not None}
    if len(df_kws) != len(df_call.keywords) or set(df_kws) != {"columns", "index"}:
        return None
    if base.dotted_name(df_kws["index"]) != f"{var}.index":
        return None
    try:
        target_cols = base.literal_value(df_kws["columns"])
    except ValueError:
        return None
    if not isinstance(target_cols, list) or not all(isinstance(c, str) for c in target_cols):
        return None

    ft_call = df_call.args[0]
    parsed_est = _parse_estimator_call(ft_call, var, "fit_transform")
    if parsed_est is None:
        return None
    est_name, est_kwargs, input_cols = parsed_est
    return output, var, dropped_cols, est_name, est_kwargs, input_cols, target_cols


def _parse_estimator_call(
    node: ast.expr, var: str, method: str
) -> tuple[str, dict[str, Any], list[str]] | None:
    """Parse `Est(**kwargs).<method>(var[cols])` -> `(est_name, est_kwargs, cols)`."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and len(node.args) == 1
        and not node.keywords
    ):
        return None
    est_call = node.func.value
    if not (
        isinstance(est_call, ast.Call)
        and isinstance(est_call.func, ast.Name)
        and not est_call.args
        and all(kw.arg is not None for kw in est_call.keywords)
    ):
        return None
    arg = node.args[0]
    if not (
        isinstance(arg, ast.Subscript) and isinstance(arg.value, ast.Name) and arg.value.id == var
    ):
        return None
    try:
        cols = base.literal_value(arg.slice)
        est_kwargs = {
            kw.arg: base.literal_value(kw.value) for kw in est_call.keywords if kw.arg is not None
        }
    except ValueError:
        return None
    if not isinstance(cols, list) or not all(isinstance(c, str) for c in cols):
        return None
    return est_call.func.id, est_kwargs, cols


class FitTransform(base.Op):
    """Fit and apply a scikit-learn preprocessing transformer on numeric columns."""

    id = "fit_transform"
    title = _("Scale / transform columns")
    description = _(
        "Fit and apply a scikit-learn scaler or transformer on numeric columns."
        " Missing values in the selected columns are rejected; fill or drop them first."
    )
    category = categories.ML
    icon = "mdi.tune-variant"
    requires = ("sklearn",)
    extra = "sklearn"

    class Params(base.Params):
        columns: list[str] = _columns_field()
        transformer: TransformerName = Field("StandardScaler", title=N_("Transformer"))
        suffix: str = Field(
            "",
            title=N_("Suffix for new columns"),
            description=N_("Empty: replace the columns. Otherwise the results are new columns."),
        )
        feature_range_min: float = Field(0.0, title=N_("Minimum (MinMaxScaler)"))
        feature_range_max: float = Field(1.0, title=N_("Maximum (MinMaxScaler)"))
        norm: NormType = Field("l2", title=N_("Norm (Normalizer)"))
        power_method: PowerMethod = Field("yeo-johnson", title=N_("Method (PowerTransformer)"))
        n_quantiles: int = Field(1000, title=N_("Quantiles (QuantileTransformer)"), ge=1)
        output_distribution: QuantileDistribution = Field(
            "uniform", title=N_("Distribution (QuantileTransformer)")
        )
        random_state: int = Field(0, title=N_("Random seed (QuantileTransformer)"))

        @model_validator(mode="after")
        def _check_range(self) -> Self:
            if (
                self.transformer == "MinMaxScaler"
                and self.feature_range_min >= self.feature_range_max
            ):
                raise ValueError("feature_range_min must be less than feature_range_max")
            return self

    @classmethod
    def imports_for(cls, params: Params) -> tuple[str, ...]:
        return ("import pandas as pd", f"from sklearn.preprocessing import {params.transformer}")

    @classmethod
    def _estimator_kwargs(cls, params: Params) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        match params.transformer:
            case "MinMaxScaler":
                if (params.feature_range_min, params.feature_range_max) != (0.0, 1.0):
                    kwargs["feature_range"] = (params.feature_range_min, params.feature_range_max)
            case "Normalizer":
                if params.norm != "l2":
                    kwargs["norm"] = params.norm
            case "PowerTransformer":
                if params.power_method != "yeo-johnson":
                    kwargs["method"] = params.power_method
            case "QuantileTransformer":
                if params.n_quantiles != 1000:  # noqa: PLR2004
                    kwargs["n_quantiles"] = params.n_quantiles
                if params.output_distribution != "uniform":
                    kwargs["output_distribution"] = params.output_distribution
                kwargs["random_state"] = params.random_state
        return kwargs

    @classmethod
    def _targets(cls, params: Params) -> list[str]:
        return [f"{c}{params.suffix}" for c in params.columns]

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import pandas as pd
        from sklearn import preprocessing

        frame = inputs[0]
        _validate_numeric_input(frame, params.columns)
        est_cls = getattr(preprocessing, params.transformer)
        estimator = est_cls(**cls._estimator_kwargs(params))
        try:
            values = estimator.fit_transform(frame[params.columns])
        except ValueError as e:
            raise base.OpError(str(e)) from e
        result = pd.DataFrame(values, columns=cls._targets(params), index=frame.index)
        return frame.assign(**result)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        est = base.format_call(params.transformer, [], cls._estimator_kwargs(params))
        cols = base.literal(params.columns)
        targets = base.literal(cls._targets(params))
        return (
            f"{output} = {var}.assign(\n"
            f"    **pd.DataFrame(\n"
            f"        {est}.fit_transform({var}[{cols}]),\n"
            f"        columns={targets},\n"
            f"        index={var}.index,\n"
            f"    )\n"
            f")"
        )

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:  # noqa: PLR0911  # noqa: PLR0911
        parsed = _parse_assign_dataframe(stmt, bound)
        if parsed is None:
            return None
        output, var, _dropped, est_name, est_kwargs, input_cols, target_cols = parsed
        if est_name not in TRANSFORMERS or len(input_cols) != len(target_cols) or not input_cols:
            return None
        suffixes: set[str] = set()
        for src, dst in zip(input_cols, target_cols):
            if not dst.startswith(src):
                return None
            suffixes.add(dst[len(src) :])
        if len(suffixes) != 1:
            return None
        suffix = suffixes.pop()
        extra: dict[str, Any] = {}
        match est_name:
            case "MinMaxScaler":
                if not set(est_kwargs) <= {"feature_range"}:
                    return None
                if "feature_range" in est_kwargs:
                    fr = est_kwargs["feature_range"]
                    if not (isinstance(fr, (tuple, list)) and len(fr) == 2):  # noqa: PLR2004
                        return None
                    extra["feature_range_min"] = fr[0]
                    extra["feature_range_max"] = fr[1]
            case "Normalizer":
                if not set(est_kwargs) <= {"norm"}:
                    return None
                extra.update(est_kwargs)
            case "PowerTransformer":
                if not set(est_kwargs) <= {"method"}:
                    return None
                if "method" in est_kwargs:
                    extra["power_method"] = est_kwargs["method"]
            case "QuantileTransformer":
                if not set(est_kwargs) <= {"n_quantiles", "output_distribution", "random_state"}:
                    return None
                extra.update(est_kwargs)
            case _:
                if est_kwargs:
                    return None
        params = cls.Params.model_validate({
            "columns": input_cols,
            "transformer": est_name,
            "suffix": suffix,
            **extra,
        })
        return series.confirm(cls, params, [var], output, stmt)


class PCA(base.Op):
    """Principal component analysis on numeric columns."""

    id = "pca"
    title = _("Principal components (PCA)")
    description = _(
        "Compute principal components (pc1..pcN) from numeric columns."
        " Missing values in the selected columns are rejected; fill or drop them first."
    )
    category = categories.ML
    icon = "mdi.axis-arrow"
    imports = ("import pandas as pd", "from sklearn.decomposition import PCA")
    requires = ("sklearn",)
    extra = "sklearn"

    class Params(base.Params):
        columns: list[str] = _columns_field()
        n_components: int = Field(2, title=N_("Components"), ge=1)
        whiten: bool = Field(False, title=N_("Whiten"))
        replace: bool = Field(
            False,
            title=N_("Replace selected columns"),
            description=N_("Drop the input columns and keep only the principal components."),
        )

    @classmethod
    def _estimator_kwargs(cls, params: Params) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"n_components": params.n_components}
        if params.whiten:
            kwargs["whiten"] = True
        return kwargs

    @classmethod
    def _pc_columns(cls, n_components: int) -> list[str]:
        return [f"pc{i}" for i in range(1, n_components + 1)]

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import pandas as pd
        from sklearn import decomposition

        frame = inputs[0]
        _validate_numeric_input(frame, params.columns)
        max_components = min(len(frame), len(params.columns))
        if params.n_components > max_components:
            raise base.OpError(
                f"n_components ({params.n_components}) cannot exceed "
                f"min(rows, columns) ({max_components})"
            )
        estimator = decomposition.PCA(**cls._estimator_kwargs(params))
        values = estimator.fit_transform(frame[params.columns])
        pcs = pd.DataFrame(values, columns=cls._pc_columns(params.n_components), index=frame.index)
        base_frame = frame.drop(columns=params.columns) if params.replace else frame
        return base_frame.assign(**pcs)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        est = base.format_call("PCA", [], cls._estimator_kwargs(params))
        cols = base.literal(params.columns)
        targets = base.literal(cls._pc_columns(params.n_components))
        target_expr = f"{var}.drop(columns={cols})" if params.replace else var
        return (
            f"{output} = {target_expr}.assign(\n"
            f"    **pd.DataFrame(\n"
            f"        {est}.fit_transform({var}[{cols}]),\n"
            f"        columns={targets},\n"
            f"        index={var}.index,\n"
            f"    )\n"
            f")"
        )

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        parsed = _parse_assign_dataframe(stmt, bound, allow_drop=True)
        if parsed is None:
            return None
        output, var, dropped_cols, est_name, est_kwargs, input_cols, target_cols = parsed
        if est_name != "PCA" or not set(est_kwargs) <= {"n_components", "whiten"}:
            return None
        n_components = est_kwargs.get("n_components")
        if not isinstance(n_components, int) or target_cols != cls._pc_columns(n_components):
            return None
        replace = dropped_cols is not None
        if replace and dropped_cols != input_cols:
            return None
        params = cls.Params(
            columns=input_cols,
            n_components=n_components,
            whiten=est_kwargs.get("whiten", False),
            replace=replace,
        )
        return series.confirm(cls, params, [var], output, stmt)


class Cluster(base.Op):
    """Cluster rows with KMeans or DBSCAN and add a cluster label column."""

    id = "cluster"
    title = _("Cluster rows")
    description = _(
        "Cluster rows using KMeans or DBSCAN on numeric columns and add a cluster label column."
        " Missing values in the selected columns are rejected; fill or drop them first."
    )
    category = categories.ML
    icon = "mdi.chart-bubble"
    requires = ("sklearn",)
    extra = "sklearn"

    class Params(base.Params):
        columns: list[str] = _columns_field()
        algorithm: ClusterAlgorithm = Field("KMeans", title=N_("Algorithm"))
        name: str = Field("cluster", title=N_("Cluster column"), min_length=1)
        n_clusters: int = Field(3, title=N_("Clusters (KMeans)"), ge=1)
        random_state: int = Field(0, title=N_("Random seed (KMeans)"))
        eps: float = Field(0.5, title=N_("Neighborhood radius eps (DBSCAN)"), gt=0)
        min_samples: int = Field(5, title=N_("Minimum samples (DBSCAN)"), ge=1)

    @classmethod
    def imports_for(cls, params: Params) -> tuple[str, ...]:
        return ("import pandas as pd", f"from sklearn.cluster import {params.algorithm}")

    @classmethod
    def _estimator_kwargs(cls, params: Params) -> dict[str, Any]:
        if params.algorithm == "KMeans":
            return {"n_clusters": params.n_clusters, "random_state": params.random_state}
        kwargs: dict[str, Any] = {}
        if params.eps != 0.5:  # noqa: PLR2004
            kwargs["eps"] = params.eps
        if params.min_samples != 5:  # noqa: PLR2004
            kwargs["min_samples"] = params.min_samples
        return kwargs

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        from sklearn import cluster as sk_cluster

        frame = inputs[0]
        _validate_numeric_input(frame, params.columns)
        if params.algorithm == "KMeans" and params.n_clusters > len(frame):
            raise base.OpError(
                f"n_clusters ({params.n_clusters}) cannot exceed row count ({len(frame)})"
            )
        est_cls = getattr(sk_cluster, params.algorithm)
        estimator = est_cls(**cls._estimator_kwargs(params))
        labels = estimator.fit_predict(frame[params.columns])
        return frame.assign(**{params.name: labels})

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        est = base.format_call(params.algorithm, [], cls._estimator_kwargs(params))
        cols = base.literal(params.columns)
        expr = f"{est}.fit_predict({var}[{cols}])"
        kwarg = base.assign_kwarg(params.name, expr)
        line = f"{output} = {var}.assign({kwarg})"
        if len(line) <= base.LINE_LENGTH:
            return line
        return f"{output} = {var}.assign(\n    {kwarg},\n)"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:  # noqa: PLR0911
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        target = base.assign_target(value, bound)
        if target is None:
            return None
        var, kw = target
        item = base.assign_item(kw)
        if item is None:
            return None
        name, expr = item
        parsed_est = _parse_estimator_call(expr, var, "fit_predict")
        if parsed_est is None:
            return None
        est_name, est_kwargs, cols = parsed_est
        if est_name not in CLUSTER_ALGORITHMS:
            return None
        if est_name == "KMeans":
            if not set(est_kwargs) <= {"n_clusters", "random_state"}:
                return None
        elif not set(est_kwargs) <= {"eps", "min_samples"}:
            return None
        params = cls.Params.model_validate({
            "columns": cols,
            "algorithm": est_name,
            "name": name,
            **est_kwargs,
        })
        return series.confirm(cls, params, [var], output, stmt)
