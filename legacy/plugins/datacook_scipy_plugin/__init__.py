"""Top-level package for DataCook SciPy plugin."""

import itertools
import logging

import numpy as np
import pandas as pd
import scipy.fftpack
import scipy.io
import scipy.io.arff
import scipy.stats
from pandas.api.types import is_numeric_dtype

import pandastools  # type: ignore  # noqa: F401
import pandastools.accessors.scipydataframe  # type: ignore  # noqa: F401
from processanalyzer.constants import iconnames
from processanalyzer.core import categories, dataset, signals, threads
from processanalyzer.plugintypes import contextmenuplugin, filereaderplugin

from . import continuous

logger = logging.getLogger(__name__)


__author__ = """Philipp Temminghoff"""
__email__ = "phil65@kodi.tv"
__version__ = "0.1.0"
__copyright__ = f"Copyright 2019, {__author__}"
__maintainer__ = __author__
__status__ = "Production"
__title__ = "DataCook SciPy plugin"


class LeveneAction(contextmenuplugin.PluginAction):
    icon = iconnames.TABLE
    context_category = categories.StatsCategory
    description = "Apply Levene test"
    short_desc = "Levene test"
    obj = scipy.stats.levene

    def is_visible(self):
        return len(self.indexes) > 0 and self.model.content_type == "groups"

    def process(self, **kwargs):
        worker = threads.Worker(self.apply_test)
        worker.signals.result.connect(signals.signals.add_datasets)
        threads.pool.start(worker, message=f"Performing {self.short_desc}...")

    def apply_test(self):
        logger.info(f"Applying {self.short_desc}...")
        ds = self.model.ds
        results_list = []
        names = list(self.selected_names())
        for col in ds.columns:
            if not is_numeric_dtype(ds[col]):
                continue
            results = dataset.DataSet(
                index=names,
                columns=names,
                dtype="float64",
                name=f"{self.short_desc} for {col}",
                inherit_from=ds,
            )
            for (n1, p1), (n2, p2) in itertools.combinations(self.model.grouped, 2):
                if p1.empty or p2.empty:
                    continue
                if n1 not in names or n2 not in names:
                    continue
                w, pval = scipy.stats.levene(p1[col], p2[col])
                results.loc[n2, n1] = pval
                logger.info(f"levene: {n1} vs {n2}")
            results_list.append(results)
        return results_list


class MWUAction(LeveneAction):
    description = "Apply Mann-Whitney-U test"
    short_desc = "Mann-Whitney-U test"
    obj = scipy.stats.mannwhitneyu

    def apply_test(self):
        logger.info(f"Applying {self.short_desc}...")
        ds = self.model.ds
        results_list = []
        names = list(self.selected_names())
        for col in ds.columns:
            if not is_numeric_dtype(ds[col]):
                continue
            result_ds = dataset.DataSet(
                index=names,
                columns=names,
                name=f"{self.short_desc} for {col}",
                inherit_from=ds,
            )
            for n1, p1 in zip(self.selected_names(), self.selected_data()):
                for n2, p2 in zip(self.selected_names(), self.selected_data()):
                    if p1.empty or p2.empty:
                        continue
                    s1 = p1[col].to_numpy()
                    s2 = p2[col].to_numpy()
                    if np.unique(s1).size > 1 and np.unique(s2).size > 1:
                        res = scipy.stats.mannwhitneyu(s1, s2)
                        result_ds.loc[n2, n1] = res[1]  # p-value
                logger.info(f"mwu: {n1}")
            results_list.append(result_ds)
        return results_list


class FFTAction(contextmenuplugin.PluginAction):
    icon = iconnames.FFT
    context_category = categories.StatsCategory
    description = "Apply Fast fourier transformation"
    short_desc = "FFT"
    obj = scipy.fftpack.rfft

    def is_visible(self):
        return len(self.indexes) > 0 and self.model.content_type == "features"

    def process(self, **kwargs):
        ds = next(self.selected_data())
        multi_or_cat = isinstance(ds.index, (pd.MultiIndex, pd.CategoricalIndex))
        if multi_or_cat or pd.api.types.is_object_dtype(ds.index):
            logger.info(f"cannot apply FFT on DataFrame with {type(ds.index)}")
            return None
        worker = threads.Worker(self.fft)
        worker.signals.result.connect(signals.signals.add_dataset_and_focus)
        threads.pool.start(worker, set_busy=True, message="Applying FFT...")

    def fft(self) -> dataset.DataSet:
        """
        return a DataFrame with fft results
        """
        names = list(self.selected_names())
        ds = self.model.ds[names]
        logger.info("Applying FFT to %s...", ds.title)
        ds.index = ds.index.pt.index_to_secs()
        ds.log(
            "|ds|.index = |ds|.index.pt.index_to_secs()",
            description="Change index to int type",
            imports=["pandastools"],
        )
        sample_rate = ds.index[1] - ds.index[0]
        # TODO: transform seems to give different results than apply, dunno why atm...
        ds = ds.transform(lambda x: scipy.fftpack.rfft(x.to_numpy(), len(ds.index)))
        ds.set_name(f"FFT: {ds.title}")
        ds.index = scipy.fftpack.rfftfreq(len(ds.index), sample_rate)
        ds = ds.abs()
        ds.log(
            f"|ds| = |ds|.loc[:, {names}]",
            "|ds| = |ds|.transform(lambda x: scipy.fftpack.rfft(x, len(|ds|.index)))",
            "|ds|.index = scipy.fftpack.rfftfreq(len(|ds|.index), "
            "|ds|.index[1] - |ds|.index[0])",
            imports=["scipy.fftpack"],
            description=f"Apply FFT to {len(ds.columns)} feature(s)",
        )
        logger.info("Finished calculating FFT.")
        return ds


class DistributionParamsAction(contextmenuplugin.PluginAction):
    icon = iconnames.CREATE_COPY
    context_category = categories.StatsCategory
    description = "Distribution parameters"
    short_desc = "Distribution parameters"

    def is_visible(self):
        return len(self.indexes) == 1 and self.model.content_type == "features"

    def process(self, **kwargs):
        ds = self.model.ds
        colname = next(self.selected_names())
        worker = threads.Worker(self.apply, ds=ds, colname=colname)
        worker.signals.result.connect(signals.signals.add_dataset_and_focus)
        threads.pool.start(worker)

    def apply(self, ds, colname):
        dists = {d.alias: d for d in continuous.BaseDistribution.__subclasses__()}
        data = ds[colname]
        results = [dist.kstest(data) for _, dist in dists.items()]
        ds = dataset.DataSet(data=results, inherit_from=ds)
        return ds


class ArffReader(filereaderplugin.FileReaderPlugin):
    menu_label = "Arff file"
    extensions = {"ARFF files": [".arff"]}
    plugin_id = "reader.arff"
    icon = iconnames.FILE

    def read_file(self, path):
        df = pd.DataFrame.pt_scipy.load_arff(path)
        ds = dataset.DataSet(data=df, name=path.name)
        ds.log(
            "|ds| = pandas.DataFrame.pt_scipy.load_arff(|ORIGIN|)",
            imports=["pandastools.accessors.scipydataframe", "pandas"],
            operation="import",
            origin=path,
            description="Import from Arff file",
        )
        yield ds


# class MatlabReader(filereaderplugin.FileReaderPlugin):

#     menu_label = "MatLab file"
#     extensions = {"MatLab files": [".mat"]}
#     plugin_id = "reader.matlab"

#     def read_file(self, path):
#         df = pd.DataFrame.pt_scipy.load_matlab(path)
#         ds = dataset.DataSet(data=df, name=path.name)
#         ds.log("|ds| = pandas.DataFrame.pt_scipy.load_matlab(|ORIGIN|)",
#                imports=["pandastools.accessors.scipydataframe", "pandas"],
#                operation="import",
#                origin=path,
#                description="Import from Matlab file")
#         yield ds
