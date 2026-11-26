"""Top-level package for DataCook XgBoost plugin."""

__author__ = """Philipp Temminghoff"""
__email__ = "phil65@kodi.tv"
__version__ = "0.1.0"
__copyright__ = f"Copyright 2019, {__author__}"
__maintainer__ = __author__
__status__ = "Production"
__title__ = "DataCook XgBoost plugin"


from .datacook_xgboost_plugin import XGBoostClassifier

__all__ = ["XGBoostClassifier"]
