from __future__ import annotations

import functools
import logging
import multiprocessing as mp
import time

import numpy as np
import pandas as pd
from simplification.cutil import simplify_coords, simplify_coords_vw

from prettyqt import core, gui

logger = logging.getLogger(__name__)

# mp.reducer = threads.Pickle4Reducer()
# mp.context._default_context.reducer = threads.Pickle4Reducer()
# ctx = mp.get_context()
# ctx.reducer = threads.Pickle4Reducer()


def simplify(x, y):
    dtype = y.dtype
    data = np.column_stack((x, y))
    # old_len = len(data)
    data = (
        simplify_coords_vw(data, 3.0) if len(data) > 1500 else simplify_coords(data, 0.5)
    )
    # new_len = len(data)
    data = data.T
    # data = np.concatenate((data,), axis=1)
    # if isinstance(y, pd.Series):
    #     data[0] = pd.Series(data[0]).astype(x.dtype).to_numpy()
    #     data[1] = pd.Series(data[1]).astype(y.dtype).to_numpy()
    # logger.info(f"reduced points: {old_len} -> {new_len}")
    return data[0], data[1].astype("bool") if dtype == "bool" else data[1]


def series_to_polyline(xdata, ydata):
    """convert series to polyline

    Convert series data to QPolygon(F) polyline

    This code is derived from PythonQwt's function named
    'qwt.plot_curve.series_to_polyline'

    Args:
        xdata: array for x-axis
        ydata: array for y-axis

    Returns:
        QPolygon polyline
    """
    size = len(xdata)
    polyline = gui.PolygonF(size)
    pointer = polyline.data()
    dtype, tinfo = float, np.finfo  # integers: = np.int, np.iinfo
    pointer.setsize(2 * polyline.size() * tinfo(dtype).dtype.itemsize)
    memory = np.frombuffer(pointer, dtype)
    memory[: (size - 1) * 2 + 1 : 2] = xdata
    memory[1 : (size - 1) * 2 + 2 : 2] = ydata
    return polyline


class WorkerSignals(core.Object):
    """
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        `tuple` (exctype, value, traceback.format_exc() )

    result
        `object` data returned from processing, anything

    progress
        `int` indicating % progress

    """

    finished = core.Signal()
    error = core.Signal(tuple)
    result = core.Signal(object)
    progress = core.Signal(int)
    add_lines = core.Signal(object)


class ChartWorker(core.Runnable):
    """
    QRunnable to prepare charts without blocking GUI
    """

    def __init__(self, datasets):
        """
        initalize our Thread
        """
        super().__init__()
        self.datasets = datasets
        self.signals = WorkerSignals()

    def run(self):
        """
        prepare lines for charts, emit signal when finished.
        """
        logger.debug("starting ChartWorker...")
        datasets = self.datasets
        if not isinstance(datasets, list):
            if isinstance(datasets.index, pd.MultiIndex):
                grouped = datasets.groupby(
                    datasets.index.get_level_values(0), observed=True
                )
                datasets = [g.reset_index(0, drop=True) for (n, g) in grouped]
            else:
                datasets = [datasets]
        coords = list(yield_coords(datasets))
        # resulting x-y pairs now get converted to polylines
        # (they cant get created in separate process)
        try:
            for coord in coords:
                poly = series_to_polyline(coord[0], coord[1])
                poly.name = coord[2]
                poly.process_name = coord[3]
                self.signals.add_lines.emit(poly)
        except ValueError as e:
            logger.exception(e)
        finally:
            self.signals.finished.emit()


def yield_coords(datasets: list):
    cores = int(mp.cpu_count() * 0.75)
    now = time.time()
    with mp.Pool(processes=cores) as p:
        for ds in datasets:
            if ds is None:
                continue
            ds = ds.select_dtypes(exclude=["datetime64", "category", "object", "string"])
            ds.index = ds.index.pt.index_to_secs()
            cols = ds.columns
            if len(ds.index) > 5_000_000:
                cores = int(cores / 2)
            # large dataframes are simplified
            if len(ds.index) > 200000 or len(datasets) > 100:
                logger.info(
                    "applying line simplification algorithm" " on dataset %s...", ds.title
                )
                callback = functools.partial(simplify, ds.index.to_numpy())
                result_gen = p.imap(callback, (ds[col].to_numpy() for col in cols))
                for col, result in zip(cols, result_gen):
                    yield (result[0], result[1], col, ds.title)
            else:
                for col in cols:
                    yield (ds.index.to_numpy(), ds[col].to_numpy(), col, ds.title)
    logger.debug(
        f"finished preparing chart data ({len(datasets)} datasets). "
        f"Took {time.time() - now} seconds"
    )
