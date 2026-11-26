"""Top-level package for DataCook LightGbm plugin."""

__author__ = """Philipp Temminghoff"""
__email__ = "phil65@kodi.tv"
__version__ = "0.1.0"
__copyright__ = f"Copyright 2019, {__author__}"
__maintainer__ = __author__
__status__ = "Production"
__title__ = "DataCook LightGbm plugin"


from .datacook_lightgbm_plugin import LightGBMClassifier

__all__ = ["LightGBMClassifier"]
