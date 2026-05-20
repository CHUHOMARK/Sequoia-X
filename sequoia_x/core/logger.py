"""日志模块：基于 rich 库提供带颜色的结构化终端日志输出。"""

import logging
from rich.logging import RichHandler

_FORMAT = "%(name)s - %(message)s"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = RichHandler(rich_tracebacks=True, show_path=False, log_time_format="[%Y-%m-%d %H:%M:%S]")
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger
