import logging
import os
from logging.handlers import RotatingFileHandler
from typing import ClassVar, Literal

import jack
import jack_server
import rich.traceback
from rich.logging import RichHandler
from rich.text import Text

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


def _configure_logger(logger: logging.Logger, prog_name: str, mode: _Mode) -> None:
    logger.addHandler(_get_console_handler(prog_name))
    logger.addHandler(_get_file_handler(mode=mode, name=logger.name))


def configure_logging(mode: _Mode) -> None:
    for name, prog_name in _loggers_name_to_progname.items():
        _configure_logger(logging.getLogger(name), prog_name=prog_name, mode=mode)
    rich.traceback.install(show_locals=True)
    logging.basicConfig(level=logging.INFO, handlers=[], datefmt="%m/%d/%Y %I:%M:%S %p")


def get_logger(
    pretty_name: str, name: str | None = None, filter: logging.Filter | None = None
) -> logging.Logger:
    name_ = name or pretty_name
    _loggers_name_to_progname[name_] = pretty_name.ljust(8)[:8]
    log = logging.getLogger(name_)
    if filter:
        log.addFilter(filter)
    return log


class MessageFilter(logging.Filter):
    messages: ClassVar[set[str]]

    def filter(self, record: logging.LogRecord) -> bool:
        for msg in self.messages:
            if msg in record.msg:
                return False

        return super().filter(record)


class JackTripFilter(MessageFilter):
    messages = {
        "WEAK-JACK: initializing",
        "WEAK-JACK: OK.",
        "mThreadPool default maxThreadCount",
        "mThreadPool maxThreadCount previously set",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        if all(c == "-" for c in record.msg):
            return False

        if all(c == "=" for c in record.msg):
            return False

        return super().filter(record)


jack_client_log = get_logger("JackClient")
jack_server_log = get_logger("JackServer")
jacktrip_log = get_logger("JackTrip", filter=JackTripFilter())
get_logger("HttpServer", "uvicorn.access")


def _silent_stream_handler(_: str) -> None:
    pass


def set_jack_client_streams() -> None:
    jack.set_info_function(_silent_stream_handler)
    jack.set_error_function(jack_client_log.error)


def block_jack_client_streams() -> None:
    jack.set_info_function(_silent_stream_handler)
    jack.set_error_function(_silent_stream_handler)


def set_jack_server_streams() -> None:
    jack_server.set_info_function(None)
    jack_server.set_error_function(jack_server_log.error)


def block_jack_server_streams() -> None:
    jack_server.set_info_function(None)
    jack_server.set_error_function(None)
