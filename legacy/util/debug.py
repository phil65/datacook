from __future__ import annotations

import functools
import logging
import time

logger = logging.getLogger(__name__)


def log_fn(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        cls_name = type(args[0]).__name__
        logger.debug(f"{cls_name}.{func.__name__} args: {args[1:]} kwargs: {kwargs}")
        return func(*args, **kwargs)

    return wrapped


def timer(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        now = time.time()
        cls_name = type(args[0]).__name__
        result = func(*args, **kwargs)
        logger.debug(f"{cls_name}.{func.__name__} took {round(time.time() - now, 3)} s")
        return result

    return wrapped
