"""Generate demo data and a demo project for the app.

    uv run python tools/demo_data.py <dir> [--rows 1500000]

Writes into `<dir>`:

- `sales.parquet`: `--rows` orders of mixed data (dates, categories, ints, floats with
  missing discounts, strings),
- `stores.csv`: 40 stores (city, region, opening year),
- `demo.datacook`: a project with two readers, a fill / filter / join / group / sort chain,
  a branch ("Top discounts") and a merge (orders x stores).

Paths in the project are absolute, so it opens from any working directory.
"""

import argparse
import pathlib

import numpy as np
import pandas as pd

from datacook.engine import Session, project
from datacook.engine.ops import combine, missing, rows, sources


MISSING_DISCOUNTS = 0.08
RETURNS = 0.01
EXPRESS = 0.15

CITIES = {
    "Berlin": "East",
    "Leipzig": "East",
    "Dresden": "East",
    "Hamburg": "North",
    "Bremen": "North",
    "Kiel": "North",
    "Munich": "South",
    "Stuttgart": "South",
    "Nuremberg": "South",
    "Cologne": "West",
    "Düsseldorf": "West",
    "Dortmund": "West",
}
PRODUCTS = {
    "Coffee": ("Food", 8.99),
    "Tea": ("Food", 4.49),
    "Chocolate": ("Food", 2.29),
    "Olive oil": ("Food", 9.79),
    "Headphones": ("Electronics", 59.0),
    "USB cable": ("Electronics", 7.5),
    "Keyboard": ("Electronics", 39.9),
    "Notebook": ("Office", 3.2),
    "Pen set": ("Office", 6.4),
    "Desk lamp": ("Home", 24.9),
    "Mug": ("Home", 5.9),
    "Towel": ("Home", 12.5),
}


def stores(n: int = 40, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cities = rng.choice(list(CITIES), n)
    return pd.DataFrame({
        "store_id": np.arange(1, n + 1),
        "city": cities,
        "region": [CITIES[c] for c in cities],
        "opened": rng.integers(1995, 2024, n),
    })


def sales(rows_: int, n_stores: int = 40, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    weights = np.linspace(2, 1, len(PRODUCTS))
    product = rng.choice(list(PRODUCTS), rows_, p=weights / weights.sum())
    list_price = pd.Series({name: price for name, (_cat, price) in PRODUCTS.items()})
    price = list_price.loc[product].to_numpy() * rng.normal(1.0, 0.05, rows_)
    discount = rng.choice([0.0, 0.05, 0.1, 0.2, 0.3], rows_, p=[0.55, 0.2, 0.15, 0.07, 0.03])
    discount[rng.random(rows_) < MISSING_DISCOUNTS] = np.nan  # missing values to fill
    quantity = rng.poisson(2.5, rows_)
    quantity[rng.random(rows_) < RETURNS] *= -1  # a few returns
    start = np.datetime64("2023-01-01T08:00")
    minutes = np.sort(rng.integers(0, 3 * 365 * 24 * 60, rows_))
    return pd.DataFrame({
        "order_id": np.arange(100_000, 100_000 + rows_),
        "timestamp": start + minutes.astype("timedelta64[m]"),
        "store_id": rng.integers(1, n_stores + 1, rows_),
        "product": pd.Categorical(product),
        "category": pd.Categorical(pd.Series(product).map({k: v[0] for k, v in PRODUCTS.items()})),
        "quantity": quantity,
        "unit_price": price.round(2),
        "discount": discount,
        "segment": rng.choice(["consumer", "business", "student"], rows_, p=[0.7, 0.2, 0.1]),
        "express": rng.random(rows_) < EXPRESS,
    })


def demo_project(directory: pathlib.Path) -> Session:
    session = Session()
    orders = session.add(
        sources.ReadParquet.record(path=str(directory / "sales.parquet")), name="Orders"
    )
    shops = session.add(sources.ReadCsv.record(path=str(directory / "stores.csv")), name="Stores")
    filled = session.add(
        missing.FillMissing.record(value={"discount": 0.0}), [orders.id], name="No discount = 0"
    )
    valid = session.add(
        rows.FilterRows.record(expr="quantity > 0"), [filled.id], name="Without returns"
    )
    joined = session.add(
        combine.Merge.record(how="left", on=["store_id"]), [valid.id, shops.id], name="With stores"
    )
    grouped = session.add(
        combine.GroupByAggregate.record(
            by=["region", "category"],
            aggregations=[
                {"column": "quantity", "func": "sum", "name": "units"},
                {"column": "unit_price", "func": "mean", "name": "avg_price"},
            ],
        ),
        [joined.id],
        name="Units per region",
    )
    session.add(
        rows.SortRows.record(by=["units"], ascending=False), [grouped.id], name="Best first"
    )
    # a branch: the same cleaned orders, a different question
    top = session.add(
        rows.SortRows.record(by=["discount", "unit_price"], ascending=False),
        [valid.id],
        name="Top discounts",
    )
    session.add(rows.Head.record(n=1000), [top.id], name="First 1000")
    return session


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=pathlib.Path)
    parser.add_argument("--rows", type=int, default=1_500_000)
    args = parser.parse_args()
    directory: pathlib.Path = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stores().to_csv(directory / "stores.csv", index=False)
    sales(args.rows).to_parquet(directory / "sales.parquet", index=False)
    sales(2_000, seed=2).to_csv(directory / "sales_small.csv", index=False)
    with demo_project(directory) as session:
        project.save(session, directory / "demo.datacook")
    print(f"wrote {directory}: sales.parquet ({args.rows:,} rows), stores.csv, demo.datacook")


if __name__ == "__main__":
    main()
