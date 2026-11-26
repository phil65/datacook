"""Machine learning ops (scikit-learn): scaling / transforming, PCA, clustering, cross-table apply.

Single-step ops (`FitTransform`, `PCA`, `Cluster`) fit and apply on the same table
(`fit_transform` / `fit_predict`). `ApplyModel` is a two-input op that fits a transformer,
PCA or KMeans model on a second (training) table on every run and applies it to the first
(target) table (`fit` + `transform` / `predict`), with no stored model artifacts.

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
type ModelEstimator = Literal[
    "StandardScaler",
    "MinMaxScaler",
    "RobustScaler",
    "MaxAbsScaler",
    "Normalizer",
    "PowerTransformer",
    "QuantileTransformer",
    "PCA",
    "KMeans",
]

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
MODEL_ESTIMATORS: tuple[str, ...] = (*TRANSFORMERS, "PCA", "KMeans")

_PAIR_LEN = 2
_DEFAULT_QUANTILES = 1000
_DEFAULT_EPS = 0.5
_DEFAULT_MIN_SAMPLES = 5


def _columns_field() -> Any:
    return Field(
        title=N_("Columns"),
        min_length=1,
        json_schema_extra={"widget": "columns"},
    )


class _ColumnsBase(base.Params):
    columns: list[str] = _columns_field()


class _FitTransformBase(_ColumnsBase):
    transformer: TransformerName = Field("StandardScaler", title=N_("Transformer"))


class _ClusterBase(_ColumnsBase):
    algorithm: ClusterAlgorithm = Field("KMeans", title=N_("Algorithm"))


class _ApplyModelBase(_ColumnsBase):
    estimator: ModelEstimator = Field("StandardScaler", title=N_("Estimator"))


class _TransformerOptions(base.Params):
    suffix: str = Field(
        "",
        title=N_("Suffix for new columns"),
        description=N_("Empty: replace the columns. Otherwise the results are new columns."),
    )
    feature_range_min: float = Field(0.0, title=N_("Minimum (MinMaxScaler)"))
    feature_range_max: float = Field(1.0, title=N_("Maximum (MinMaxScaler)"))
    norm: NormType = Field("l2", title=N_("Norm (Normalizer)"))
    power_method: PowerMethod = Field("yeo-johnson", title=N_("Method (PowerTransformer)"))
    n_quantiles: int = Field(_DEFAULT_QUANTILES, title=N_("Quantiles (QuantileTransformer)"), ge=1)
    output_distribution: QuantileDistribution = Field(
        "uniform", title=N_("Distribution (QuantileTransformer)")
    )
    random_state: int = Field(0, title=N_("Random seed (QuantileTransformer)"))


class _PCAOptions(base.Params):
    n_components: int = Field(2, title=N_("Components"), ge=1)
    whiten: bool = Field(False, title=N_("Whiten"))
    replace: bool = Field(
        False,
        title=N_("Replace selected columns"),
        description=N_("Drop the input columns and keep only the principal components."),
    )


class _KMeansOptions(base.Params):
    name: str = Field("cluster", title=N_("Cluster column"), min_length=1)
    n_clusters: int = Field(3, title=N_("Clusters (KMeans)"), ge=1)
    random_state: int = Field(0, title=N_("Random seed (KMeans)"))


def _check_minmax_range(estimator_name: str, minimum: float, maximum: float) -> None:
    if estimator_name == "MinMaxScaler" and minimum >= maximum:
        raise ValueError("feature_range_min must be less than feature_range_max")


def _validate_numeric_input(
    frame: Frame,
    columns: Sequence[str],
    *,
    empty_msg: str = "cannot fit on an empty table",
) -> None:
    """Validate that selected columns exist, are numeric, non-empty, and have no missing values."""
    import pandas as pd

    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise base.OpError(f"unknown columns: {missing}")
    if len(frame) == 0:
        raise base.OpError(empty_msg)
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


def _transformer_kwargs(params: _TransformerOptions, name: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    match name:
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
            if params.n_quantiles != _DEFAULT_QUANTILES:
                kwargs["n_quantiles"] = params.n_quantiles
            if params.output_distribution != "uniform":
                kwargs["output_distribution"] = params.output_distribution
            kwargs["random_state"] = params.random_state
    return kwargs


def _pca_kwargs(params: _PCAOptions) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"n_components": params.n_components}
    if params.whiten:
        kwargs["whiten"] = True
    return kwargs


def _kmeans_kwargs(params: _KMeansOptions) -> dict[str, Any]:
    return {"n_clusters": params.n_clusters, "random_state": params.random_state}


def _estimator_import(name: str) -> str:
    if name in TRANSFORMERS:
        return f"from sklearn.preprocessing import {name}"
    if name == "PCA":
        return "from sklearn.decomposition import PCA"
    return f"from sklearn.cluster import {name}"


def _make_estimator(name: str, kwargs: Mapping[str, Any]) -> Any:
    if name in TRANSFORMERS:
        from sklearn import preprocessing

        return getattr(preprocessing, name)(**kwargs)
    if name == "PCA":
        from sklearn import decomposition

        return decomposition.PCA(**kwargs)
    from sklearn import cluster as sk_cluster

    return getattr(sk_cluster, name)(**kwargs)


def _suffixed_columns(columns: Sequence[str], suffix: str) -> list[str]:
    return [f"{c}{suffix}" for c in columns]


def _extract_suffix(input_cols: Sequence[str], target_cols: Sequence[str]) -> str | None:
    if len(input_cols) != len(target_cols) or not input_cols:
        return None
    suffixes: set[str] = set()
    for src, dst in zip(input_cols, target_cols):
        if not dst.startswith(src):
            return None
        suffixes.add(dst[len(src) :])
    return suffixes.pop() if len(suffixes) == 1 else None


def _pc_columns(n_components: int) -> list[str]:
    return [f"pc{i}" for i in range(1, n_components + 1)]


def _assign_dataframe_code(
    var: str,
    output: str,
    expr: str,
    targets: list[str],
    *,
    drop_cols: list[str] | None = None,
) -> str:
    target_expr = f"{var}.drop(columns={base.literal(drop_cols)})" if drop_cols is not None else var
    return (
        f"{output} = {target_expr}.assign(\n"
        f"    **pd.DataFrame(\n"
        f"        {expr},\n"
        f"        columns={base.literal(targets)},\n"
        f"        index={var}.index,\n"
        f"    )\n"
        f")"
    )


def _assign_column_code(var: str, output: str, name: str, expr: str) -> str:
    kwarg = base.assign_kwarg(name, expr)
    line = f"{output} = {var}.assign({kwarg})"
    if len(line) <= base.LINE_LENGTH:
        return line
    return f"{output} = {var}.assign(\n    {kwarg},\n)"


def _fresh_var(prefix: str, used: set[str]) -> str:
    if prefix not in used:
        return prefix
    i = 2
    while f"{prefix}{i}" in used:
        i += 1
    return f"{prefix}{i}"


def _same_block(stmts: Sequence[ast.stmt], code: str) -> bool:
    """Whether `code` has the same sequence of statement syntax trees as `stmts`."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    return len(tree.body) == len(stmts) and all(
        ast.dump(a) == ast.dump(b) for a, b in zip(tree.body, stmts)
    )


def _parse_assign_dataframe_shell(  # noqa: PLR0911
    stmt: ast.stmt,
    bound: Mapping[str, Any],
    *,
    allow_drop: bool = False,
) -> tuple[str, str, list[str] | None, ast.expr, list[str]] | None:
    """Parse `out = var[.drop(...)].assign(**pd.DataFrame(<expr>, columns=..., index=var.index))`.

    Returns `(output, var, dropped_cols, inner_expr, target_cols)` or None.
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
    return output, var, dropped_cols, df_call.args[0], target_cols


def _parse_subscript_cols(node: ast.expr) -> tuple[str, list[str]] | None:
    """Parse `var[["a", "b"]]` -> `(var, ["a", "b"])`."""
    if not (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)):
        return None
    try:
        cols = base.literal_value(node.slice)
    except ValueError:
        return None
    if not isinstance(cols, list) or not all(isinstance(c, str) for c in cols):
        return None
    return node.value.id, cols


def _parse_estimator_call_any_var(
    node: ast.expr, method: str
) -> tuple[str, dict[str, Any], str, list[str]] | None:
    """Parse `Est(**kwargs).<method>(var[cols])` -> `(est_name, est_kwargs, var, cols)`."""
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
    subscript = _parse_subscript_cols(node.args[0])
    if subscript is None:
        return None
    try:
        est_kwargs = {
            kw.arg: base.literal_value(kw.value) for kw in est_call.keywords if kw.arg is not None
        }
    except ValueError:
        return None
    var, cols = subscript
    return est_call.func.id, est_kwargs, var, cols


def _parse_estimator_call(
    node: ast.expr, var: str, method: str
) -> tuple[str, dict[str, Any], list[str]] | None:
    """Parse `Est(**kwargs).<method>(var[cols])` -> `(est_name, est_kwargs, cols)`."""
    parsed = _parse_estimator_call_any_var(node, method)
    if parsed is None or parsed[2] != var:
        return None
    return parsed[0], parsed[1], parsed[3]


def _parse_model_call(node: ast.expr, model_var: str, var: str, method: str) -> list[str] | None:
    """Parse `<model_var>.<method>(<var>[cols])` -> `cols`."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == model_var
        and node.func.attr == method
        and len(node.args) == 1
        and not node.keywords
    ):
        return None
    subscript = _parse_subscript_cols(node.args[0])
    if subscript is None or subscript[0] != var:
        return None
    return subscript[1]


def _parse_assign_dataframe(
    stmt: ast.stmt,
    bound: Mapping[str, Any],
    *,
    allow_drop: bool = False,
) -> tuple[str, str, list[str] | None, str, dict[str, Any], list[str], list[str]] | None:
    """Parse `out = var[.drop(...)].assign(**pd.DataFrame(Est(...).fit_transform(...)))`.

    Returns `(output, var, dropped_cols, est_name, est_kwargs, input_cols, target_cols)` or None.
    """
    shell = _parse_assign_dataframe_shell(stmt, bound, allow_drop=allow_drop)
    if shell is None:
        return None
    output, var, dropped_cols, ft_call, target_cols = shell
    parsed_est = _parse_estimator_call(ft_call, var, "fit_transform")
    if parsed_est is None:
        return None
    est_name, est_kwargs, input_cols = parsed_est
    return output, var, dropped_cols, est_name, est_kwargs, input_cols, target_cols


def _parse_transformer_kwargs(  # noqa: PLR0911
    est_name: str, est_kwargs: Mapping[str, Any]
) -> dict[str, Any] | None:
    extra: dict[str, Any] = {}
    match est_name:
        case "MinMaxScaler":
            if not set(est_kwargs) <= {"feature_range"}:
                return None
            if "feature_range" in est_kwargs:
                fr = est_kwargs["feature_range"]
                if not (isinstance(fr, (tuple, list)) and len(fr) == _PAIR_LEN):
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
    return extra


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

    class Params(_TransformerOptions, _FitTransformBase):
        @model_validator(mode="after")
        def _check_range(self) -> Self:
            _check_minmax_range(self.transformer, self.feature_range_min, self.feature_range_max)
            return self

    @classmethod
    def imports_for(cls, params: Params) -> tuple[str, ...]:
        return ("import pandas as pd", _estimator_import(params.transformer))

    @classmethod
    def _estimator_kwargs(cls, params: Params) -> dict[str, Any]:
        return _transformer_kwargs(params, params.transformer)

    @classmethod
    def _targets(cls, params: Params) -> list[str]:
        return _suffixed_columns(params.columns, params.suffix)

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import pandas as pd

        frame = inputs[0]
        _validate_numeric_input(frame, params.columns)
        estimator = _make_estimator(params.transformer, cls._estimator_kwargs(params))
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
        return _assign_dataframe_code(
            var, output, f"{est}.fit_transform({var}[{cols}])", cls._targets(params)
        )

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        parsed = _parse_assign_dataframe(stmt, bound)
        if parsed is None:
            return None
        output, var, _dropped, est_name, est_kwargs, input_cols, target_cols = parsed
        if est_name not in TRANSFORMERS:
            return None
        suffix = _extract_suffix(input_cols, target_cols)
        extra = _parse_transformer_kwargs(est_name, est_kwargs)
        if suffix is None or extra is None:
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

    class Params(_PCAOptions, _ColumnsBase):
        pass

    @classmethod
    def _estimator_kwargs(cls, params: Params) -> dict[str, Any]:
        return _pca_kwargs(params)

    @classmethod
    def _pc_columns(cls, n_components: int) -> list[str]:
        return _pc_columns(n_components)

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import pandas as pd

        frame = inputs[0]
        _validate_numeric_input(frame, params.columns)
        max_components = min(len(frame), len(params.columns))
        if params.n_components > max_components:
            raise base.OpError(
                f"n_components ({params.n_components}) cannot exceed "
                f"min(rows, columns) ({max_components})"
            )
        estimator = _make_estimator("PCA", cls._estimator_kwargs(params))
        values = estimator.fit_transform(frame[params.columns])
        pcs = pd.DataFrame(values, columns=cls._pc_columns(params.n_components), index=frame.index)
        base_frame = frame.drop(columns=params.columns) if params.replace else frame
        return base_frame.assign(**pcs)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        est = base.format_call("PCA", [], cls._estimator_kwargs(params))
        cols = base.literal(params.columns)
        return _assign_dataframe_code(
            var,
            output,
            f"{est}.fit_transform({var}[{cols}])",
            cls._pc_columns(params.n_components),
            drop_cols=params.columns if params.replace else None,
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

    class Params(_KMeansOptions, _ClusterBase):
        eps: float = Field(_DEFAULT_EPS, title=N_("Neighborhood radius eps (DBSCAN)"), gt=0)
        min_samples: int = Field(_DEFAULT_MIN_SAMPLES, title=N_("Minimum samples (DBSCAN)"), ge=1)

    @classmethod
    def imports_for(cls, params: Params) -> tuple[str, ...]:
        return ("import pandas as pd", _estimator_import(params.algorithm))

    @classmethod
    def _estimator_kwargs(cls, params: Params) -> dict[str, Any]:
        if params.algorithm == "KMeans":
            return _kmeans_kwargs(params)
        kwargs: dict[str, Any] = {}
        if params.eps != _DEFAULT_EPS:
            kwargs["eps"] = params.eps
        if params.min_samples != _DEFAULT_MIN_SAMPLES:
            kwargs["min_samples"] = params.min_samples
        return kwargs

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        _validate_numeric_input(frame, params.columns)
        if params.algorithm == "KMeans" and params.n_clusters > len(frame):
            raise base.OpError(
                f"n_clusters ({params.n_clusters}) cannot exceed row count ({len(frame)})"
            )
        estimator = _make_estimator(params.algorithm, cls._estimator_kwargs(params))
        labels = estimator.fit_predict(frame[params.columns])
        return frame.assign(**{params.name: labels})

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        est = base.format_call(params.algorithm, [], cls._estimator_kwargs(params))
        cols = base.literal(params.columns)
        return _assign_column_code(var, output, params.name, f"{est}.fit_predict({var}[{cols}])")

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


class ApplyModel(base.Op):
    """Fit a scikit-learn estimator on a training table and apply it to the target table."""

    id = "apply_model"
    title = _("Apply model trained on another table")
    description = _(
        "Fit a scikit-learn transformer, PCA or KMeans model on a second (training) table"
        " and apply it to the current table. Missing values in the selected columns of either"
        " table are rejected; fill or drop them first."
    )
    category = categories.ML
    icon = "mdi.transfer-right"
    n_inputs = 2
    requires = ("sklearn",)
    extra = "sklearn"

    class Params(_KMeansOptions, _PCAOptions, _TransformerOptions, _ApplyModelBase):
        random_state: int = Field(0, title=N_("Random seed (QuantileTransformer / KMeans)"))

        @model_validator(mode="after")
        def _check_range(self) -> Self:
            _check_minmax_range(self.estimator, self.feature_range_min, self.feature_range_max)
            return self

    @classmethod
    def imports_for(cls, params: Params) -> tuple[str, ...]:
        return ("import pandas as pd", _estimator_import(params.estimator))

    @classmethod
    def _estimator_kwargs(cls, params: Params) -> dict[str, Any]:
        if params.estimator == "PCA":
            return _pca_kwargs(params)
        if params.estimator == "KMeans":
            return _kmeans_kwargs(params)
        return _transformer_kwargs(params, params.estimator)

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import pandas as pd

        target, train = inputs[0], inputs[1]
        _validate_numeric_input(train, params.columns, empty_msg="cannot fit on an empty table")
        _validate_numeric_input(
            target, params.columns, empty_msg="cannot apply model to an empty table"
        )
        if params.estimator == "PCA":
            max_components = min(len(train), len(params.columns))
            if params.n_components > max_components:
                raise base.OpError(
                    f"n_components ({params.n_components}) cannot exceed "
                    f"min(rows, columns) ({max_components})"
                )
        elif params.estimator == "KMeans" and params.n_clusters > len(train):
            raise base.OpError(
                f"n_clusters ({params.n_clusters}) cannot exceed row count ({len(train)})"
            )
        estimator = _make_estimator(params.estimator, cls._estimator_kwargs(params))
        try:
            model = estimator.fit(train[params.columns])
            if params.estimator == "KMeans":
                labels = model.predict(target[params.columns])
                return target.assign(**{params.name: labels})
            values = model.transform(target[params.columns])
        except ValueError as e:
            raise base.OpError(str(e)) from e
        if params.estimator == "PCA":
            pcs = pd.DataFrame(values, columns=_pc_columns(params.n_components), index=target.index)
            base_frame = target.drop(columns=params.columns) if params.replace else target
            return base_frame.assign(**pcs)
        result = pd.DataFrame(
            values, columns=_suffixed_columns(params.columns, params.suffix), index=target.index
        )
        return target.assign(**result)

    @classmethod
    def to_code(
        cls,
        params: Params,
        inputs: Sequence[str],
        output: str,
        *,
        model_var: str = "model",
    ) -> str:
        target_var, train_var = inputs[0], inputs[1]
        reserved = {target_var, train_var, output}
        if model_var in reserved:
            model_var = _fresh_var("model", reserved)
        est = base.format_call(params.estimator, [], cls._estimator_kwargs(params))
        cols = base.literal(params.columns)
        fit_line = f"{model_var} = {est}.fit({train_var}[{cols}])"
        if params.estimator == "KMeans":
            apply_code = _assign_column_code(
                target_var, output, params.name, f"{model_var}.predict({target_var}[{cols}])"
            )
        elif params.estimator == "PCA":
            apply_code = _assign_dataframe_code(
                target_var,
                output,
                f"{model_var}.transform({target_var}[{cols}])",
                _pc_columns(params.n_components),
                drop_cols=params.columns if params.replace else None,
            )
        else:
            apply_code = _assign_dataframe_code(
                target_var,
                output,
                f"{model_var}.transform({target_var}[{cols}])",
                _suffixed_columns(params.columns, params.suffix),
            )
        return f"{fit_line}\n{apply_code}"

    @classmethod
    def to_code_block(
        cls, params: Params, inputs: Sequence[str], output: str, used: set[str]
    ) -> str:
        model_var = _fresh_var("model", used | set(inputs) | {output})
        used.add(model_var)
        return cls.to_code(params, inputs, output, model_var=model_var)

    @classmethod
    def from_block(cls, stmts: Sequence[ast.stmt], bound: Mapping[str, Any]) -> base.Match | None:  # noqa: PLR0911
        if len(stmts) != _PAIR_LEN:
            return None
        fit_assign = base.assignment(stmts[0])
        if fit_assign is None:
            return None
        model_var, fit_expr = fit_assign
        if model_var in bound:
            return None
        parsed_fit = _parse_estimator_call_any_var(fit_expr, "fit")
        if parsed_fit is None:
            return None
        est_name, est_kwargs, train_var, train_cols = parsed_fit
        if train_var not in bound or est_name not in MODEL_ESTIMATORS or not train_cols:
            return None

        if est_name == "KMeans":
            parsed_apply = cls._parse_kmeans_apply(
                stmts[1], bound, model_var, train_cols, est_kwargs
            )
        else:
            parsed_apply = cls._parse_transform_apply(
                stmts[1], bound, model_var, est_name, train_cols, est_kwargs
            )
        if parsed_apply is None:
            return None
        output, target_var, params = parsed_apply
        expected = cls.to_code(params, [target_var, train_var], output, model_var=model_var)
        if not _same_block(stmts, expected):
            return None
        return base.Match(params, (target_var, train_var), output)

    @classmethod
    def _parse_kmeans_apply(
        cls,
        stmt: ast.stmt,
        bound: Mapping[str, Any],
        model_var: str,
        train_cols: list[str],
        est_kwargs: Mapping[str, Any],
    ) -> tuple[str, str, Params] | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        target = base.assign_target(value, bound)
        if target is None:
            return None
        target_var, kw = target
        item = base.assign_item(kw)
        if item is None:
            return None
        name, expr = item
        target_cols = _parse_model_call(expr, model_var, target_var, "predict")
        if target_cols != train_cols or not set(est_kwargs) <= {"n_clusters", "random_state"}:
            return None
        params = cls.Params.model_validate({
            "columns": train_cols,
            "estimator": "KMeans",
            "name": name,
            **est_kwargs,
        })
        return output, target_var, params

    @classmethod
    def _parse_transform_apply(  # noqa: PLR0911
        cls,
        stmt: ast.stmt,
        bound: Mapping[str, Any],
        model_var: str,
        est_name: str,
        train_cols: list[str],
        est_kwargs: Mapping[str, Any],
    ) -> tuple[str, str, Params] | None:
        shell = _parse_assign_dataframe_shell(stmt, bound, allow_drop=(est_name == "PCA"))
        if shell is None:
            return None
        output, target_var, dropped_cols, inner_expr, out_cols = shell
        target_cols = _parse_model_call(inner_expr, model_var, target_var, "transform")
        if target_cols != train_cols:
            return None
        if est_name == "PCA":
            if not set(est_kwargs) <= {"n_components", "whiten"}:
                return None
            n_components = est_kwargs.get("n_components")
            if not isinstance(n_components, int) or out_cols != _pc_columns(n_components):
                return None
            replace = dropped_cols is not None
            if replace and dropped_cols != train_cols:
                return None
            params = cls.Params.model_validate({
                "columns": train_cols,
                "estimator": "PCA",
                "n_components": n_components,
                "whiten": est_kwargs.get("whiten", False),
                "replace": replace,
            })
            return output, target_var, params
        suffix = _extract_suffix(train_cols, out_cols)
        extra = _parse_transformer_kwargs(est_name, est_kwargs)
        if suffix is None or extra is None:
            return None
        params = cls.Params.model_validate({
            "columns": train_cols,
            "estimator": est_name,
            "suffix": suffix,
            **extra,
        })
        return output, target_var, params
