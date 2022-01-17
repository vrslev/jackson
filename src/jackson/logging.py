import logging
from functools import partial

import rich.traceback
from rich.console import Console
from rich.logging import RichHandler
from rich.style import Style

rich.traceback.install()
logging.basicConfig(level=logging.INFO, handlers=[])


def _generate_stream_handlers(proc: str):
    console = Console(log_path=False, log_time_format=f"[%X] [{proc}]")
    return console.log, partial(console.log, style=Style(bold=True))


def get_logging_handler(name: str):
    return RichHandler(log_time_format=f"[%X] [{name}]")


def get_configured_logger(name: str | None, prog_name: str):
    logger = logging.getLogger(name)
    logger.addHandler(get_logging_handler(prog_name))
    return logger


def silent_jack_stream_handler(message: str):
    pass
