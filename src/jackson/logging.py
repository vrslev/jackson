import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Literal

import rich.traceback
from rich.logging import RichHandler
from rich.text import Text

rich.traceback.install(show_locals=True)
logging.basicConfig(level=logging.INFO, handlers=[], datefmt="%m/%d/%Y %I:%M:%S %p")

_loggers_name_to_progname: dict[str, str] = {}
_Mode = Literal["server", "client"]


def _get_console_handler(prog_name: str) -> RichHandler:
    time_with_prog_name = f"[%X] [{prog_name}] "
    return RichHandler(
        log_time_format=time_with_prog_name, markup=True, rich_tracebacks=True
    )


class _RichMarkupStripper(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        return Text.from_markup(text=text).plain


def _get_file_handler(mode: _Mode, name: str) -> RotatingFileHandler:
    os.makedirs(f"log/{mode}", exist_ok=True)

    filename = f"log/{mode}/{name}.log"
    size = 5 * 1024 * 1024
    handler = RotatingFileHandler(filename=filename, maxBytes=size, backupCount=5)

    formatter = _RichMarkupStripper(
        fmt="%(asctime)s  %(levelname)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)

    return handler


def _add_handlers(logger: logging.Logger, mode: _Mode, prog_name: str):
    logger.addHandler(_get_console_handler(prog_name))
    logger.addHandler(_get_file_handler(mode=mode, name=logger.name))


def configure_loggers(mode: _Mode):
    for name, prog_name in _loggers_name_to_progname.items():
        _add_handlers(logger=logging.getLogger(name), mode=mode, prog_name=prog_name)


def get_logger(name: str, prog_name: str):
    _loggers_name_to_progname[name] = prog_name.ljust(8)[:8]
    return logging.getLogger(name)


def silent_jack_stream_handler(_: str) -> None:
    pass


class MessageFilter(logging.Filter):
    messages: set[str]

    def filter(self, record: logging.LogRecord) -> bool:
        for msg in self.messages:
            if msg in record.msg:
                return False

        return super().filter(record)
