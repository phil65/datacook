from __future__ import annotations

import scipy.stats

from processanalyzer.constants import iconnames

BASE_URL = "https://docs.scipy.org/doc/scipy/reference/"


class BaseDistribution:
    icon = iconnames.TRANSFORMER
    obj = None
    alias: str

    def help_url(self):
        return f"{BASE_URL}generated/{self.module_name()}.html"

    def help_image(self):
        return f"{BASE_URL}_images/scipy-stats-{self.obj.__name__}-1.png"

    @classmethod
    def kstest(cls, data):
        param = cls.obj.fit(data)
        ks, p = scipy.stats.kstest(data, cls.obj.name, args=param)
        return {
            "Name": cls.alias,
            "Parameter": str(param),
            "ks statistic": ks,
            "p-value": p,
        }


class AlphaDistribution(BaseDistribution):
    obj = scipy.stats.alpha
    alias = "Alpha distribution"


class BetaDistribution(BaseDistribution):
    obj = scipy.stats.beta
    alias = "Beta distribution"


class NormalDistribution(BaseDistribution):
    obj = scipy.stats.norm
    alias = "Normal distribution"


class ExponentialWeibullDistribution(BaseDistribution):
    obj = scipy.stats.exponweib
    alias = "Exponential weibull distribution"


class WeibullMaxdistribution(BaseDistribution):
    obj = scipy.stats.weibull_max
    alias = "Weibull max distribution"


class WeibullMinDistribution(BaseDistribution):
    obj = scipy.stats.weibull_min
    alias = "Weibull min distribution"


class ParetoDistribution(BaseDistribution):
    obj = scipy.stats.pareto
    alias = "Pareto distribution"


class GeneralizedExtremeValueDistribution(BaseDistribution):
    obj = scipy.stats.genextreme
    alias = "Generalized extreme value"
