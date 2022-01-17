import logging

import rich.traceback
from rich.logging import RichHandler

rich.traceback.install()
logging.basicConfig(level=logging.INFO, handlers=[])


def get_logging_handler(name: str):
    return RichHandler(log_time_format=f"[%X] [{name}] ")


def get_configured_logger(name: str | None, prog_name: str):
    logger = logging.getLogger(name)
    logger.addHandler(get_logging_handler(prog_name.ljust(8)[:8]))
    return logger


def silent_jack_stream_handler(message: str):
    pass
